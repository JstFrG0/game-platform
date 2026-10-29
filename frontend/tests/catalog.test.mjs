import test from "node:test";
import assert from "node:assert/strict";
import { readQuery, buildQuery, defaults } from "../src/catalog.js";
import { score, displayCover } from "../src/api.js";

test("restore filters and pagination from URL without losing zero rating", () => {
  const state = readQuery({
    q: "Routine",
    page: "3",
    min_rating: "0",
    platform_id: "6",
    scope: "all",
  });
  assert.equal(state.page, 3);
  assert.equal(state.filters.min_rating, "0");
  assert.equal(state.filters.scope, "all");
  assert.equal(buildQuery(state.filters, state.page).q, "Routine");
  assert.equal(buildQuery(state.filters, state.page).page, "3");
});
test("invalid URL values fall back to safe defaults", () => {
  const state = readQuery({
    year: "abc",
    page: "-1",
    min_rating: "NaN",
    scope: "bad",
    sort: "bad",
    genre_id: "1.5",
    q: ["injected"],
  });
  assert.equal(state.page, 1);
  assert.deepEqual(state.filters, defaults());
});
test("missing score stays distinct from zero", () => {
  assert.equal(score(null), "暂无评分");
  assert.equal(score(0), "0.0");
  assert.equal(score(77.1482838), "77.1");
});
test("only IGDB thumbnail paths are upgraded", () => {
  assert.equal(
    displayCover(
      "https://images.igdb.com/igdb/image/upload/t_thumb/coay6e.jpg",
    ),
    "https://images.igdb.com/igdb/image/upload/t_cover_big_2x/coay6e.jpg",
  );
  assert.equal(
    displayCover("https://other.example/t_thumb/a.jpg"),
    "https://other.example/t_thumb/a.jpg",
  );
  assert.equal(displayCover(null), null);
});
