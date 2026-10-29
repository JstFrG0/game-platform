"""Sequential IGN link-list collection with SQLite checkpoints.

Keep this file beside ign_collect.py. Existing game records are reused.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import math
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.robotparser import RobotFileParser

from ign_collect import export_files, ign_url, parse_review, safe_csv, save_record

ROOT = Path(__file__).resolve().parent
AGENT = "GameDataCollector"


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def read_links(path):
    links = []
    errors = []
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if not line.startswith("https://"):
            errors.append(f"Line {number}: expected a complete HTTPS URL")
            continue
        try:
            url = ign_url(line, "articles")
            if url not in links:
                links.append(url)
        except ValueError as exc:
            errors.append(f"Line {number}: {exc}")
    if errors:
        raise ValueError("Invalid list. Nothing collected:\n" + "\n".join(errors))
    if not links:
        raise ValueError("The list is empty. Add one review URL per line.")
    return links


def table_exists(connection, name):
    return connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def register_tasks(connection, links, retry_failed=False, refresh=False):
    connection.execute("""CREATE TABLE IF NOT EXISTS collection_tasks (
        url TEXT PRIMARY KEY, status TEXT NOT NULL,
        attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT, updated_at TEXT NOT NULL)""")
    existing = {row[0] for row in connection.execute("SELECT review_url FROM reviews")} if table_exists(connection, "reviews") else set()
    with connection:
        for url in links:
            row = connection.execute("SELECT status FROM collection_tasks WHERE url=?", (url,)).fetchone()
            if row is None:
                status = "success" if url in existing and not refresh else "pending"
                connection.execute("INSERT INTO collection_tasks VALUES (?, ?, 0, NULL, ?)", (url, status, timestamp()))
            elif refresh or (retry_failed and row[0] == "failed"):
                update_status(connection, url, "pending")
            elif row[0] == "running":
                update_status(connection, url, "success" if url in existing else "pending")
            elif url in existing and row[0] == "pending":
                update_status(connection, url, "success")


def update_status(connection, url, status, error=None, add_attempt=False):
    connection.execute("""UPDATE collection_tasks SET status=?, last_error=?, updated_at=?,
        attempts=attempts+? WHERE url=?""", (status, error, timestamp(), int(add_attempt), url))


def pending_tasks(connection, links):
    return [url for url in links if connection.execute(
        "SELECT status FROM collection_tasks WHERE url=?", (url,)).fetchone()[0] == "pending"]


def write_reports(connection, directory):
    directory.mkdir(parents=True, exist_ok=True)
    rows = connection.execute("SELECT url,status,attempts,last_error,updated_at FROM collection_tasks ORDER BY url").fetchall()
    path = directory / "batch_status.csv"
    temporary = path.with_suffix(".csv.tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["评测链接", "状态", "累计尝试次数", "最近错误", "更新时间（UTC）"])
        writer.writerows([[safe_csv(v) for v in row] for row in rows])
    temporary.replace(path)
    failed = directory / "failed_urls.txt"
    temporary = failed.with_suffix(".txt.tmp")
    temporary.write_text("".join(row[0] + "\n" for row in rows if row[1] == "failed"), encoding="utf-8")
    temporary.replace(failed)
    totals = dict(connection.execute("SELECT status,count(*) FROM collection_tasks GROUP BY status"))
    print("Task totals (all batches):", totals, flush=True)
    print("Status report:", path)


def load_robots(request):
    response = request.get("https://www.ign.com/robots.txt", timeout=30000)
    if response.status == 404:
        rules = RobotFileParser()
        rules.parse([])
        return rules
    if response.status != 200:
        raise ValueError(f"Cannot check robots.txt (HTTP {response.status}); pending tasks preserved.")
    text = response.text()
    if "<html" in text.lower() or "<!doctype" in text.lower():
        raise ValueError("robots.txt returned an HTML page; pending tasks preserved.")
    rules = RobotFileParser()
    rules.parse(text.splitlines())
    return rules


class BatchStop(ValueError):
    """Stop new requests after the server denies or rate-limits access."""


def run_batch(connection, links, directory, delay, retries, headless, limit):
    from playwright.sync_api import Error, sync_playwright

    jobs = pending_tasks(connection, links)[:limit]
    print(f"List: {len(links)} distinct URLs; queued this run: {len(jobs)}", flush=True)
    if not jobs:
        print("Nothing queued. Successful URLs are skipped; use --retry-failed for failed URLs.")
        return
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", r"F:\PlaywrightBrowsers")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        try:
            context = browser.new_context()
            # Use the actual browser UA with an explicit collector identifier.
            probe = context.new_page()
            user_agent = probe.evaluate("navigator.userAgent") + " " + AGENT + "/0.2"
            context.close()
            context = browser.new_context(user_agent=user_agent)
            rules = load_robots(context.request)
            crawl_delay = rules.crawl_delay(AGENT) or rules.crawl_delay("*") or 0
            interval = max(delay, crawl_delay)
            request_rate = rules.request_rate(AGENT) or rules.request_rate("*")
            if request_rate and request_rate.requests > 0:
                interval = max(interval, request_rate.seconds / request_rate.requests)
            if interval > 60:
                raise ValueError("Site requests an interval above 60 seconds; pending tasks preserved for a later scheduler.")
            page = context.new_page()
            for index, url in enumerate(jobs, 1):
                print(f"[{index}/{len(jobs)}] {url}", flush=True)
                if not rules.can_fetch(AGENT, url):
                    with connection:
                        update_status(connection, url, "failed", "robots.txt disallows automated access")
                    print("  FAILED: robots.txt disallows automated access", flush=True)
                    continue
                for attempt in range(retries + 1):
                    if index > 1 or attempt > 0:
                        time.sleep(max(interval, min(20, 4 * attempt)))
                    with connection:
                        update_status(connection, url, "running", add_attempt=True)
                    try:
                        response = page.goto(url, wait_until="domcontentloaded", timeout=45000)
                        if response is None:
                            raise ValueError("Navigation returned no response")
                        if response.status in {401, 403, 429}:
                            raise BatchStop(f"HTTP {response.status}; batch paused, no bypass attempted")
                        if response.status >= 500:
                            raise Error(f"HTTP {response.status}")
                        if response.status >= 400:
                            raise ValueError(f"HTTP {response.status}")
                        final_url = ign_url(page.url, "articles")
                        if not rules.can_fetch(AGENT, final_url):
                            raise ValueError("Redirected page disallowed by robots.txt")
                        page.wait_for_function("() => Boolean(document.querySelector('script#__NEXT_DATA__'))", timeout=15000)
                        html = page.content()
                        record = parse_review(html)
                        if record["review_url"] != final_url:
                            raise ValueError("Review canonical URL differs from loaded page; check manually")
                        folder = directory / "samples" / (datetime.now().strftime("%Y%m%d_%H%M%S_%f") + "_" + hashlib.sha256(url.encode()).hexdigest()[:8])
                        folder.mkdir(parents=True)
                        (folder / "review.html").write_text(html, encoding="utf-8")
                        # Commit data first; restart detects a saved record if interrupted here.
                        save_record(connection, record)
                        with connection:
                            update_status(connection, url, "success")
                        print(f"  OK: {record['name']} | IGN {record['score']}", flush=True)
                        break
                    except BatchStop as exc:
                        with connection:
                            update_status(connection, url, "failed", str(exc))
                        raise
                    except Error as exc:
                        if attempt < retries:
                            print("  Temporary error; retrying...", flush=True)
                            continue
                        with connection:
                            update_status(connection, url, "failed", str(exc)[:1500])
                        print("  FAILED:", str(exc)[:250], flush=True)
                    except (ValueError, KeyError, TypeError, OSError) as exc:
                        with connection:
                            update_status(connection, url, "failed", str(exc)[:1500])
                        print("  FAILED:", str(exc)[:250], flush=True)
                        break
        finally:
            browser.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, default=ROOT / "urls.txt")
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--refresh", action="store_true", help="Recollect every URL in this list")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--delay", type=float, default=4, help="Minimum seconds between requests (3–60)")
    parser.add_argument("--retries", type=int, default=1, choices=[0, 1, 2])
    parser.add_argument("--limit", type=int, default=50, help="Maximum queued URLs processed this run")
    parser.add_argument("--year", type=int, help="Filter exports by earliest confirmed US release year")
    parser.add_argument("--csv-only", action="store_true")
    parser.add_argument("--check-list", action="store_true", help="Validate URLs without browser or database changes")
    args = parser.parse_args()
    if not math.isfinite(args.delay) or not 3 <= args.delay <= 60:
        parser.error("--delay must be between 3 and 60")
    if not 1 <= args.limit <= 200:
        parser.error("--limit must be between 1 and 200")
    if args.year is not None and not 1900 <= args.year <= 2200:
        parser.error("--year must be between 1900 and 2200")
    try:
        links = read_links(args.file)
        if args.check_list:
            print(f"Valid list: {len(links)} distinct URLs")
            return 0
        directory = ROOT / "data"
        directory.mkdir(parents=True, exist_ok=True)
        code = 0
        with sqlite3.connect(directory / "games.sqlite3") as connection:
            register_tasks(connection, links, args.retry_failed, args.refresh)
            try:
                run_batch(connection, links, directory, args.delay, args.retries, args.headless, args.limit)
            except KeyboardInterrupt:
                print("Interrupted. Checkpoints saved; rerun the same command to continue.")
                code = 130
            except Exception as exc:
                print("Batch stopped:", exc)
                code = 1
            finally:
                write_reports(connection, directory / "exports")
                if table_exists(connection, "reviews"):
                    export_files(connection, directory / "exports", args.year, args.csv_only)
                else:
                    print("No successful reviews yet; only task reports were exported.")
            if any(connection.execute("SELECT status FROM collection_tasks WHERE url=?", (url,)).fetchone()[0] == "failed" for url in links):
                code = code or 2
        return code
    except (OSError, ValueError, sqlite3.Error) as exc:
        print("ERROR:", exc)
        print("Close Excel before exporting. Send the error text if it persists.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
