/**
 * 16 kHz mono PCM helpers for realtime speech recognition.
 *
 * Tencent's realtime ASR expects 16-bit mono PCM at 16 kHz, sent in ~40 ms
 * frames (640 samples / 1280 bytes) at roughly 1:1 realtime.
 */

export const REALTIME_SAMPLE_RATE = 16000;
export const FRAME_SAMPLES = 640;
export const FRAME_BYTES = FRAME_SAMPLES * 2;

function toPcm16(sample: number): number {
  const clamped = Math.max(-1, Math.min(1, sample));
  return clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff;
}

export function floatToPcm16(input: Float32Array): Int16Array {
  const out = new Int16Array(input.length);
  for (let i = 0; i < input.length; i += 1) {
    out[i] = toPcm16(input[i]);
  }
  return out;
}

/** Linearly interpolated resample to 16 kHz PCM16; adequate for speech. */
export function downsampleToPcm16(
  input: Float32Array,
  inputRate: number,
): Int16Array {
  if (inputRate <= REALTIME_SAMPLE_RATE) return floatToPcm16(input);
  const ratio = inputRate / REALTIME_SAMPLE_RATE;
  const outLength = Math.floor(input.length / ratio);
  const out = new Int16Array(outLength);
  for (let i = 0; i < outLength; i += 1) {
    const position = i * ratio;
    const left = Math.floor(position);
    const right = Math.min(left + 1, input.length - 1);
    const weight = position - left;
    out[i] = toPcm16(input[left] * (1 - weight) + input[right] * weight);
  }
  return out;
}

/** Accumulates arbitrary PCM chunks into whole {@link FRAME_BYTES} frames. */
export class PcmFrameBuffer {
  private carry = new Uint8Array(0);

  push(samples: Int16Array): Uint8Array[] {
    const bytes = new Uint8Array(
      samples.buffer,
      samples.byteOffset,
      samples.byteLength,
    );
    const merged = new Uint8Array(this.carry.length + bytes.length);
    merged.set(this.carry, 0);
    merged.set(bytes, this.carry.length);

    const frames: Uint8Array[] = [];
    let offset = 0;
    while (merged.length - offset >= FRAME_BYTES) {
      frames.push(merged.slice(offset, offset + FRAME_BYTES));
      offset += FRAME_BYTES;
    }
    this.carry = merged.slice(offset);
    return frames;
  }

  reset(): void {
    this.carry = new Uint8Array(0);
  }
}
