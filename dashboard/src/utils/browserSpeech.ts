/**
 * Chrome-safe wrapper around window.speechSynthesis.
 */

import {
  detectSpeechLocale,
  hasBrowserVoiceForText,
} from "./plainTextForSpeech";

const CANCEL_TO_SPEAK_MS = 280;
const CHUNK_MAX_LEN = 120;
const CHUNK_GAP_MS = 120;
const KEEPALIVE_MS = 10_000;

type SpeechError = SpeechSynthesisErrorEvent["error"];

export interface SpeakBrowserCallbacks {
  onDone: () => void;
  /** Chrome has no voice for this language (common on Linux with zh content). */
  onNoVoice?: () => void;
}

interface SpeechRuntime {
  session: number;
  pendingTimer: number | null;
  keepAliveTimer: number | null;
  needsSpeakDelay: boolean;
}

function runtime(): SpeechRuntime {
  const w = window as Window & { __octopSpeech?: SpeechRuntime };
  if (!w.__octopSpeech) {
    w.__octopSpeech = {
      session: 0,
      pendingTimer: null,
      keepAliveTimer: null,
      needsSpeakDelay: false,
    };
  }
  return w.__octopSpeech;
}

function clearTimer(id: number | null): void {
  if (id !== null) clearTimeout(id);
}

function clearKeepAlive(rt: SpeechRuntime): void {
  if (rt.keepAliveTimer !== null) {
    clearInterval(rt.keepAliveTimer);
    rt.keepAliveTimer = null;
  }
}

function clearPending(rt: SpeechRuntime): void {
  clearTimer(rt.pendingTimer);
  rt.pendingTimer = null;
}

function waitForVoices(): Promise<SpeechSynthesisVoice[]> {
  return new Promise((resolve) => {
    let settled = false;
    const finish = () => {
      if (settled) return;
      settled = true;
      window.speechSynthesis.onvoiceschanged = null;
      resolve(window.speechSynthesis.getVoices());
    };

    const voices = window.speechSynthesis.getVoices();
    if (voices.length > 0) {
      finish();
      return;
    }

    window.speechSynthesis.onvoiceschanged = finish;
    window.setTimeout(finish, 800);
  });
}

function pickVoiceForLocale(
  locale: string,
  voices: SpeechSynthesisVoice[],
): SpeechSynthesisVoice | undefined {
  const norm = locale.replace("_", "-").toLowerCase();
  const prefix = norm.split("-")[0];

  const matches = voices.filter((v) => {
    const vl = v.lang.replace("_", "-").toLowerCase();
    return vl.startsWith(norm) || vl.startsWith(prefix);
  });

  if (matches.length === 0) return undefined;

  return (
    matches.find((v) => v.localService) ??
    matches.find((v) =>
      /huihui|xiaoxiao|tingting|yaoyao|kangkang|mandarin|chinese|中文|普通话/i.test(
        v.name,
      ),
    ) ??
    matches.find((v) => !/google/i.test(v.name)) ??
    matches[0]
  );
}

const SENTENCE_ENDERS = "。！？.!?";

/**
 * Split after sentence enders, dropping the following whitespace.
 * A lookbehind would do this, but Safari before 16.4 cannot compile it.
 */
function splitKeepingSentenceEnd(text: string): string[] {
  const parts: string[] = [];
  let start = 0;
  for (let i = 0; i < text.length; i += 1) {
    const ch = text.charAt(i);
    if (!SENTENCE_ENDERS.includes(ch)) continue;
    parts.push(text.slice(start, i + 1));
    let next = i + 1;
    while (next < text.length && /\s/.test(text.charAt(next))) next += 1;
    start = next;
    i = next - 1;
  }
  if (start < text.length) parts.push(text.slice(start));
  return parts;
}

