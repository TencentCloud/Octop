import assert from "node:assert/strict";
import { test } from "node:test";

import { selectRelease, platformAssetKey, isValidAssetUrl } from "./update-coordinator";

const stable = {
  tag: "v1.0.2",
  releasesUrl: "https://github.com/x/releases",
  assets: {
    mac_arm: { name: "Octop.dmg", ext: "dmg", url: "https://download.octop.cloud/Octop-1.0.2-arm64.dmg" },
  },
};
const beta = {
  tag: "v1.0.3b1",
  releasesUrl: "https://github.com/x/releases",
  assets: {
    mac_arm: { name: "Octop.dmg", ext: "dmg", url: "https://download.octop.cloud/Octop-1.0.3b1-arm64.dmg" },
  },
};

test("platformAssetKey maps platform+arch", () => {
  assert.equal(platformAssetKey("darwin", "arm64"), "mac_arm");
  assert.equal(platformAssetKey("darwin", "x64"), "mac_intel");
  assert.equal(platformAssetKey("win32", "arm64"), "win_arm");
  assert.equal(platformAssetKey("win32", "x64"), "win_x64");
  assert.equal(platformAssetKey("linux", "x64"), null);
});

test("stableOnly ignores higher beta", () => {
  const sel = selectRelease(
    { client: { stable, beta } },
    "1.0.1",
    "mac_arm",
    true,
  );
  assert.equal(sel?.tag, "v1.0.2");
});

test("beta channel selected when stableOnly off and beta is newer", () => {
  const sel = selectRelease(
    { client: { stable, beta } },
    "1.0.2",
    "mac_arm",
    false,
  );
  assert.equal(sel?.tag, "v1.0.3b1");
});

test("installed beta higher than stable never downgrades", () => {
  const sel = selectRelease(
    { client: { stable, beta } },
    "1.0.3b1",
    "mac_arm",
    false,
  );
  assert.equal(sel, null);
});

test("missing platform asset yields no update", () => {
  const sel = selectRelease({ client: { stable } }, "1.0.1", "win_x64", true);
  assert.equal(sel, null);
});

test("non-download-host urls are rejected", () => {
  assert.equal(isValidAssetUrl("https://download.octop.cloud/a.dmg"), true);
  assert.equal(isValidAssetUrl("http://download.octop.cloud/a.dmg"), false);
  assert.equal(isValidAssetUrl("https://evil.example/a.dmg"), false);
});
