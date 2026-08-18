import { useCallback, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { voiceApi } from "../api/modules/voice";
import { cachedActiveVoice, fetchActiveVoice } from "./useVoiceConfig";
import {
  ensureAudioUnlocked,
  isAutoplayBlockedError,
  primeAudioElement,
} from "./useAudioUnlock";
import { prepareSpeechText } from "../utils/plainTextForSpeech";
import { speakBrowserText, stopBrowserSpeech } from "../utils/browserSpeech";
import { isMobileUserAgent } from "../utils/mobileDevice";
import { WavStreamPlayer } from "../utils/wavStreamPlayer";

import { message as antMessage } from "@/utils/antdMessage";

export function useVoiceOutput() {
  const { t } = useTranslation();
  const [speakingId, setSpeakingId] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const streamPlayerRef = useRef<WavStreamPlayer | null>(null);
  const speakingIdRef = useRef<string | null>(null);
  const playGenerationRef = useRef(0);

  const finishSpeaking = useCallback(() => {
    speakingIdRef.current = null;
    setSpeakingId(null);
  }, []);

  const abortPlayback = useCallback(() => {
    playGenerationRef.current += 1;
    stopBrowserSpeech();
    streamPlayerRef.current?.stop();
    streamPlayerRef.current = null;
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.onended = null;
      audioRef.current.onerror = null;
      audioRef.current.removeAttribute("src");
      audioRef.current.load();
      audioRef.current = null;
    }
    finishSpeaking();
  }, [finishSpeaking]);

  const primeMobileAudio = useCallback(() => {
    if (!isMobileUserAgent()) return;
    const audio = new Audio();
    audioRef.current = audio;
    primeAudioElement(audio);
  }, []);

  /**
   * Stream the MiMo WAV response and schedule chunks as they arrive.
   * Returns false when streaming is unsupported or the response is not a
   * WAV — the caller then falls back to the buffered blob path.
   */
  const speakMimoStream = useCallback(
    async (plain: string, gen: number) => {
      const player = new WavStreamPlayer();
      streamPlayerRef.current = player;
      try {
        if (!player.ensureContext()) return false;
        const { contentType, body } = await voiceApi.synthesizeStream(plain);
        if (
          !contentType.includes("audio/wav") &&
          !contentType.includes("audio/wave")
        ) {
          try {
            await body.cancel();
          } catch {
            /* ignore */
          }
          return false;
        }
        const reader = body.getReader();
        // Read until the WAV header plus first audio chunk are scheduled —
        // malformed streams can still fall back to the blob path here.
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          if (!value) continue;
          if (!player.push(value)) {
            player.stop();
            return false;
          }
          if (player.hasAudio) break;
        }
        // Feed remaining chunks in the background until the stream ends.
        void (async () => {
          try {
            for (;;) {
              const { done, value } = await reader.read();
              if (done) break;
              if (value) player.push(value);
            }
          } catch {
            /* network hiccup — keep whatever was scheduled */
          } finally {
            const wait = Math.max(player.msRemaining(), 0);
            window.setTimeout(() => {
              player.stop();
              if (playGenerationRef.current === gen) finishSpeaking();
            }, wait);
          }
        })();
        if (playGenerationRef.current !== gen) {
          player.stop();
        }
        return true;
      } catch {
        return false;
      }
    },
    [finishSpeaking],
  );

  const speakWithServer = useCallback(
    async (plain: string, gen: number, provider?: string) => {
      // MiMo streams a live WAV — play it chunk-by-chunk for low latency.
      // Other providers stream MP3, which needs the buffered blob path.
      const active = cachedActiveVoice();
      const ttsProvider = provider ?? active?.tts;
      if (ttsProvider === "mimo-tts" || ttsProvider === "mimo") {
        if (await speakMimoStream(plain, gen)) return;
      }

      try {
        const blob = await voiceApi.synthesize(plain, provider);
        if (playGenerationRef.current !== gen) return;

        const url = URL.createObjectURL(blob);
        const audio = audioRef.current ?? new Audio();
        audioRef.current = audio;

        audio.onended = () => {
          URL.revokeObjectURL(url);
          if (playGenerationRef.current === gen) finishSpeaking();
        };
        audio.onerror = () => {
          URL.revokeObjectURL(url);
          if (playGenerationRef.current === gen) {
            antMessage.error(t("voice.ttsFailed"));
            finishSpeaking();
          }
        };

        audio.src = url;
        audio.load();

        if (!isMobileUserAgent()) {
          ensureAudioUnlocked();
        }

        await audio.play();
      } catch (err) {
        if (playGenerationRef.current !== gen) return;
        if (isAutoplayBlockedError(err)) {
          antMessage.warning(t("voice.ttsAutoplayBlocked"));
        } else {
          antMessage.error(t("voice.ttsFailed"));
        }
        finishSpeaking();
      }
    },
    [finishSpeaking, speakMimoStream, t],
  );

  const speakWithBrowser = useCallback(
    (plain: string, gen: number) => {
      speakBrowserText(plain, {
        onDone: () => {
          if (playGenerationRef.current !== gen) return;
          finishSpeaking();
        },
        onNoVoice: () => {
          if (playGenerationRef.current !== gen) return;
          if (!isMobileUserAgent()) {
            antMessage.info(t("voice.browserNoChineseVoice"));
          }
          stopBrowserSpeech();
          void speakWithServer(plain, gen, "edge");
        },
      });
    },
    [finishSpeaking, speakWithServer, t],
  );

  const beginPlayback = useCallback(
    (messageId: string, plain: string, gen: number, tts: string) => {
      if (playGenerationRef.current !== gen) return;

      speakingIdRef.current = messageId;
      setSpeakingId(messageId);

      // Mobile: browser speechSynthesis + async Edge fallback break the tap
      // gesture chain on iOS/Android — use Edge TTS directly.
      if (isMobileUserAgent()) {
        stopBrowserSpeech();
        void speakWithServer(plain, gen, "edge");
        return;
      }

      if (tts === "browser") {
        speakWithBrowser(plain, gen);
        return;
      }

      stopBrowserSpeech();
      void speakWithServer(plain, gen);
    },
    [speakWithBrowser, speakWithServer],
  );

  const speak = useCallback(
    (messageId: string, text: string) => {
      if (speakingIdRef.current === messageId) {
        abortPlayback();
        return;
      }

      const plain = prepareSpeechText(text);
      abortPlayback();
      const gen = playGenerationRef.current;

      if (!plain) {
        antMessage.info(t("voice.nothingToRead", "没有可朗读的正文"));
        return;
      }

      // Must run in the same synchronous turn as the tap (before any await).
      primeMobileAudio();

      const cached = cachedActiveVoice();
      if (cached || isMobileUserAgent()) {
        beginPlayback(messageId, plain, gen, cached?.tts ?? "browser");
        return;
      }

      void fetchActiveVoice()
        .then((active) => {
          beginPlayback(messageId, plain, gen, active.tts);
        })
        .catch(() => {
          if (playGenerationRef.current !== gen) return;
          antMessage.error(t("voice.ttsFailed"));
        });
    },
    [abortPlayback, beginPlayback, primeMobileAudio, t],
  );

  return { speakingId, speak, stop: abortPlayback };
}
