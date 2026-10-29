import test from "node:test";
import assert from "node:assert/strict";
import { busyUpdateStates, shouldRefreshCatalog, updateStatusText } from "../src/dataUpdateStatus.js";

test("only a committed version change refreshes the visible catalog", () => {
  assert.equal(shouldRefreshCatalog(undefined, "v1"), false);
  assert.equal(shouldRefreshCatalog(null, "v1"), true);
  assert.equal(shouldRefreshCatalog("v1", "v1"), false);
  assert.equal(shouldRefreshCatalog("v1", "v2"), true);
  assert.equal(shouldRefreshCatalog("v1", null), false);
});

test("download and database installation remain busy and have distinct messages", () => {
  for (const status of ["checking", "downloading", "installing"]) assert.ok(busyUpdateStates.has(status));
  assert.ok(!busyUpdateStates.has("failed"));
  assert.equal(updateStatusText({ status: "installing" }), "正在备份并更新资料");
  assert.equal(updateStatusText({ status: "up_to_date" }), "游戏资料已是最新");
});
