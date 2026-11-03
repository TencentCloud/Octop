import assert from "node:assert/strict";
import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import {
  MAC_PRIVACY_USAGE_KEYS,
  infoPlistStrings,
  macPrivacyExtendInfo,
  macPrivacyUsage,
  writeMacPrivacyLocalizations,
} from "../mac-privacy-plist";

test("macOS 隐私用途说明覆盖桌面端会触发的系统权限", () => {
  assert.deepEqual(MAC_PRIVACY_USAGE_KEYS, [
    "NSMicrophoneUsageDescription",
    "NSSpeechRecognitionUsageDescription",
    "NSScreenCaptureUsageDescription",
    "NSLocalNetworkUsageDescription",
  ]);
  const extendInfo = macPrivacyExtendInfo();
  for (const key of MAC_PRIVACY_USAGE_KEYS) {
    assert.equal(extendInfo[key], macPrivacyUsage[key].en);
    assert.notEqual(macPrivacyUsage[key].zh, macPrivacyUsage[key].en);
    assert.match(infoPlistStrings("zh"), new RegExp(`"${key}" = "${macPrivacyUsage[key].zh}";`));
  }
});

test("打包资源目录写入中英文 InfoPlist.strings", () => {
  const resources = mkdtempSync(join(tmpdir(), "octop-privacy-"));
  writeMacPrivacyLocalizations(resources);
  const english = readFileSync(join(resources, "en.lproj", "InfoPlist.strings"));
  const chinese = readFileSync(join(resources, "zh-Hans.lproj", "InfoPlist.strings"));
  assert.equal(english.subarray(0, 2).toString("hex"), "fffe");
  assert.equal(chinese.subarray(0, 2).toString("hex"), "fffe");
  assert.match(english.toString("utf16le"), /NSMicrophoneUsageDescription/);
  assert.match(chinese.toString("utf16le"), /Octop 录制屏幕/);
});
