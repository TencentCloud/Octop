import { afterEach, describe, expect, it, vi } from "vitest";
import { chunkTextForSpeech } from "./browserSpeech";
import {
  detectSpeechLocale,
  hasBrowserVoiceForText,
  plainTextForSpeech,
  prepareSpeechText,
} from "./plainTextForSpeech";

describe("plainTextForSpeech", () => {
  it("strips code blocks and thinking tags", () => {
    const raw = [
      "<think>hidden thought</think>",
      "你好，这是正文。",
      "```python",
      "print('x')",
      "```",
    ].join("\n");
    expect(plainTextForSpeech(raw)).toBe("你好，这是正文。");
  });

  it("returns empty when only code remains", () => {
    expect(prepareSpeechText("```bash\nls\n```")).toBe("");
  });
});

describe("detectSpeechLocale", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it.each([
    "今日はいい天気です。",
    "日本語で説明してください。",
    "東京へ行きます。",
    "東京タワー",
  ])("uses ja-JP for Japanese text containing kanji and kana: %s", (text) => {
    expect(detectSpeechLocale(text)).toBe("ja-JP");
  });

  it.each(["こんにちは", "カタカナ"])(
    "uses ja-JP for kana-only text: %s",
    (text) => {
      expect(detectSpeechLocale(text)).toBe("ja-JP");
    },
  );

  it("uses ko-KR for Korean text", () => {
    expect(detectSpeechLocale("안녕하세요")).toBe("ko-KR");
  });

  it("falls back to the browser language for text without a matching script", () => {
    vi.stubGlobal("navigator", { language: "fr-FR" });
    expect(detectSpeechLocale("Bonjour")).toBe("fr-FR");
  });

  it("falls back to en-US when the browser language is empty", () => {
    vi.stubGlobal("navigator", { language: "" });
    expect(detectSpeechLocale("hello")).toBe("en-US");
  });

  it("uses zh-CN for Chinese text regardless of navigator", () => {
    expect(detectSpeechLocale("你好世界")).toBe("zh-CN");
  });
});

describe("hasBrowserVoiceForText", () => {
  it("matches a Japanese voice for text containing kanji and kana", () => {
    const japaneseVoices = [
      { lang: "ja-JP", name: "Japanese", localService: true },
    ] as SpeechSynthesisVoice[];
    const chineseVoices = [
      { lang: "zh-CN", name: "Chinese", localService: true },
    ] as SpeechSynthesisVoice[];
    expect(hasBrowserVoiceForText("今日はいい天気です。", japaneseVoices)).toBe(
      true,
    );
    expect(hasBrowserVoiceForText("今日はいい天気です。", chineseVoices)).toBe(
      false,
    );
  });

  it("requires a matching voice language", () => {
    const voices = [
      { lang: "en-US", name: "English", localService: true },
    ] as SpeechSynthesisVoice[];
    expect(hasBrowserVoiceForText("你好", voices)).toBe(false);
    expect(hasBrowserVoiceForText("hello", voices)).toBe(true);
  });
});

describe("chunkTextForSpeech", () => {
  it("keeps short text as one chunk", () => {
    expect(chunkTextForSpeech("短句。")).toEqual(["短句。"]);
  });

  it("splits long text into multiple chunks", () => {
    const long = "第一句很长。".repeat(20);
    const chunks = chunkTextForSpeech(long, 40);
    expect(chunks.length).toBeGreaterThan(1);
    expect(chunks.join("")).toContain("第一句很长");
  });
});
