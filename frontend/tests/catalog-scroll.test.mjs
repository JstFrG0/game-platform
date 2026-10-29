import test from "node:test";
import assert from "node:assert/strict";
import { createCatalogScroll } from "../src/catalogScroll.js";

const list = { name: "catalog", fullPath: "/?page=2&genre_id=12" };
const detail = { name: "detail", fullPath: "/games/8948?page=2&genre_id=12" };
const other = { name: "catalog", fullPath: "/?page=3" };

test("detail return waits for the matching list render and restores its position", async () => {
  const scroll = createCatalogScroll();
  scroll.beforeNavigation(detail, list, { left: 0, top: 1420 });
  scroll.beforeNavigation(list, detail, { left: 0, top: 50 });
  let resolved = false;
  const result = scroll.scrollBehavior(list, detail, null).then((value) => {
    resolved = true;
    return value;
  });
  scroll.catalogReady(other.fullPath);
  await Promise.resolve();
  assert.equal(resolved, false);
  scroll.catalogReady(list.fullPath);
  assert.deepEqual(await result, { left: 0, top: 1420, behavior: "instant" });
});

test("browser history position takes priority and also waits for rendering", async () => {
  const scroll = createCatalogScroll();
  scroll.beforeNavigation(detail, list, { left: 0, top: 1420 });
  scroll.beforeNavigation(list, detail, { left: 0, top: 0 });
  const result = scroll.scrollBehavior(list, detail, { left: 0, top: 920 });
  scroll.catalogReady(list.fullPath);
  assert.deepEqual(await result, { left: 0, top: 920, behavior: "instant" });
});

test("a later navigation cancels a pending restoration", async () => {
  const scroll = createCatalogScroll();
  scroll.beforeNavigation(detail, list, { left: 0, top: 1420 });
  scroll.beforeNavigation(list, detail, { left: 0, top: 0 });
  const pending = scroll.scrollBehavior(list, detail, null);
  scroll.beforeNavigation(other, list, { left: 0, top: 0 });
  scroll.catalogReady(list.fullPath);
  assert.equal(await pending, false);
  assert.deepEqual(await scroll.scrollBehavior(other, list, null), { left: 0, top: 0 });
});

test("new filters and another list do not inherit an unrelated saved position", async () => {
  const scroll = createCatalogScroll();
  scroll.beforeNavigation(detail, list, { left: 0, top: 1420 });
  scroll.beforeNavigation(other, detail, { left: 0, top: 0 });
  assert.deepEqual(await scroll.scrollBehavior(other, detail, null), { left: 0, top: 0 });
  scroll.beforeNavigation(list, other, { left: 0, top: 200 });
  assert.deepEqual(await scroll.scrollBehavior(list, other, null), { left: 0, top: 0 });
});
