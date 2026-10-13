import { describe, expect, it } from "vitest";
import {
  FRAME_BYTES,
  PcmFrameBuffer,
  downsampleToPcm16,
  floatToPcm16,
} from "./pcmCapture";

describe("floatToPcm16", () => {
  it("clamps to the signed 16-bit range", () => {
    const out = floatToPcm16(new Float32Array([0, 1, -1, 2, -2]));
    expect([...out]).toEqual([0, 32767, -32768, 32767, -32768]);
  });
});

describe("downsampleToPcm16", () => {
  it("keeps 16 kHz input as is", () => {
    const out = downsampleToPcm16(new Float32Array([0, 0.5, -0.5]), 16000);
    expect([...out]).toEqual([0, 16383, -16384]);
  });

  it("interpolates 48 kHz input down to a third of the samples", () => {
    const input = new Float32Array(480).fill(0.5);
    const out = downsampleToPcm16(input, 48000);
    expect(out.length).toBe(160);
    expect([...out].every((sample) => sample === 16383)).toBe(true);
  });
});

describe("PcmFrameBuffer", () => {
  it("emits whole frames of 1280 bytes", () => {
    const buffer = new PcmFrameBuffer();
    const frames = buffer.push(new Int16Array(640).fill(1));

    expect(frames).toHaveLength(1);
    expect(frames[0].byteLength).toBe(FRAME_BYTES);
    expect([...frames[0].slice(0, 2)]).toEqual([1, 0]);
  });

  it("carries the remainder into the next frame", () => {
    const buffer = new PcmFrameBuffer();

    expect(buffer.push(new Int16Array(320).fill(1))).toHaveLength(0);
    const frames = buffer.push(new Int16Array(320).fill(2));

    expect(frames).toHaveLength(1);
    expect([...new Int16Array(frames[0].buffer)].slice(0, 320)).toEqual(
      new Array(320).fill(1),
    );
    expect([...new Int16Array(frames[0].buffer)].slice(320)).toEqual(
      new Array(320).fill(2),
    );
  });

  it("emits several frames for a large chunk", () => {
    const buffer = new PcmFrameBuffer();
    expect(buffer.push(new Int16Array(1600))).toHaveLength(2);
  });

  it("drops the carry on reset", () => {
    const buffer = new PcmFrameBuffer();
    buffer.push(new Int16Array(320).fill(1));
    buffer.reset();

    expect(buffer.push(new Int16Array(320).fill(2))).toHaveLength(0);
    const frames = buffer.push(new Int16Array(320).fill(2));
    expect([...new Int16Array(frames[0].buffer)].slice(0, 320)).toEqual(
      new Array(320).fill(2),
    );
  });
});
