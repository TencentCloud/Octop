import { useCallback, useRef, useState } from "react";
import { message as antMessage } from "antd";
import { useTranslation } from "react-i18next";
import { voiceApi, type ActiveVoice } from "../api/modules/voice";
import { cachedActiveVoice, fetchActiveVoice } from "./useVoiceConfig";

interface BrowserSpeechRecognitionResultEvent {
  results: ArrayLike<{ [index: number]: { transcript?: string } }>;
}

interface BrowserSpeechRecognition {
  lang: string;
  interimResults: boolean;
  maxAlternatives: number;
  onresult: ((event: BrowserSpeechRecognitionResultEvent) => void) | null;
  onerror: (() => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop?: () => void;
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

async function transcribeWithBrowser(language: string): Promise<string> {
  const Ctor = getSpeechRecognition();
  if (!Ctor) {
    throw new Error("SpeechRecognition not supported");
  }
  return new Promise((resolve, reject) => {
    const rec = new Ctor();
    let settled = false;
    let timer = 0;
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
    rec.interimResults = false;
    rec.maxAlternatives = 1;
    rec.onresult = (event) => {
      const text = event.results[0]?.[0]?.transcript?.trim() ?? "";
      settle(() => resolve(text));
    };
    rec.onerror = () => settle(() => reject(new Error("browser STT failed")));
    rec.onend = () => settle(() => resolve(""));
    timer = window.setTimeout(() => {
      try {
        rec.stop?.();
      } catch {
        // Browser implementations differ; the timeout still settles below.
      }
      settle(() => reject(new Error("browser STT timed out")));
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
  return browserSttAvailable(); // browser STT (Android Chrome only)
}

export function useVoiceInput(onText: (text: string) => void) {
  const { t } = useTranslation();
  const [recording, setRecording] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  const language = navigator.language || "zh-CN";

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
      let text = "";
      if (active.stt === "browser" && browserSttAvailable()) {
        text = await transcribeWithBrowser(language);
      } else {
        try {
          const result = await voiceApi.transcribe(blob, language);
          text = result.text?.trim() ?? "";
        } catch (err) {
          const msg = err instanceof Error ? err.message : "";
          if (msg.includes("VOICE_BROWSER_ONLY") || msg.includes("422")) {
            if (browserSttAvailable()) {
              text = await transcribeWithBrowser(language);
            } else {
              antMessage.error(t("voice.sttProviderRequired"));
              return;
            }
          } else {
            // Server STT failed — try browser fallback if available.
            if (browserSttAvailable()) {
              antMessage.warning(t("voice.sttFallback"));
              text = await transcribeWithBrowser(language);
            } else {
              throw err;
            }
          }
        }
      }
      if (text) onText(text);
      else antMessage.info(t("voice.sttEmpty"));
    } catch {
      antMessage.error(t("voice.sttFailed"));
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
