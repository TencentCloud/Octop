import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

/**
 * Usage strings merged into the packaged app's Info.plist.
 *
 * macOS reads these when the desktop app (or a child it is responsible for)
 * touches a protected resource. A missing string makes the call fail; for the
 * microphone and speech recognition the system can terminate the process.
 * English is the Info.plist fallback (development region). zh-Hans is written
 * to InfoPlist.strings so a Chinese system shows Chinese.
 *
 * Accessibility and Input Monitoring have no usage-description key. Those
 * toggles only appear in System Settings.
 */
export const MAC_PRIVACY_USAGE_KEYS = [
  "NSMicrophoneUsageDescription",
  "NSSpeechRecognitionUsageDescription",
  "NSScreenCaptureUsageDescription",
  "NSLocalNetworkUsageDescription",
] as const;

export type MacPrivacyUsageKey = (typeof MAC_PRIVACY_USAGE_KEYS)[number];

export const macPrivacyUsage: Record<MacPrivacyUsageKey, { readonly en: string; readonly zh: string }> =
  {
    NSMicrophoneUsageDescription: {
      en: "Octop uses the microphone to turn your speech into text.",
      zh: "Octop 使用麦克风，把你说的话转成文字。",
    },
    NSSpeechRecognitionUsageDescription: {
      en: "Octop uses speech recognition to transcribe what you say.",
      zh: "Octop 使用语音识别，把你说的话转成文字。",
    },
    NSScreenCaptureUsageDescription: {
      en: "Octop records the screen so it can show and control this computer's desktop.",
      zh: "Octop 录制屏幕，以便显示并操控这台电脑的桌面。",
    },
    NSLocalNetworkUsageDescription: {
      en: "Octop connects to services on your local network, such as a local model or a device you control.",
      zh: "Octop 连接本地网络上的服务，例如本地模型或你控制的设备。",
    },
  };

export function macPrivacyExtendInfo(): Record<MacPrivacyUsageKey, string> {
  const info = {} as Record<MacPrivacyUsageKey, string>;
  for (const key of MAC_PRIVACY_USAGE_KEYS) info[key] = macPrivacyUsage[key].en;
  return info;
}

export function infoPlistStrings(locale: "en" | "zh"): string {
  return MAC_PRIVACY_USAGE_KEYS.map((key) => {
    const value = macPrivacyUsage[key][locale].replace(/\\/g, "\\\\").replace(/"/g, '\\"');
    return `"${key}" = "${value}";\n`;
  }).join("");
}

const PRIVACY_LPROJ: ReadonlyArray<readonly [folder: string, locale: "en" | "zh"]> = [
  ["en.lproj", "en"],
  ["zh-Hans.lproj", "zh"],
];

/** Write InfoPlist.strings next to Electron's locale packs. UTF-16 LE with BOM, as Xcode emits. */
export function writeMacPrivacyLocalizations(resourcesDir: string): void {
  for (const [folder, locale] of PRIVACY_LPROJ) {
    const dir = join(resourcesDir, folder);
    mkdirSync(dir, { recursive: true });
    const body = `\uFEFF${infoPlistStrings(locale)}`;
    writeFileSync(join(dir, "InfoPlist.strings"), Buffer.from(body, "utf16le"));
  }
}
