import { describe, expect, it } from "vitest";
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
  it("uses zh-CN for Chinese text regardless of navigator", () => {
    expect(detectSpeechLocale("你好世界")).toBe("zh-CN");
  });
});

describe("hasBrowserVoiceForText", () => {
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

  it("keeps sentence punctuation and drops the space after it", () => {
    const first = `${"甲".repeat(20)}。`;
    const second = `${"乙".repeat(20)}！`;
    const text = `${first} ${second}`;
    const expected = text
      .split(/(?<=[。！？.!?])\s*/)
      .map((part) => part.trim())
      .filter(Boolean);
    expect(chunkTextForSpeech(text, 30)).toEqual(expected);
    expect(expected).toEqual([first, second]);
  });
});
