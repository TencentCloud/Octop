import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { PNG } from "pngjs";

/** Compare fixed-size RGBA screenshots. Masks require explicit reasons. */
export function compareScreenshots(reference, actual, masks = []) {
  if (reference.width !== actual.width || reference.height !== actual.height)
    throw new Error(
      "Screenshot dimensions differ; use the same CSS viewport and scale",
    );
  for (const mask of masks)
    if (
      !mask.reason?.trim() ||
      ![mask.x, mask.y, mask.width, mask.height].every(Number.isInteger) ||
      mask.x < 0 ||
      mask.y < 0 ||
      mask.width <= 0 ||
      mask.height <= 0 ||
      mask.x + mask.width > reference.width ||
      mask.y + mask.height > reference.height
    )
      throw new Error(
        "Each mask needs an in-bounds integer rectangle and a reason",
      );
  let comparedPixels = 0,
    changedPixels = 0,
    maskedPixels = 0;
  for (let y = 0; y < reference.height; y++) {
    for (let x = 0; x < reference.width; x++) {
      if (
        masks.some(
          (mask) =>
            x >= mask.x &&
            x < mask.x + mask.width &&
            y >= mask.y &&
            y < mask.y + mask.height,
        )
      ) {
        maskedPixels++;
        continue;
      }
      comparedPixels++;
      const offset = (y * reference.width + x) * 4;
      if (
        [0, 1, 2, 3].some(
          (channel) =>
            Math.abs(
              reference.data[offset + channel] - actual.data[offset + channel],
            ) > 10,
        )
      )
        changedPixels++;
    }
  }
  if (!comparedPixels)
    throw new Error("Masks cannot exclude the entire screenshot");
  return {
    width: reference.width,
    height: reference.height,
    comparedPixels,
    maskedPixels,
    changedPixels,
    changedRatio: changedPixels / comparedPixels,
  };
}

if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href
) {
  const [referencePath, actualPath, masksPath] = process.argv.slice(2);
  if (!referencePath || !actualPath)
    throw new Error(
      "Usage: node scripts/compare-workbuddy-screenshots.mjs reference.png actual.png [masks.json]",
    );
  const result = compareScreenshots(
    PNG.sync.read(fs.readFileSync(referencePath)),
    PNG.sync.read(fs.readFileSync(actualPath)),
    masksPath ? JSON.parse(fs.readFileSync(masksPath, "utf8")) : [],
  );
  console.log(
    JSON.stringify(
      { ...result, threshold: 0.01, passed: result.changedRatio <= 0.01 },
      null,
      2,
    ),
  );
  if (result.changedRatio > 0.01) process.exitCode = 1;
}
