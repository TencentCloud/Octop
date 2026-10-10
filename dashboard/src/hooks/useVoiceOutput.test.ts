import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { voiceApi } from "../api/modules/voice";
import { cachedActiveVoice, fetchActiveVoice } from "./useVoiceConfig";
import { isMobileUserAgent } from "../utils/mobileDevice";
import { speakBrowserText } from "../utils/browserSpeech";
import { message } from "@/utils/antdMessage";
import { useVoiceOutput } from "./useVoiceOutput";

const { player, audio, createObjectURL, revokeObjectURL } = vi.hoisted(() => ({
  player: {
    ensureContext: vi.fn(),
    push: vi.fn(),
    stop: vi.fn(),
    msRemaining: vi.fn(),
    hasAudio: true,
  },
  audio: {
    src: "",
    onended: null as (() => void) | null,
    onerror: null as (() => void) | null,
    load: vi.fn(),
    play: vi.fn(),
    pause: vi.fn(),
    removeAttribute: vi.fn(),
  },
  createObjectURL: vi.fn(),
  revokeObjectURL: vi.fn(),
}));

vi.mock("../api/modules/voice", () => ({
  voiceApi: { synthesizeStream: vi.fn(), synthesize: vi.fn() },
}));
vi.mock("./useVoiceConfig", () => ({
  cachedActiveVoice: vi.fn(),
  fetchActiveVoice: vi.fn(),
}));
vi.mock("./useAudioUnlock", () => ({
  ensureAudioUnlocked: vi.fn(),
  isAutoplayBlockedError: vi.fn().mockReturnValue(false),
  primeAudioElement: vi.fn(),
}));
vi.mock("../utils/browserSpeech", () => ({
  speakBrowserText: vi.fn(),
  stopBrowserSpeech: vi.fn(),
}));
vi.mock("../utils/mobileDevice", () => ({ isMobileUserAgent: vi.fn() }));
vi.mock("../utils/wavStreamPlayer", () => ({
  WavStreamPlayer: vi.fn(function () {
    return player;
  }),
}));
vi.mock("@/utils/antdMessage", () => ({
  message: { error: vi.fn(), warning: vi.fn(), info: vi.fn() },
}));

