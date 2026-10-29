"""Discover review links using the anonymous directory's observed pagination.

Uses the ReviewsContentFeed request captured from the user's own directory.
No credentials or undocumented query fields are added. Website rules are
checked on both the directory and API host before requests are made.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import time
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.robotparser import RobotFileParser

from ign_batch import AGENT
from ign_collect import ign_url, safe_csv

ROOT = Path(__file__).resolve().parent
ENDPOINT = "https://mollusk.apis.ign.com/graphql"


def request_params(offset, sort, template):
    params = dict(template)
    variables = json.loads(params["variables"])
    variables["startIndex"] = offset
    variables["sortOption"] = sort
    params["variables"] = json.dumps(variables, separators=(",", ":"))
    return params


def capture_template(url):
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != "mollusk.apis.ign.com" or parsed.path != "/graphql":
        return None
    params = {key: values[0] for key, values in parse_qs(parsed.query).items() if len(values) == 1}
    if params.get("operationName") != "ReviewsContentFeed":
        return None
    variables = json.loads(params.get("variables", "{}"))
    if variables.get("filter") != "Games" or variables.get("sortOption") not in {"Latest", "Oldest"}:
        return None
    if variables.get("count") != 10:
        return None
    return params


class BrowserRequest:
    def __init__(self, request, headers):
        self.request = request
        self.headers = headers

    def get(self, url, **kwargs):
        return self.request.get(url, headers=self.headers, **kwargs)


def response_error(response):
    try:
        payload = response.json()
        if isinstance(payload, dict):
            return {k: payload[k] for k in ("errors", "error", "message", "code") if k in payload}
    except Exception:
        pass
    try:
        return {"response_excerpt": response.text()[:2000]}
    except Exception as exc:
        return {"body_read_error": str(exc)[:500]}


def read_rules(request, origin):
    response = request.get(origin + "/robots.txt", timeout=45000)
    rules = RobotFileParser()
    if response.status == 404:
        rules.parse([])
        return rules
    if response.status != 200:
        raise ValueError(f"Cannot check robots.txt for {origin}: HTTP {response.status}")
    text = response.text()
    if "<html" in text.lower() or "<!doctype" in text.lower():
        raise ValueError(f"robots.txt returned an HTML page for {origin}")
    rules.parse(text.splitlines())
    return rules


def unpack_feed(payload):
    errors = payload.get("errors")
    if errors:
        message = "; ".join(str(e.get("message", e)) for e in errors if isinstance(e, dict))
        raise ValueError("API returned GraphQL errors: " + message[:1200])
    feed = (payload.get("data") or {}).get("reviewContentFeed")
    if not isinstance(feed, dict) or not isinstance(feed.get("feedItems"), list):
        raise ValueError("Unexpected feed structure; no pagination assumptions made.")
    items = feed["feedItems"]
    rows = []
    for item in items:
        content = item.get("content") if isinstance(item, dict) else None
        if not isinstance(content, dict):
            continue
        try:
            url = ign_url(content.get("url") or "", "articles")
        except ValueError:
            continue
        published = content.get("publishDate")
        try:
            published_date = date.fromisoformat(str(published)[:10]).isoformat()
        except ValueError:
            published_date = None
        rows.append({"url": url, "title": content.get("title"), "review_date": published_date})
    return items, rows, feed.get("pagination")


def next_position(offset, items, pagination):
    end = pagination.get("endIndex") if isinstance(pagination, dict) else None
    if isinstance(end, int) and not isinstance(end, bool) and end >= offset:
        return end + 1
    return offset + len(items)


def content_samples(items):
    samples = []
    for item in items[:3]:
        content = item.get("content") if isinstance(item, dict) else None
        if not isinstance(content, dict):
            continue
        selected = {key: content[key] for key in ("url", "title", "publishDate", "vertical", "primaryObject", "attributes") if key in content}
        review = content.get("review")
        if isinstance(review, dict):
            selected["review"] = {key: review[key] for key in ("id", "score", "scoreText", "reviewedOn") if key in review}
        samples.append({"content_field_names": list(content), "selected_game_data": selected})
    return samples


def seek_date(request, rules, total, boundary, template, delay, probes, report_path):
    """Find the first publishDate >= boundary in the observed Oldest ordering.

