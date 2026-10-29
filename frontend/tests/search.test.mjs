import test from "node:test";
import assert from "node:assert/strict";
import {
  defaults, readQuery, buildQuery, makeBrowseState, readBrowseState,
  buildCatalogQuery, listParams,
} from "../src/catalog.js";
import { createCatalogScroll } from "../src/catalogScroll.js";

test("global requests drop every catalog filter without losing the saved view", () => {
  const filters = { ...defaults(), q: "NBA 2K21", year: "2019", scope: "unknown",
    game_type: "bundle", platform_id: "167", genre_id: "31", mode_id: "2",
    min_rating: "99", min_rating_count: "1000" };
  const snapshot = makeBrowseState(filters, 4, { left: 0, top: 820 });
  const query = buildCatalogQuery(filters, 1, snapshot);
  assert.equal(query.year, "2019");
  assert.equal(query.page, "1");
  const saved = readBrowseState(query.browse);
  assert.equal(saved.page, 4);
  assert.equal(saved.filters.q, "");
  assert.equal(saved.filters.min_rating, "99");
  assert.equal(saved.position.top, 820);
  assert.deepEqual(listParams(filters), {
    q: "NBA 2K21", search_scope: "global", page: "1", page_size: "20", sort: "release_desc",
  });
});

test("filtered and empty searches preserve the normal filter parameters", () => {
  const filtered = { ...defaults(), q: "Captain Toad", search_scope: "filtered", year: "2018", scope: "all" };
  assert.deepEqual(listParams(filtered, 2), buildQuery(filtered, 2));
  const browse = { ...defaults(), q: "   ", year: "2019" };
  assert.equal(listParams(browse).year, "2019");
  assert.equal(listParams(browse).scope, "default");
  assert.equal(readQuery({ search_scope: "injected" }).filters.search_scope, "global");
});

test("snapshot survives pagination and a detail URL without recursive snapshots", () => {
  const snapshot = makeBrowseState({ ...defaults(), year: "2019", min_rating: "0" }, 3, { top: 1000 });
  const search = { ...defaults(), q: "Routine", search_scope: "filtered" };
  const secondPage = buildCatalogQuery(search, 2, snapshot);
  const encoded = new URLSearchParams(secondPage).toString();
  const routeQuery = Object.fromEntries(new URLSearchParams(encoded));
  assert.deepEqual(readBrowseState(routeQuery.browse), snapshot);
  assert.equal(readQuery(routeQuery).page, 2);
  assert.equal(readQuery(routeQuery).filters.search_scope, "filtered");
  const restored = buildQuery(snapshot.filters, snapshot.page);
  assert.equal(restored.year, "2019");
  assert.equal(restored.page, "3");
  assert.equal(restored.min_rating, "0");
  assert.equal(restored.q, undefined);
  assert.equal(restored.browse, undefined);
  assert.equal(buildCatalogQuery({ ...search, q: "" }, 1, snapshot).browse, undefined);
});

test("malformed saved views cannot restore an arbitrary route or invalid filters", () => {
  for (const value of [null, {}, "{", "x".repeat(5000), JSON.stringify({ version: 2 }),
    JSON.stringify({version:1,filters:{q:"another search"}})]) {
    assert.equal(readBrowseState(value), null);
  }
  const saved = readBrowseState(JSON.stringify({
    version: 1, filters: { year: "oops", min_rating: "NaN", scope: "bad" },
    page: -1, position: { top: -500, left: 1e20 },
  }));
  assert.equal(saved.filters.year, "2025");
  assert.equal(saved.page, 1);
  assert.deepEqual(saved.position, { top: 0, left: 10000000 });
});

test("clearing search restores the saved browse position after rendering", async () => {
  const scroll = createCatalogScroll();
  const to = { name: "catalog", fullPath: "/?year=2019&page=3" };
  const from = { name: "catalog", fullPath: "/?q=Captain" };
  scroll.restoreOnNextCatalog(to.fullPath, { left: 0, top: 905 });
  scroll.beforeNavigation(to, from, { left: 0, top: 0 });
  let resolved = false;
  const promise = scroll.scrollBehavior(to, from).then(value => { resolved = true; return value; });
  await Promise.resolve();
  assert.equal(resolved, false);
  scroll.catalogReady(to.fullPath);
  assert.deepEqual(await promise, { left: 0, top: 905, behavior: "instant" });
  const other = { name: "catalog", fullPath: "/?year=2020" };
  scroll.beforeNavigation(other, to, { left: 0, top: 905 });
  assert.deepEqual(await scroll.scrollBehavior(other, to), { left: 0, top: 0 });
});

test("an interrupted restoration cannot leak into a later navigation", async () => {
  const scroll = createCatalogScroll();
  const target = { name: "catalog", fullPath: "/?year=2019" };
  const different = { name: "catalog", fullPath: "/?year=2026" };
  scroll.restoreOnNextCatalog(target.fullPath, { left: 0, top: 900 });
  scroll.beforeNavigation(different, target, { left: 0, top: 0 });
  assert.deepEqual(await scroll.scrollBehavior(different, target), { left: 0, top: 0 });
  scroll.beforeNavigation(target, different, { left: 0, top: 0 });
  assert.deepEqual(await scroll.scrollBehavior(target, different), { left: 0, top: 0 });
});
