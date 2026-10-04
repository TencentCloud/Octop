import { test } from "node:test";
import assert from "node:assert/strict";
import { PNG } from "pngjs";
import { compareScreenshots } from "./compare-workbuddy-screenshots.mjs";

test("reports changed pixels after excluding only the documented dynamic region", () => {
  const reference = new PNG({ width: 10, height: 10 });
  const actual = new PNG({ width: 10, height: 10 });
  actual.data[0] = 255;
  actual.data[4] = 255;
  const result = compareScreenshots(reference, actual, [
    { x: 0, y: 0, width: 1, height: 1, reason: "stream cursor" },
  ]);
  assert.equal(result.maskedPixels, 1);
  assert.equal(result.changedPixels, 1);
  assert.equal(result.changedRatio, 1 / 99);
});
test("rejects viewport mismatch instead of resizing the reference", () => {
  assert.throws(
    () =>
      compareScreenshots(
        new PNG({ width: 10, height: 10 }),
        new PNG({ width: 11, height: 10 }),
      ),
    /dimensions differ/,
  );
});
test("rejects unjustified masks and fully hidden screenshots", () => {
  const image = new PNG({ width: 10, height: 10 });
  assert.throws(
    () =>
      compareScreenshots(image, image, [{ x: 0, y: 0, width: 1, height: 1 }]),
    /reason/,
  );
  assert.throws(
    () =>
      compareScreenshots(image, image, [
        { x: 0, y: 0, width: 10, height: 10, reason: "invalid blanket mask" },
      ]),
    /entire screenshot/,
  );
});
