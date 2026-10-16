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
  const streamReaderRef =
    useRef<ReadableStreamDefaultReader<Uint8Array> | null>(null);
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
    void streamReaderRef.current?.cancel().catch(() => {});
    streamReaderRef.current = null;
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

  const primeWavPlayer = useCallback(() => {
    const player = new WavStreamPlayer();
    try {
      if (player.ensureContext()) {
        streamPlayerRef.current = player;
        return;
      }
    } catch {
      // Buffer the response when the browser cannot create an AudioContext.
    }
    player.stop();
  }, []);

  const speakWavStream = useCallback(
    async (
      body: ReadableStream<Uint8Array>,
      gen: number,
      player: WavStreamPlayer,
    ) => {
      const reader = body.getReader();
      streamReaderRef.current = reader;
      try {
        // A response's 44-byte WAV header may arrive in multiple network chunks.
        const headerChunks: Uint8Array[] = [];
        let headerLength = 0;
        let headerReady = false;
        for (;;) {
          const { done, value } = await reader.read();
          if (playGenerationRef.current !== gen) {
            await reader.cancel();
            player.stop();
            return true;
          }
          if (done) break;
          if (!value) continue;
          let chunk = value;
          if (!headerReady) {
            headerChunks.push(value);
            headerLength += value.length;
            if (headerLength < 44) continue;
            chunk = new Uint8Array(headerLength);
            let offset = 0;
            for (const part of headerChunks) {
              chunk.set(part, offset);
              offset += part.length;
            }
            headerChunks.length = 0;
            headerReady = true;
          }
          if (!player.push(chunk)) throw new Error("Unsupported WAV stream");
        }
        if (!player.hasAudio) throw new Error("Empty WAV stream");
        const wait = Math.max(player.msRemaining(), 0);
        window.setTimeout(() => {
          player.stop();
          if (streamPlayerRef.current === player)
            streamPlayerRef.current = null;
          if (playGenerationRef.current === gen) finishSpeaking();
        }, wait);
        return true;
      } catch (err) {
        player.stop();
        if (streamPlayerRef.current === player) streamPlayerRef.current = null;
        await reader.cancel().catch(() => {});
        throw err;
      } finally {
        if (streamReaderRef.current === reader) streamReaderRef.current = null;
        reader.releaseLock();
      }
    },
    [finishSpeaking],
  );

  const speakWithServer = useCallback(
    async (plain: string, gen: number, provider?: string) => {
      const preparedPlayer = streamPlayerRef.current;
      try {
        const { contentType, body } = await voiceApi.synthesizeStream(
          plain,
          provider,
        );
        if (playGenerationRef.current !== gen) {
          await body.cancel();
          return;
        }
        const mime = contentType.split(";", 1)[0].trim().toLowerCase();
        if (
          preparedPlayer &&
          ["audio/wav", "audio/wave", "audio/x-wav"].includes(mime)
        ) {
          await speakWavStream(body, gen, preparedPlayer);
          return;
        }
        preparedPlayer?.stop();
        if (streamPlayerRef.current === preparedPlayer)
          streamPlayerRef.current = null;
        // Reuse the response for MP3 and browsers without WebAudio.
        const blob = await new Response(body, {
          headers: { "Content-Type": contentType },
        }).blob();
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
        preparedPlayer?.stop();
        if (streamPlayerRef.current === preparedPlayer)
          streamPlayerRef.current = null;
        if (playGenerationRef.current !== gen) return;
        if (isAutoplayBlockedError(err)) {
          antMessage.warning(t("voice.ttsAutoplayBlocked"));
        } else {
          antMessage.error(t("voice.ttsFailed"));
        }
        finishSpeaking();
      }
    },
    [finishSpeaking, speakWavStream, t],
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

      if (tts === "browser") {
        streamPlayerRef.current?.stop();
        streamPlayerRef.current = null;
      }

      // Mobile: browser speechSynthesis + async Edge fallback break the tap
      // gesture chain on iOS/Android — use Edge TTS directly.
      if (isMobileUserAgent() && tts === "browser") {
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
      if (cached?.tts !== "browser") primeWavPlayer();
      if (cached) {
        beginPlayback(messageId, plain, gen, cached.tts);
        return;
      }

      void fetchActiveVoice()
        .then((active) => {
          beginPlayback(messageId, plain, gen, active.tts);
        })
        .catch(() => {
          if (playGenerationRef.current !== gen) return;
          antMessage.error(t("voice.ttsFailed"));
          abortPlayback();
        });
    },
    [abortPlayback, beginPlayback, primeMobileAudio, primeWavPlayer, t],
  );

  return { speakingId, speak, stop: abortPlayback };
}
