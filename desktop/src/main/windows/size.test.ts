import assert from "node:assert/strict";
import { test } from "node:test";

import { DEFAULT_WINDOW_SIZE, MIN_WINDOW_SIZE } from "./size";

/**
 * The window refuses to shrink below `MIN_WINDOW_SIZE`, so that number has to
 * stay inside what the Dashboard can actually lay out: its mobile fallback kicks
 * in under 767px and the sidebar already spends 220px of the width.
 */

test("the minimum keeps the Dashboard in its desktop layout", () => {
  assert.ok(MIN_WINDOW_SIZE.width >= 768, "768px is the Dashboard's mobile breakpoint");
  assert.ok(MIN_WINDOW_SIZE.height > 0);
});

test("the minimum is smaller than the size a window opens at", () => {
  // Otherwise the window could never reach its own default size.
  assert.ok(MIN_WINDOW_SIZE.width < DEFAULT_WINDOW_SIZE.width);
  assert.ok(MIN_WINDOW_SIZE.height < DEFAULT_WINDOW_SIZE.height);
});