Validate local and observed cross-page ordering; stop if dates are unavailable
or the feed changes rather than assuming the binary search is valid.
"""
    low, high = 0, total
    while low < high:
        position = (low + high) // 2
        url = ENDPOINT + "?" + urlencode(request_params(position, "Oldest", template))
        if not rules.can_fetch(AGENT, url):
            raise ValueError("API robots.txt disallows the archive request.")
        time.sleep(delay)
        response = request.get(url, timeout=45000)
        if response.status != 200:
            raise ValueError(f"Archive date lookup at {position}: HTTP {response.status}, {response_error(response)}")
        items, _, pagination = unpack_feed(response.json())
        if not items:
            raise ValueError(f"Archive returned an empty page at {position} inside reported total {total}.")
        if not isinstance(pagination, dict) or pagination.get("total") != total:
            raise ValueError("Archive total changed during date lookup; rerun to get a consistent range.")
        dates = []
        for item in items:
            value = (item.get("content") or {}).get("publishDate") if isinstance(item, dict) else None
            try:
                dates.append(date.fromisoformat(str(value)[:10]).isoformat())
            except ValueError as exc:
                raise ValueError("An archive item has no valid publishDate; date lookup stopped.") from exc
        if dates != sorted(dates):
            raise ValueError("Oldest page is not ordered by publishDate; cannot use date lookup reliably.")
        for earlier in probes:
            if earlier["position"] < position and earlier["first_date"] > dates[0]:
                raise ValueError("Observed archive order is inconsistent with publishDate.")
            if earlier["position"] > position and earlier["first_date"] < dates[0]:
                raise ValueError("Observed archive order is inconsistent with publishDate.")
        probes.append({"boundary": boundary, "position": position, "first_date": dates[0], "last_date": dates[-1]})
        report_path.write_text(json.dumps({"state": "locating", "total": total, "probes": probes}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Locate {boundary}: index {position} -> {dates[0]}", flush=True)
        if dates[0] < boundary:
            low = position + 1
        else:
            high = position
    return low


def write_output(folder, rows, report):
    folder.mkdir(parents=True, exist_ok=True)
    for name, text in [
        ("feed_review_urls.txt", "".join(row["url"] + "\n" for row in rows.values())),
        ("feed_discovery_report.json", json.dumps(report, ensure_ascii=False, indent=2)),
    ]:
        path = folder / name
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(path)
    path = folder / "feed_review_metadata.csv"
    temporary = path.with_suffix(".csv.tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["评测链接", "目录标题", "评测发布日期"])
        writer.writerows([[safe_csv(row[k]) for k in ("url", "title", "review_date")] for row in rows.values()])
    temporary.replace(path)


def discover(request, rules, folder, until, max_pages, delay, sort, template,
             start_index=0, end_index=None, review_from=None, review_to=None):
    # Keep separate from prior UI-discovered links. Write a checkpoint every page.
    rows = {}
    report = {"source": "Observed anonymous ReviewsContentFeed request", "sort": sort,
              "started_at": datetime.now(timezone.utc).isoformat(), "date_boundary": until,
              "pages": [], "candidate_count": 0, "stop_reason": "running",
              "coverage_complete": False, "range_start_index": start_index, "range_end_index_exclusive": end_index,
              "review_date_from": review_from, "review_date_to_exclusive": review_to}
    offset = start_index
    try:
        for page_number in range(max_pages):
            if end_index is not None and offset >= end_index:
                report["stop_reason"] = "located_date_range_scanned"
                break
            url = ENDPOINT + "?" + urlencode(request_params(offset, sort, template))
            if not rules.can_fetch(AGENT, url):
                raise ValueError("API host robots.txt disallows this request; stopped.")
            if page_number:
                time.sleep(delay)
            response = request.get(url, timeout=45000)
            page_report = {"start_index": offset, "http_status": response.status}
            report["pages"].append(page_report)
            if response.status != 200:
                page_report["response_error"] = response_error(response)
                raise ValueError(f"Pagination stopped at index {offset}: HTTP {response.status}")
            items, found, pagination = unpack_feed(response.json())
            if page_number == 0:
                (folder / "feed_api_samples.json").write_text(json.dumps(content_samples(items), ensure_ascii=False, indent=2), encoding="utf-8")
            following_offset = next_position(offset, items, pagination) if items else None
            page_report.update({"returned_items": len(items), "candidate_links": len(found),
                                "reported_pagination": pagination,
                                "next_start_index": following_offset,
                                "first_review_date": found[0]["review_date"] if found else None,
                                "last_review_date": found[-1]["review_date"] if found else None})
            before = len(rows)
            for row in found:
                if review_from or review_to:
                    if not row["review_date"]:
                        raise ValueError("Missing article publishDate inside the selected review window.")
                    if review_from and row["review_date"] < review_from:
                        continue
                    if review_to and row["review_date"] >= review_to:
                        continue
                rows[row["url"]] = row
            report["candidate_count"] = len(rows)
            print(f"Index {offset}: {len(items)} items | {len(rows)} distinct links | last review {page_report['last_review_date']}", flush=True)
            if offset == 80:
                report["index_80_returned_items"] = len(items)
                print("Index 80 result:", len(items), "items", flush=True)
            write_output(folder, rows, report)
            if not items:
                report["stop_reason"] = "empty_page_returned"
                break
            if not found:
                report["stop_reason"] = "items_without_supported_article_urls"
                break
            if page_number and len(rows) == before and (end_index is None or offset < end_index):
                report["stop_reason"] = "repeated_page_without_new_links"
                break
            dates = [row["review_date"] for row in found if row["review_date"]]
            if sort == "Latest" and dates and min(dates) < until:
                report["stop_reason"] = "review_date_boundary_reached"
                break
            if following_offset is None or following_offset <= offset:
                report["stop_reason"] = "invalid_pagination_position"
                break
            offset = following_offset
            if end_index is not None and offset >= end_index:
                report["stop_reason"] = "located_date_range_scanned"
                break
        else:
            report["stop_reason"] = "max_pages_reached"
    except KeyboardInterrupt:
        report["stop_reason"] = "interrupted"
        print("Interrupted; collected links saved.")
    except Exception as exc:
        report["stop_reason"] = "request_or_response_error"
        report["error"] = str(exc)
        print("ERROR:", exc)
    finally:
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        write_output(folder, rows, report)
    print("Stop reason:", report["stop_reason"])
    print("Links:", folder / "feed_review_urls.txt")
    print("Report:", folder / "feed_discovery_report.json")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--until", default="2024-01-01")
    parser.add_argument("--max-pages", type=int, default=100, help="Pages of 10 items, maximum 300")
    parser.add_argument("--delay", type=float, default=4)
    parser.add_argument("--sort", choices=["Latest", "Oldest"], default="Latest")
    parser.add_argument("--headless", action="store_true", help="Run discovery without a visible browser window")
    parser.add_argument("--proxy", help="Explicit local HTTP proxy, for example http://127.0.0.1:7897")
    parser.add_argument("--http", action="store_true", help="Use public HTTP for feed requests after browser discovery")
    parser.add_argument("--review-from", help="Oldest archive: inclusive review publish date")
    parser.add_argument("--review-to", help="Oldest archive: exclusive review publish date")
    args = parser.parse_args()
    if not 1 <= args.max_pages <= 300 or not 3 <= args.delay <= 60:
        parser.error("--max-pages must be 1–300 and --delay must be 3–60")
    try:
        date.fromisoformat(args.until)
    except ValueError:
        parser.error("--until must be an ISO date")
    if bool(args.review_from) != bool(args.review_to):
        parser.error("Use --review-from and --review-to together")
    if args.review_from:
        if args.sort != "Oldest":
            parser.error("Date range lookup requires --sort Oldest")
        try:
            if date.fromisoformat(args.review_from) >= date.fromisoformat(args.review_to):
                parser.error("--review-from must precede --review-to")
        except ValueError:
            parser.error("Review range dates must use YYYY-MM-DD")
    try:
        from playwright.sync_api import sync_playwright
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", r"F:\PlaywrightBrowsers")
        output = ROOT / "data" / "feed_discovery" / (datetime.now().strftime("%Y%m%d_%H%M%S_%f") + "_browser_" + args.sort.lower())
        output.mkdir(parents=True)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=args.headless,
                **({'proxy': {'server': args.proxy}} if args.proxy else {}))
            try:
                context = browser.new_context()
                request = context.request
                if args.http:
                    from ign_public_http import PublicHTTP
                    request = PublicHTTP(args.proxy)
                directory_rules = read_rules(request, "https://www.ign.com")
                if not directory_rules.can_fetch(AGENT, "https://www.ign.com/reviews/games"):
                    raise ValueError("Directory robots.txt disallows automated access.")
                api_rules = read_rules(request, "https://mollusk.apis.ign.com")
                interval = args.delay
                for rules in (directory_rules, api_rules):
                    interval = max(interval, rules.crawl_delay(AGENT) or rules.crawl_delay("*") or 0)
                    rate = rules.request_rate(AGENT) or rules.request_rate("*")
                    if rate and rate.requests:
                        interval = max(interval, rate.seconds / rate.requests)
                if interval > 60:
                    raise ValueError("Site requires a longer wait; stopped for scheduler setup.")
                observed = {}
                allowed_headers = {"accept", "content-type", "origin", "referer", "apollographql-client-name",
                                   "apollographql-client-version", "apollo-require-preflight", "x-ign-app-id", "x-ign-app-version"}

                def observe(response):
                    try:
                        template = capture_template(response.url)
                        if template is None:
                            return
                        if json.loads(template["variables"]).get("sortOption") != args.sort:
                            return
                        observed["last_status"] = response.status
                        if response.status != 200:
                            observed["last_error"] = response_error(response)
                            return
                        unpack_feed(response.json())
                        observed["template"] = template
                        observed["headers"] = {k: v for k, v in response.request.headers.items() if k.lower() in allowed_headers}
                    except Exception as exc:
                        observed["capture_error"] = str(exc)[:1500]

                page = context.new_page()
                page.on("response", observe)
                response = page.goto("https://www.ign.com/reviews/games", wait_until="domcontentloaded", timeout=45000)
                if not response or response.status >= 400:
                    raise ValueError("Browser directory access failed.")
                sort_control = page.locator("select#sortBy")
                sort_control.wait_for(state="visible", timeout=30000)
                if sort_control.input_value() != args.sort:
                    sort_control.select_option(args.sort)
                page.locator('[data-cy="content-item"]').first.wait_for(state="attached", timeout=30000)
                print("Capturing a successful pagination request from the normal directory...", flush=True)
                for _ in range(4):
                    if observed.get("template"):
                        break
                    if observed.get("last_status") in {401, 403, 429}:
                        raise ValueError("Browser pagination is denied or rate-limited; stopped.")
                    page.locator('[data-cy="content-item"]').last.scroll_into_view_if_needed(timeout=10000)
                    page.evaluate("window.scrollBy(0, -500)")
                    page.wait_for_timeout(500)
                    page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
                    page.wait_for_timeout(int(interval * 1000))
                if not observed.get("template"):
                    (output / "request_capture_report.json").write_text(json.dumps(observed, ensure_ascii=False, indent=2), encoding="utf-8")
                    raise ValueError("No successful live pagination request captured. Upload request_capture_report.json.")
                print("Captured live ReviewsContentFeed parameters.", flush=True)
                adapter = BrowserRequest(request, observed["headers"])
                # Recheck the exact successful URL before changing its pagination index.
                baseline_url = ENDPOINT + "?" + urlencode(observed["template"])
                if not api_rules.can_fetch(AGENT, baseline_url):
                    raise ValueError("API robots.txt disallows this request.")
                time.sleep(interval)
                baseline = adapter.get(baseline_url, timeout=45000)
                if baseline.status != 200:
                    failure = {"stage": "baseline_replay", "http_status": baseline.status,
                               "response_error": response_error(baseline),
                               "captured_header_names": list(observed["headers"])}
                    (output / "request_capture_report.json").write_text(json.dumps(failure, ensure_ascii=False, indent=2), encoding="utf-8")
                    raise ValueError("Baseline request replay failed. Upload request_capture_report.json.")
                _, _, baseline_pagination = unpack_feed(baseline.json())
                time.sleep(interval)
                start_index, end_index = 0, None
                if args.review_from:
                    total = baseline_pagination.get("total") if isinstance(baseline_pagination, dict) else None
                    if not isinstance(total, int) or isinstance(total, bool) or total <= 0:
                        raise ValueError("Oldest API did not provide a usable archive total.")
                    probes = []
                    seek_report = output / "archive_seek_report.json"
                    try:
                        start_index = seek_date(adapter, api_rules, total, args.review_from, observed["template"], interval, probes, seek_report)
                        end_index = seek_date(adapter, api_rules, total, args.review_to, observed["template"], interval, probes, seek_report)
                        seek_report.write_text(json.dumps({"state": "located", "total": total, "range_start": start_index,
                            "range_end_exclusive": end_index, "probes": probes}, ensure_ascii=False, indent=2), encoding="utf-8")
                    except Exception as exc:
                        seek_report.write_text(json.dumps({"state": "error", "error": str(exc), "total": total,
                            "probes": probes}, ensure_ascii=False, indent=2), encoding="utf-8")
                        raise
                    print(f"Review window: indices {start_index} through {end_index - 1}", flush=True)
                report = discover(adapter, api_rules, output, args.until, args.max_pages, interval, args.sort, observed["template"],
                                  start_index, end_index, args.review_from, args.review_to)
                return 1 if report["stop_reason"] == "request_or_response_error" else 0
            finally:
                browser.close()
    except Exception as exc:
        print("ERROR:", exc)
        if 'output' in locals():
            print("Diagnostic directory:", output)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