function stream(chunks: Uint8Array[]): ReadableStream<Uint8Array> {
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(chunk);
      controller.close();
    },
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(cachedActiveVoice).mockReturnValue({
    stt: "browser",
    tts: "My Qwen",
  });
  vi.mocked(isMobileUserAgent).mockReturnValue(false);
  player.ensureContext.mockReturnValue(true);
  player.push.mockReturnValue(true);
  player.msRemaining.mockReturnValue(0);
  player.hasAudio = true;
  audio.play.mockResolvedValue(undefined);
  audio.onended = null;
  audio.onerror = null;
  createObjectURL.mockReturnValue("blob:voice");
  vi.stubGlobal(
    "Audio",
    vi.fn(function () {
      return audio;
    }),
  );
  const NativeURL = globalThis.URL;
  vi.stubGlobal(
    "URL",
    class extends NativeURL {
      static createObjectURL = createObjectURL;
      static revokeObjectURL = revokeObjectURL;
    },
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("useVoiceOutput server playback", () => {
  it("streams WAV from a custom provider and buffers a fragmented header", async () => {
    const first = new Uint8Array(20);
    const second = new Uint8Array(24);
    const pcm = new Uint8Array([1, 2, 3, 4]);
    vi.mocked(voiceApi.synthesizeStream).mockResolvedValue({
      contentType: "Audio/WAV; charset=binary",
      body: stream([first, second, pcm]),
    });
    const hook = renderHook(() => useVoiceOutput());
    act(() => hook.result.current.speak("message-1", "Hello"));

    await waitFor(() => expect(player.push).toHaveBeenCalledTimes(2));
    expect(player.push.mock.calls[0][0]).toHaveLength(44);
    expect(player.push.mock.calls[1][0]).toEqual(pcm);
    expect(voiceApi.synthesizeStream).toHaveBeenCalledWith("Hello", undefined);
    expect(voiceApi.synthesize).not.toHaveBeenCalled();
    expect(audio.play).not.toHaveBeenCalled();
  });

  it("buffers MP3 from the same response without requesting synthesis twice", async () => {
    vi.mocked(voiceApi.synthesizeStream).mockResolvedValue({
      contentType: "audio/mpeg",
      body: stream([new Uint8Array([1, 2, 3])]),
    });
    const hook = renderHook(() => useVoiceOutput());
    act(() => hook.result.current.speak("message-1", "Hello"));

    await waitFor(() => expect(audio.play).toHaveBeenCalledOnce());
    expect(createObjectURL.mock.calls[0][0]).toMatchObject({
      type: "audio/mpeg",
      size: 3,
    });
    expect(voiceApi.synthesizeStream).toHaveBeenCalledOnce();
    expect(voiceApi.synthesize).not.toHaveBeenCalled();
    expect(player.push).not.toHaveBeenCalled();
    expect(player.stop).toHaveBeenCalled();
  });

  it("buffers the unread WAV response when WebAudio is unavailable", async () => {
    player.ensureContext.mockReturnValue(false);
    vi.mocked(voiceApi.synthesizeStream).mockResolvedValue({
      contentType: "audio/wav",
      body: stream([new Uint8Array(48)]),
    });
    const hook = renderHook(() => useVoiceOutput());
    act(() => hook.result.current.speak("message-1", "Hello"));

    await waitFor(() => expect(audio.play).toHaveBeenCalledOnce());
    expect(createObjectURL.mock.calls[0][0]).toMatchObject({
      type: "audio/wav",
      size: 48,
    });
    expect(voiceApi.synthesizeStream).toHaveBeenCalledOnce();
    expect(voiceApi.synthesize).not.toHaveBeenCalled();
  });

  it("passes the Edge provider override through browser speech fallback", async () => {
    vi.mocked(cachedActiveVoice).mockReturnValue({
      stt: "browser",
      tts: "browser",
    });
    vi.mocked(speakBrowserText).mockImplementation((_, options) => {
      options.onNoVoice?.();
    });
    vi.mocked(voiceApi.synthesizeStream).mockResolvedValue({
      contentType: "audio/mpeg",
      body: stream([new Uint8Array([1, 2])]),
    });
    const hook = renderHook(() => useVoiceOutput());
    act(() => hook.result.current.speak("message-1", "Hello"));

    await waitFor(() => expect(audio.play).toHaveBeenCalled());
    expect(voiceApi.synthesizeStream).toHaveBeenCalledWith("Hello", "edge");
    expect(voiceApi.synthesize).not.toHaveBeenCalled();
  });

  it("honors a custom provider on mobile and prepares WebAudio during the tap", async () => {
    vi.mocked(isMobileUserAgent).mockReturnValue(true);
    vi.mocked(voiceApi.synthesizeStream).mockResolvedValue({
      contentType: "audio/wav",
      body: stream([new Uint8Array(48)]),
    });
    const hook = renderHook(() => useVoiceOutput());
    act(() => hook.result.current.speak("message-1", "Hello"));

    expect(player.ensureContext).toHaveBeenCalledOnce();
    expect(player.ensureContext.mock.invocationCallOrder[0]).toBeLessThan(
      vi.mocked(voiceApi.synthesizeStream).mock.invocationCallOrder[0],
    );
    await waitFor(() => expect(player.push).toHaveBeenCalled());
    expect(voiceApi.synthesizeStream).toHaveBeenCalledWith("Hello", undefined);
    expect(speakBrowserText).not.toHaveBeenCalled();
    expect(audio.play).not.toHaveBeenCalled();
  });

  it("fetches the selected mobile provider when the voice cache is empty", async () => {
    vi.mocked(isMobileUserAgent).mockReturnValue(true);
    vi.mocked(cachedActiveVoice).mockReturnValue(null);
    vi.mocked(fetchActiveVoice).mockResolvedValue({
      stt: "browser",
      tts: "My Qwen",
    });
    vi.mocked(voiceApi.synthesizeStream).mockResolvedValue({
      contentType: "audio/wav",
      body: stream([new Uint8Array(48)]),
    });
    const hook = renderHook(() => useVoiceOutput());
    act(() => hook.result.current.speak("message-1", "Hello"));

    await waitFor(() => expect(player.push).toHaveBeenCalled());
    expect(fetchActiveVoice).toHaveBeenCalledOnce();
    expect(voiceApi.synthesizeStream).toHaveBeenCalledWith("Hello", undefined);
    expect(speakBrowserText).not.toHaveBeenCalled();
  });

  it("reports malformed WAV without retrying a billable synthesis request", async () => {
    player.push.mockReturnValue(false);
    vi.mocked(voiceApi.synthesizeStream).mockResolvedValue({
      contentType: "audio/wav",
      body: stream([new Uint8Array(48)]),
    });
    const hook = renderHook(() => useVoiceOutput());
    act(() => hook.result.current.speak("message-1", "Hello"));

    await waitFor(() =>
      expect(message.error).toHaveBeenCalledWith("voice.ttsFailed"),
    );
    expect(hook.result.current.speakingId).toBeNull();
    expect(voiceApi.synthesizeStream).toHaveBeenCalledOnce();
    expect(voiceApi.synthesize).not.toHaveBeenCalled();
    expect(player.stop).toHaveBeenCalled();
  });

  it("reports a stream read failure and clears speaking state without retrying", async () => {
    let controller!: ReadableStreamDefaultController<Uint8Array>;
    const body = new ReadableStream<Uint8Array>({
      start(value) {
        controller = value;
      },
    });
    vi.mocked(voiceApi.synthesizeStream).mockResolvedValue({
      contentType: "audio/wav",
      body,
    });
    const hook = renderHook(() => useVoiceOutput());
    act(() => hook.result.current.speak("message-1", "Hello"));
    controller.enqueue(new Uint8Array(48));
    await waitFor(() => expect(player.push).toHaveBeenCalled());
    controller.error(new Error("Connection lost"));

    await waitFor(() =>
      expect(message.error).toHaveBeenCalledWith("voice.ttsFailed"),
    );
    expect(hook.result.current.speakingId).toBeNull();
    expect(voiceApi.synthesizeStream).toHaveBeenCalledOnce();
    expect(voiceApi.synthesize).not.toHaveBeenCalled();
  });

  it("cancels a pending WAV body when playback is stopped", async () => {
    const cancel = vi.fn();
    let controller!: ReadableStreamDefaultController<Uint8Array>;
    const body = new ReadableStream<Uint8Array>({
      start(value) {
        controller = value;
      },
      cancel,
    });
    vi.mocked(voiceApi.synthesizeStream).mockResolvedValue({
      contentType: "audio/wav",
      body,
    });
    const hook = renderHook(() => useVoiceOutput());
    act(() => hook.result.current.speak("message-1", "Hello"));
    controller.enqueue(new Uint8Array(48));
    await waitFor(() => expect(player.push).toHaveBeenCalled());
    act(() => hook.result.current.stop());

    await waitFor(() => expect(cancel).toHaveBeenCalledOnce());
    expect(hook.result.current.speakingId).toBeNull();
    expect(message.error).not.toHaveBeenCalled();
    expect(voiceApi.synthesizeStream).toHaveBeenCalledOnce();
  });
});
