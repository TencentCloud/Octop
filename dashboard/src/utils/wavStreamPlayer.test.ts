import { describe, expect, it } from "vitest";

import { parseWavHeader, pcm16ToFloat32 } from "./wavStreamPlayer";

function wavHeaderBytes(
  sampleRate = 24000,
  channels = 1,
  dataLen = 8,
): Uint8Array {
  const bytes = new Uint8Array(44);
  const dv = new DataView(bytes.buffer);
  const ascii = (offset: number, s: string) => {
    for (let i = 0; i < s.length; i++) bytes[offset + i] = s.charCodeAt(i);
  };
  ascii(0, "RIFF");
  dv.setUint32(4, 36 + dataLen, true);
  ascii(8, "WAVE");
  ascii(12, "fmt ");
  dv.setUint32(16, 16, true);
  dv.setUint16(20, 1, true); // PCM
  dv.setUint16(22, channels, true);
  dv.setUint32(24, sampleRate, true);
  dv.setUint32(28, sampleRate * channels * 2, true);
  dv.setUint16(32, channels * 2, true);
  dv.setUint16(34, 16, true);
  ascii(36, "data");
  dv.setUint32(40, dataLen, true);
  return bytes;
}

describe("parseWavHeader", () => {
  it("parses a canonical 44-byte PCM header", () => {
    const fmt = parseWavHeader(wavHeaderBytes());
    expect(fmt).not.toBeNull();
    expect(fmt?.sampleRate).toBe(24000);
    expect(fmt?.channels).toBe(1);
    expect(fmt?.bitsPerSample).toBe(16);
    expect(fmt?.headerLength).toBe(44);
  });

  it("rejects short buffers", () => {
    expect(parseWavHeader(new Uint8Array(10))).toBeNull();
  });

  it("rejects non-WAV payloads", () => {
    const mp3 = new TextEncoder().encode(
      "ID3SOMEDATASOMEDATASOMEDATASOMEDATASOMED",
    );
    expect(parseWavHeader(mp3)).toBeNull();
  });
});

describe("pcm16ToFloat32", () => {
  it("decodes little-endian int16 to [-1, 1] floats", () => {
    const bytes = new Uint8Array([0x00, 0x00, 0x00, 0x80, 0x00, 0x7f]);
    const out = pcm16ToFloat32(bytes);
    expect(out).toHaveLength(3);
    expect(out[0]).toBe(0);
    expect(out[1]).toBeCloseTo(-1);
    expect(out[2]).toBeCloseTo(32512 / 32768);
  });

  it("drops a trailing odd byte", () => {
    expect(pcm16ToFloat32(new Uint8Array(5))).toHaveLength(2);
  });
});

describe("WavStreamPlayer frame buffering (node env without AudioContext)", () => {
  it("pushing a non-WAV first chunk reports unsupported", async () => {
    const { WavStreamPlayer } = await import("./wavStreamPlayer");
    const player = new WavStreamPlayer();
    const mp3 = new TextEncoder().encode("ID3...");
    expect(player.push(mp3)).toBe(false);
  });

  it("validates header and buffers partial frames via push/carry", async () => {
    const { WavStreamPlayer } = await import("./wavStreamPlayer");
    const player = new WavStreamPlayer();
    // No AudioContext in node — push() should still parse the header and
    // buffer partial frames without throwing.
    const header = wavHeaderBytes();
    const odd = new Uint8Array(3);
    expect(player.push(header)).toBe(true);
    expect(player.push(odd)).toBe(true);
    expect(player.hasAudio).toBe(false);
    expect(player.push(new Uint8Array(1))).toBe(true);
    // hasAudio stays false in node (no context to schedule on).
    player.stop();
  });
});
