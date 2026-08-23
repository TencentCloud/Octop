/**
 * Incremental WAV/PCM playback for streaming TTS responses.
 *
 * The server streams MiMo TTS as a WAV (24kHz PCM16LE mono) whose data-size
 * field is a max-size sentinel — a blob/<audio> player would have to wait for
 * the full body. Here we parse the header once, decode incoming PCM chunks,
 * and schedule them back-to-back on an AudioContext as they arrive.
 */

export interface WavFormat {
  channels: number;
  sampleRate: number;
  bitsPerSample: number;
  headerLength: number;
}

/** Parse the canonical 44-byte PCM WAV header the voice router emits. */
export function parseWavHeader(bytes: Uint8Array): WavFormat | null {
  if (bytes.length < 44) return null;
  const dv = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const tag = (offset: number) =>
    String.fromCharCode(
      bytes[offset],
      bytes[offset + 1],
      bytes[offset + 2],
      bytes[offset + 3],
    );
  if (tag(0) !== "RIFF" || tag(8) !== "WAVE" || tag(36) !== "data") return null;
  const channels = dv.getUint16(22, true);
  const sampleRate = dv.getUint32(24, true);
  const bitsPerSample = dv.getUint16(34, true);
  if (bitsPerSample !== 16 || channels < 1) return null;
  return { channels, sampleRate, bitsPerSample, headerLength: 44 };
}

/** Convert little-endian PCM16 bytes to normalized float samples. */
export function pcm16ToFloat32(bytes: Uint8Array): Float32Array {
  const frames = Math.floor(bytes.length / 2);
  const out = new Float32Array(frames);
  const dv = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  for (let i = 0; i < frames; i++) {
    out[i] = dv.getInt16(i * 2, true) / 32768;
  }
  return out;
}

type AudioContextCtor = typeof AudioContext;

function audioContextCtor(): AudioContextCtor | null {
  if (typeof window === "undefined") return null;
  return (
    window.AudioContext ||
    (window as unknown as { webkitAudioContext?: AudioContextCtor })
      .webkitAudioContext ||
    null
  );
}

/** True when the environment can do WebAudio streaming playback. */
export function supportsWavStreamPlayback(): boolean {
  return audioContextCtor() !== null && typeof ReadableStream !== "undefined";
}

/**
 * Schedules PCM chunks on an AudioContext with gapless back-to-back timing.
 * Supports the mono/stereo PCM16 formats the TTS route produces.
 */
export class WavStreamPlayer {
  private ctx: AudioContext | null = null;
  private nextStart = 0;
  private sources = new Set<AudioBufferSourceNode>();
  private headerConsumed = false;
  private bytesScheduled = 0;
  private carry: Uint8Array = new Uint8Array(0);

  get hasAudio(): boolean {
    return this.bytesScheduled > 0;
  }

  /** Create/resume the AudioContext (call inside the user-gesture task). */
  ensureContext(): boolean {
    const Ctor = audioContextCtor();
    if (!Ctor) return false;
    if (!this.ctx) this.ctx = new Ctor();
    if (this.ctx.state === "suspended") {
      void this.ctx.resume().catch(() => {});
    }
    return true;
  }

  /**
   * Feed one raw HTTP response chunk. Strips the WAV header on the first
   * call, re-buffers partial frames, and schedules complete frames.
   * Returns false when the stream is not a supported WAV (nothing played).
   */
  push(chunk: Uint8Array): boolean {
    let data = this.carry.length
      ? concatBytes(this.carry, chunk)
      : chunk.slice();
    this.carry = new Uint8Array(0);
    if (!this.headerConsumed) {
      const fmt = parseWavHeader(data);
      if (!fmt) return false;
      this.fmt = fmt;
      data = data.subarray(fmt.headerLength);
      this.headerConsumed = true;
    }
    const fmt = this.fmt;
    if (!fmt) return false;
    const frameBytes = fmt.channels * (fmt.bitsPerSample / 8);
    const whole = Math.floor(data.length / frameBytes) * frameBytes;
    if (whole > 0) this.schedule(data.subarray(0, whole));
    if (whole < data.length) this.carry = data.slice(whole);
    return true;
  }

  private fmt: WavFormat | null = null;

  private schedule(pcm: Uint8Array): void {
    const ctx = this.ctx;
    const fmt = this.fmt;
    if (!ctx || !fmt) return;
    const samples = pcm16ToFloat32(pcm);
    const perChannel = Math.floor(samples.length / fmt.channels);
    if (perChannel === 0) return;
    const buffer = ctx.createBuffer(fmt.channels, perChannel, fmt.sampleRate);
    if (fmt.channels === 1) {
      buffer.copyToChannel(samples, 0);
    } else {
      for (let ch = 0; ch < fmt.channels; ch++) {
        const channelData = new Float32Array(perChannel);
        for (let i = 0; i < perChannel; i++) {
          channelData[i] = samples[i * fmt.channels + ch];
        }
        buffer.copyToChannel(channelData, ch);
      }
    }
    const src = ctx.createBufferSource();
    src.buffer = buffer;
    src.connect(ctx.destination);
    const startAt = Math.max(ctx.currentTime + 0.02, this.nextStart);
    src.start(startAt);
    this.nextStart = startAt + buffer.duration;
    this.sources.add(src);
    this.bytesScheduled += pcm.length;
    src.onended = () => {
      this.sources.delete(src);
    };
  }

  /** Milliseconds until every scheduled chunk has finished playing. */
  msRemaining(): number {
    if (!this.ctx || this.bytesScheduled === 0) return 0;
    return Math.max(0, (this.nextStart - this.ctx.currentTime) * 1000);
  }

  /** Stop immediately; pending and queued audio are dropped. */
  stop(): void {
    for (const src of this.sources) {
      try {
        src.stop();
      } catch {
        /* already stopped */
      }
    }
    this.sources.clear();
    const ctx = this.ctx;
    this.close();
    if (ctx && ctx.state !== "closed") {
      void ctx.close().catch(() => {
        /* ignore close failures */
      });
    }
  }

  /** Release the AudioContext (keeps it usable until closed). */
  close(): void {
    this.ctx = null;
    this.fmt = null;
    this.headerConsumed = false;
    this.carry = new Uint8Array(0);
  }
}

function concatBytes(a: Uint8Array, b: Uint8Array): Uint8Array {
  const out = new Uint8Array(a.length + b.length);
  out.set(a, 0);
  out.set(b, a.length);
  return out;
}
