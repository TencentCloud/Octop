import { useCallback, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { voiceApi, type ActiveVoice } from "../api/modules/voice";
import { speechLocaleFromUi } from "../utils/localePrefs";
import { cachedActiveVoice, fetchActiveVoice } from "./useVoiceConfig";

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
        if (!text && lastError && lastError !== "no-speech" && lastError !== "aborted") {
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

export function useVoiceInput(onText: (text: string) => void) {
  const { t, i18n } = useTranslation();
  const [recording, setRecording] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  // Follow dashboard UI locale — not navigator.language (often en-US on
  // machines used with Chinese UI / Chinese speech).
  const language = speechLocaleFromUi(i18n.language);

  const stopRecording = useCallback(async () => {
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
      const result = await voiceApi.transcribe(blob, language);
      const text = result.text?.trim() ?? "";
      if (text) onText(text);
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
  }, [onText, t, language]);

  const startRecording = useCallback(async () => {
    // Read cached config synchronously to stay in the user-gesture stack.
    const active: ActiveVoice | null = cachedActiveVoice();

    if ((active?.stt ?? "browser") === "browser" && browserSttAvailable()) {
      // Browser STT: use the native SpeechRecognition API directly.
      setTranscribing(true);
      try {
        const text = await transcribeWithBrowser(language);
        if (text) onText(text);
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
  }, [onText, t, language]);

  const toggle = useCallback(() => {
    if (transcribing) return;
    if (recording) void stopRecording();
    else void startRecording();
  }, [recording, transcribing, startRecording, stopRecording]);

  return { recording, transcribing, toggle };
}
