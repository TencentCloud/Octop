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

import { message as antMessage } from "@/utils/antdMessage";

export function useVoiceOutput() {
  const { t } = useTranslation();
  const [speakingId, setSpeakingId] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const speakingIdRef = useRef<string | null>(null);
  const playGenerationRef = useRef(0);

  const finishSpeaking = useCallback(() => {
    speakingIdRef.current = null;
    setSpeakingId(null);
  }, []);

  const abortPlayback = useCallback(() => {
    playGenerationRef.current += 1;
    stopBrowserSpeech();
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

  const speakWithServer = useCallback(
    async (plain: string, gen: number, provider?: string) => {
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
    [finishSpeaking, t],
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