export function chunkTextForSpeech(
  text: string,
  maxLen = CHUNK_MAX_LEN,
): string[] {
  const trimmed = text.trim();
  if (!trimmed) return [];
  if (trimmed.length <= maxLen) return [trimmed];

  const sentences = splitKeepingSentenceEnd(trimmed)
    .map((s) => s.trim())
    .filter(Boolean);
  const parts = sentences.length > 0 ? sentences : [trimmed];

  const chunks: string[] = [];
  let buf = "";

  const flush = () => {
    const next = buf.trim();
    if (next.length >= 2) chunks.push(next);
    buf = "";
  };

  for (const sentence of parts) {
    if (sentence.length > maxLen) {
      flush();
      for (let i = 0; i < sentence.length; i += maxLen) {
        const slice = sentence.slice(i, i + maxLen).trim();
        if (slice.length >= 2) chunks.push(slice);
      }
      continue;
    }

    if (!buf) {
      buf = sentence;
    } else if (buf.length + sentence.length <= maxLen) {
      buf += sentence;
    } else {
      flush();
      buf = sentence;
    }
  }

  flush();
  return chunks.length > 0 ? chunks : [trimmed.slice(0, maxLen)];
}

export function stopBrowserSpeech(): number {
  const rt = runtime();
  rt.session += 1;
  rt.needsSpeakDelay = true;
  clearPending(rt);
  clearKeepAlive(rt);
  window.speechSynthesis.cancel();
  return rt.session;
}

function isBenignSpeechError(error: SpeechError | undefined): boolean {
  return error === "interrupted" || error === "canceled";
}

function scheduleSpeak(
  rt: SpeechRuntime,
  session: number,
  delayMs: number,
  fn: () => void,
): void {
  clearPending(rt);
  rt.pendingTimer = window.setTimeout(() => {
    rt.pendingTimer = null;
    if (rt.session !== session) return;
    fn();
  }, delayMs);
}

export function speakBrowserText(
  text: string,
  callbacks: SpeakBrowserCallbacks,
): void {
  const rt = runtime();
  const session = rt.session;
  const chunks = chunkTextForSpeech(text);
  if (chunks.length === 0) {
    callbacks.onDone();
    return;
  }

  let chunkIdx = 0;

  const finish = () => {
    clearKeepAlive(rt);
    if (rt.session !== session) return;
    callbacks.onDone();
  };

  void waitForVoices().then((voices) => {
    if (rt.session !== session) return;

    const locale = detectSpeechLocale(text);
    if (!hasBrowserVoiceForText(text, voices)) {
      callbacks.onNoVoice?.();
      return;
    }

    const voice = pickVoiceForLocale(locale, voices);

    const speakChunk = () => {
      if (rt.session !== session || chunkIdx >= chunks.length) {
        finish();
        return;
      }

      const utter = new SpeechSynthesisUtterance(chunks[chunkIdx]);
      utter.lang = locale;
      if (voice) utter.voice = voice;

      let settled = false;
      const settle = (advance: boolean) => {
        if (settled || rt.session !== session) return;
        settled = true;
        clearKeepAlive(rt);
        if (!advance) {
          finish();
          return;
        }
        chunkIdx += 1;
        if (chunkIdx >= chunks.length) {
          finish();
          return;
        }
        scheduleSpeak(rt, session, CHUNK_GAP_MS, speakChunk);
      };

      utter.onstart = () => {
        clearKeepAlive(rt);
        rt.keepAliveTimer = window.setInterval(() => {
          if (rt.session !== session || !window.speechSynthesis.speaking) {
            clearKeepAlive(rt);
            return;
          }
          window.speechSynthesis.pause();
          window.speechSynthesis.resume();
        }, KEEPALIVE_MS);
      };

      utter.onend = () => settle(true);
      utter.onerror = (event) => {
        if (isBenignSpeechError(event.error)) return;
        settle(false);
      };

      window.speechSynthesis.speak(utter);
    };

    const delay =
      rt.needsSpeakDelay ||
      window.speechSynthesis.speaking ||
      window.speechSynthesis.pending
        ? CANCEL_TO_SPEAK_MS
        : 0;
    rt.needsSpeakDelay = false;
    scheduleSpeak(rt, session, delay, speakChunk);
  });
}
