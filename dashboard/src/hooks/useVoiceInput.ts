import { useCallback, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { getWsUrl } from "../api/config";
import { voiceApi, type ActiveVoice } from "../api/modules/voice";
import { getAuthToken } from "../api/request";
import { speechLocaleFromUi } from "../utils/localePrefs";
import { PcmFrameBuffer, downsampleToPcm16 } from "../utils/pcmCapture";
import { RealtimeSttClient } from "../utils/realtimeStt";
import {
  cachedActiveVoice,
  fetchActiveVoice,
  useVoiceConfig,
} from "./useVoiceConfig";

import { message as antMessage } from "@/utils/antdMessage";

interface BrowserSpeechRecognitionAlternative {
  transcript?: string;
}

interface BrowserSpeechRecognitionResult {
  isFinal: boolean;
  length: number;
  [index: number]: BrowserSpeechRecognitionAlternative;
}

interface BrowserSpeechRecognitionResultEvent {
  resultIndex: number;
  results: ArrayLike<BrowserSpeechRecognitionResult> & { length: number };
}

interface BrowserSpeechRecognitionErrorEvent {
  error?: string;
}

interface BrowserSpeechRecognition {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  onresult: ((event: BrowserSpeechRecognitionResultEvent) => void) | null;
  onerror: ((event: BrowserSpeechRecognitionErrorEvent) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop?: () => void;
  abort?: () => void;
}

type SpeechRecognitionCtor = new () => BrowserSpeechRecognition;
const BROWSER_STT_TIMEOUT_MS = 15000;

function getSpeechRecognition(): SpeechRecognitionCtor | null {
  const w = window as Window & {
    SpeechRecognition?: SpeechRecognitionCtor;
    webkitSpeechRecognition?: SpeechRecognitionCtor;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

function browserSttAvailable(): boolean {
  return getSpeechRecognition() !== null;
}

const WAV_SAMPLE_RATE = 16000;

/**
 * Re-encode a recorded blob as 16kHz mono PCM16 WAV.
 *
 * Server STT providers reject browser recording containers (e.g. Tencent ASR
 * does not accept webm). Decoding via Web Audio and uploading plain WAV works
 * for every provider. Falls back to the original blob when the browser cannot
 * decode it.
 */
async function recordedBlobToWav(blob: Blob): Promise<Blob> {
  const Ctor =
    window.AudioContext ??
    (window as Window & { webkitAudioContext?: typeof AudioContext })
      .webkitAudioContext;
  if (!Ctor) return blob;
  const ctx = new Ctor();
  try {
    const decoded = await ctx.decodeAudioData(await blob.arrayBuffer());
    const length = Math.max(1, Math.round(decoded.duration * WAV_SAMPLE_RATE));
    const offline = new OfflineAudioContext(1, length, WAV_SAMPLE_RATE);
    const source = offline.createBufferSource();
    source.buffer = decoded;
    source.connect(offline.destination);
    source.start();
    const rendered = await offline.startRendering();
    const samples = rendered.getChannelData(0);
    const pcm = new Int16Array(samples.length);
    for (let i = 0; i < samples.length; i += 1) {
      const s = Math.max(-1, Math.min(1, samples[i]));
      pcm[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
    }
    const header = new ArrayBuffer(44);
    const view = new DataView(header);
    const writeStr = (offset: number, text: string) => {
      for (let i = 0; i < text.length; i += 1) {
        view.setUint8(offset + i, text.charCodeAt(i));
      }
    };
    writeStr(0, "RIFF");
    view.setUint32(4, 36 + pcm.byteLength, true);
    writeStr(8, "WAVE");
    writeStr(12, "fmt ");
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true); // PCM
    view.setUint16(22, 1, true); // mono
    view.setUint32(24, WAV_SAMPLE_RATE, true);
    view.setUint32(28, WAV_SAMPLE_RATE * 2, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    writeStr(36, "data");
    view.setUint32(40, pcm.byteLength, true);
    return new Blob([header, pcm.buffer], { type: "audio/wav" });
  } catch {
    return blob;
  } finally {
    void ctx.close();
  }
}

/** Pick the best MIME type supported by the current browser for recording. */
function pickRecorderMimeType(): string {
  const types = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/mp4",
    "audio/ogg",
  ];
  for (const t of types) {
    if (MediaRecorder.isTypeSupported(t)) return t;
  }
  return "";
}

/**
 * Native Web Speech API transcription.
 *
 * Important: settle only on `onend` / error / timeout. Resolving in `onresult`
 * races Chrome's `onend` and often yields empty text for Chinese utterances.
 */
async function transcribeWithBrowser(language: string): Promise<string> {
  const Ctor = getSpeechRecognition();
  if (!Ctor) {
    throw new Error("SpeechRecognition not supported");
  }
  return new Promise((resolve, reject) => {
    const rec = new Ctor();
    let settled = false;
    let finalText = "";
    let interimText = "";
    let timer = 0;
    let lastError: string | undefined;

    const settle = (fn: () => void) => {
      if (settled) return;
      settled = true;
      if (timer) window.clearTimeout(timer);
      rec.onresult = null;
      rec.onerror = null;
      rec.onend = null;
      fn();
    };

    rec.lang = language;
    rec.continuous = false;
    rec.interimResults = true;
    rec.maxAlternatives = 1;

    rec.onresult = (event) => {
      let finals = "";
      let interim = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        const piece = result?.[0]?.transcript ?? "";
        if (result?.isFinal) finals += piece;
        else interim += piece;
      }
      if (finals) finalText += finals;
      interimText = interim;
    };

    rec.onerror = (event) => {
      lastError = event.error;
      // no-speech / aborted: let onend resolve with whatever we have.
      if (event.error === "no-speech" || event.error === "aborted") return;
      settle(() => {
        if (event.error === "network") {
          reject(new Error("browser STT network"));
          return;
        }
        reject(new Error(`browser STT failed: ${event.error ?? "unknown"}`));
      });
    };

    rec.onend = () => {
      const text = (finalText || interimText).trim();
      settle(() => {
        if (
          !text &&
          lastError &&
          lastError !== "no-speech" &&
          lastError !== "aborted"
        ) {
          reject(new Error(`browser STT failed: ${lastError}`));
          return;
        }
        resolve(text);
      });
    };

    timer = window.setTimeout(() => {
      try {
        rec.stop?.();
      } catch {
        // Browser implementations differ; the timeout still settles below.
      }
      settle(() => {
        const text = (finalText || interimText).trim();
        if (text) resolve(text);
        else reject(new Error("browser STT timed out"));
      });
    }, BROWSER_STT_TIMEOUT_MS);

    try {
      rec.start();
    } catch (err) {
      settle(() =>
        reject(err instanceof Error ? err : new Error("browser STT failed")),
      );
    }
  });
}

/** Check whether the browser can record audio (requires secure context). */
export function canRecordAudio(): boolean {
  return !!navigator.mediaDevices?.getUserMedia && "MediaRecorder" in window;
}

/** Check whether any STT method is available. */
export function isSttAvailable(): boolean {
  if (canRecordAudio()) return true; // server STT via MediaRecorder
  return browserSttAvailable(); // browser STT (Chrome / Edge)
}

export interface VoiceInputOptions {
  /** Called when a capture session starts, before any transcript arrives. */
  onStart?: () => void;
  /** Cumulative transcript while the session is still being refined. */
  onInterim?: (text: string) => void;
  /** Cumulative transcript of the session; the realtime path calls it per sentence. */
  onText: (text: string) => void;
}

/** Live 16 kHz capture feeding the realtime STT WebSocket. */
interface RealtimeCapture {
  client: RealtimeSttClient;
  stream: MediaStream;
  ctx: AudioContext;
  source: MediaStreamAudioSourceNode;
  processor: ScriptProcessorNode;
  sink: GainNode;
}

function realtimeSttUrl(language: string): string {
  const params = new URLSearchParams({
    locale: language.toLowerCase().startsWith("zh") ? "zh" : "en",
  });
  const token = getAuthToken();
  if (token) params.set("token", token);
  return `${getWsUrl("/voice/stt-stream")}?${params.toString()}`;
}

function audioContextCtor(): typeof AudioContext | null {
  return (
    window.AudioContext ??
    (window as Window & { webkitAudioContext?: typeof AudioContext })
      .webkitAudioContext ??
    null
  );
}

export function useVoiceInput(options: VoiceInputOptions) {
  const { t, i18n } = useTranslation();
  const [recording, setRecording] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const captureRef = useRef<RealtimeCapture | null>(null);
  // A press-and-hold release can land while `startRealtime` is still awaiting
  // getUserMedia; remember it so the capture is not left running.
  const pendingStopRef = useRef(false);
  // Keep the latest callbacks without rebuilding every capture closure.
  const optionsRef = useRef(options);
  optionsRef.current = options;
  const { active } = useVoiceConfig();

  // Follow dashboard UI locale — not navigator.language (often en-US on
  // machines used with Chinese UI / Chinese speech).
  const language = speechLocaleFromUi(i18n.language);

  const teardownRealtime = useCallback(() => {
    const capture = captureRef.current;
    captureRef.current = null;
    if (!capture) return;
    capture.processor.onaudioprocess = null;
    capture.processor.disconnect();
    capture.source.disconnect();
    capture.sink.disconnect();
    capture.stream.getTracks().forEach((track) => track.stop());
    void capture.ctx.close();
  }, []);

  const finishRealtime = useCallback(() => {
    teardownRealtime();
    setRecording(false);
    setTranscribing(false);
  }, [teardownRealtime]);

  const startRealtime = useCallback(async () => {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
      },
    });
    const Ctor = audioContextCtor();
    if (!Ctor) throw new Error("AudioContext unavailable");
    const ctx = new Ctor();
    const source = ctx.createMediaStreamSource(stream);
    const processor = ctx.createScriptProcessor(1024, 1, 1);
    const sink = ctx.createGain();
    sink.gain.value = 0; // keep the graph running without echoing the mic

    const client = new RealtimeSttClient(realtimeSttUrl(language), {
      onInterim: (text) => optionsRef.current.onInterim?.(text),
      onFinal: (text) => {
        if (text) optionsRef.current.onText(text);
      },
      onDone: finishRealtime,
      onError: (message) => {
        finishRealtime();
        antMessage.error(message || t("voice.realtimeFailed"));
      },
    });

    captureRef.current = { client, stream, ctx, source, processor, sink };
    const frames = new PcmFrameBuffer();
    processor.onaudioprocess = (event) => {
      const pcm = downsampleToPcm16(
        event.inputBuffer.getChannelData(0),
        ctx.sampleRate,
      );
      for (const frame of frames.push(pcm)) client.send(frame);
    };
    source.connect(processor);
    processor.connect(sink);
    sink.connect(ctx.destination);

    // Frames are buffered until the server reports ready; failures surface
    // through `onError`, so the connect rejection needs no extra handling.
    void client.connect().catch(() => undefined);
    setRecording(true);
  }, [finishRealtime, language, t]);

  const stopRealtime = useCallback(() => {
    const capture = captureRef.current;
    if (!capture) return;
    capture.processor.onaudioprocess = null;
    capture.processor.disconnect();
    capture.source.disconnect();
    capture.sink.disconnect();
    capture.stream.getTracks().forEach((track) => track.stop());
    setRecording(false);
    setTranscribing(true);
    // `end` makes the server flush its final sentences, then `onDone` clears.
    capture.client.end();
  }, []);

  const stopRecording = useCallback(async () => {
    pendingStopRef.current = true;
    if (captureRef.current) {
      stopRealtime();
      return;
    }
    const recorder = mediaRecorderRef.current;
    if (!recorder || recorder.state === "inactive") {
      setRecording(false);
      return;
    }
    await new Promise<void>((resolve) => {
      recorder.onstop = () => resolve();
      recorder.stop();
    });
    mediaRecorderRef.current = null;
    setRecording(false);

    const blob = new Blob(chunksRef.current, {
      type: chunksRef.current[0]?.type || "audio/webm",
    });
    chunksRef.current = [];
    if (!blob.size) return;

    setTranscribing(true);
    try {
      const active = await fetchActiveVoice();
      // SpeechRecognition cannot consume a recorded blob. If STT is still
      // "browser", ask the user to configure a server provider (or use the
      // click-to-talk browser path from a cold start).
      if (active.stt === "browser") {
        antMessage.error(t("voice.sttProviderRequired"));
        return;
      }
      const upload = await recordedBlobToWav(blob);
      const result = await voiceApi.transcribe(upload, language);
      const text = result.text?.trim() ?? "";
      if (text) optionsRef.current.onText(text);
      else antMessage.info(t("voice.sttEmpty"));
    } catch (err) {
      const msg = err instanceof Error ? err.message : "";
      if (msg.includes("VOICE_BROWSER_ONLY") || msg.includes("422")) {
        antMessage.error(t("voice.sttProviderRequired"));
      } else {
        antMessage.error(t("voice.sttFailed"));
      }
    } finally {
      setTranscribing(false);
    }
  }, [t, language, stopRealtime]);

  const startRecording = useCallback(async () => {
    // Read cached config synchronously to stay in the user-gesture stack.
    const active: ActiveVoice | null = cachedActiveVoice();
    pendingStopRef.current = false;
    optionsRef.current.onStart?.();

    if (active?.stt_realtime && canRecordAudio() && audioContextCtor()) {
      // Realtime STT: stream PCM and let results arrive while speaking.
      try {
        await startRealtime();
      } catch {
        antMessage.error(t("voice.micDenied"));
        return;
      }
      if (pendingStopRef.current) stopRealtime();
      return;
    }

    if ((active?.stt ?? "browser") === "browser" && browserSttAvailable()) {
      // Browser STT: use the native SpeechRecognition API directly.
      setTranscribing(true);
      try {
        const text = await transcribeWithBrowser(language);
        if (text) optionsRef.current.onText(text);
        else antMessage.info(t("voice.sttEmpty"));
      } catch (err) {
        const msg = err instanceof Error ? err.message : "";
        if (msg.includes("network")) {
          antMessage.error(t("voice.sttNetworkFailed"));
        } else {
          antMessage.error(t("voice.sttFailed"));
        }
      } finally {
        setTranscribing(false);
      }
      return;
    }

    // Server STT: record audio via MediaRecorder, then transcribe.
    if (!canRecordAudio()) {
      antMessage.error(t("voice.micNotAvailable"));
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = pickRecorderMimeType();
      const recorder = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      recorder.onstop = () => {
        stream.getTracks().forEach((track) => track.stop());
      };
      mediaRecorderRef.current = recorder;
      recorder.start();
      setRecording(true);
    } catch {
      antMessage.error(t("voice.micDenied"));
    }
  }, [t, language, startRealtime, stopRealtime]);

  const toggle = useCallback(() => {
    if (transcribing) return;
    if (recording) void stopRecording();
    else void startRecording();
  }, [recording, transcribing, startRecording, stopRecording]);

  return {
    recording,
    transcribing,
    /** True when the mic streams results live (press and hold, not click). */
    realtime: active.stt_realtime === true,
    start: startRecording,
    stop: stopRecording,
    toggle,
  };
}
