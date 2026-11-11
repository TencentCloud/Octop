import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { synthesize } = vi.hoisted(() => ({ synthesize: vi.fn() }));

vi.mock("../api/modules/voice", () => ({
  voiceApi: { synthesize, synthesizeStream: vi.fn() },
}));
vi.mock("./useVoiceConfig", () => ({
  cachedActiveVoice: () => null,
  fetchActiveVoice: vi.fn(),
}));
vi.mock("../utils/browserSpeech", () => ({
  speakBrowserText: vi.fn(),
  stopBrowserSpeech: vi.fn(),
}));
vi.mock("@/utils/antdMessage", () => ({
  message: { error: vi.fn(), warning: vi.fn(), info: vi.fn() },
}));

import { useVoiceOutput } from "./useVoiceOutput";

const ANDROID_UA =
  "Mozilla/5.0 (Linux; Android 15) AppleWebKit/537.36 Chrome/130.0 Mobile Safari/537.36";

describe("useVoiceOutput on mobile", () => {
  const playedVolumes: Array<{ src: string; volume: number }> = [];

  beforeEach(() => {
    playedVolumes.length = 0;
    vi.spyOn(navigator, "userAgent", "get").mockReturnValue(ANDROID_UA);
    vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(function (
      this: HTMLMediaElement,
    ) {
      playedVolumes.push({ src: this.src, volume: this.volume });
      return Promise.resolve();
    });
    vi.spyOn(HTMLMediaElement.prototype, "load").mockImplementation(() => {});
    vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
    URL.createObjectURL = vi.fn(() => "blob:speech");
    URL.revokeObjectURL = vi.fn();
    synthesize.mockResolvedValue(new Blob(["mp3"], { type: "audio/mpeg" }));
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("plays the speech at full volume after the quiet unlock clip", async () => {
    const { result } = renderHook(() => useVoiceOutput());

    await act(async () => {
      result.current.speak("msg-1", "你好，世界");
    });

    expect(playedVolumes).toHaveLength(2);
    expect(playedVolumes[0].src).toMatch(/^data:audio\/mp3/);
    expect(playedVolumes[1]).toEqual({ src: "blob:speech", volume: 1 });
  });
});
