/** Decode Annex-B-derived AVCC H.264 samples onto a canvas via WebCodecs. */

export interface H264Init {
  codec: string;
  description: Uint8Array;
  width: number;
  height: number;
}

export function canDecodeAvc(): boolean {
  return typeof VideoDecoder !== "undefined";
}

function b64ToBytes(b64: string): Uint8Array {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

export class H264CanvasDecoder {
  private decoder: VideoDecoder | null = null;
  private canvas: HTMLCanvasElement | null = null;
  private ts = 0;
  private configured = false;

  attach(canvas: HTMLCanvasElement | null): void {
    this.canvas = canvas;
  }

  configure(init: H264Init): void {
    this.close();
    if (!canDecodeAvc()) {
      throw new Error("WebCodecs VideoDecoder is not available");
    }
    const canvas = this.canvas;
    this.decoder = new VideoDecoder({
      output: (frame) => {
        const target = this.canvas ?? canvas;
        if (!target) {
          frame.close();
          return;
        }
        const w = frame.displayWidth || init.width;
        const h = frame.displayHeight || init.height;
        if (w > 0 && h > 0 && (target.width !== w || target.height !== h)) {
          target.width = w;
          target.height = h;
        }
        const ctx = target.getContext("2d");
        if (ctx) {
          ctx.drawImage(frame, 0, 0, target.width, target.height);
        }
        frame.close();
      },
      error: (err) => {
        console.error("mobile H.264 decode error", err);
      },
    });
    const config: VideoDecoderConfig = {
      codec: init.codec,
      description: init.description,
      optimizeForLatency: true,
    };
    if (init.width > 0) config.codedWidth = init.width;
    if (init.height > 0) config.codedHeight = init.height;
    this.decoder.configure(config);
    this.configured = true;
    this.ts = 0;
  }

  decode(sample: Uint8Array, key: boolean): void {
    if (!this.decoder || !this.configured) return;
    if (this.decoder.decodeQueueSize > 16 && !key) return;
    const chunk = new EncodedVideoChunk({
      type: key ? "key" : "delta",
      timestamp: this.ts,
      data: sample,
    });
    this.ts += 16_667;
    this.decoder.decode(chunk);
  }

  close(): void {
    if (this.decoder) {
      try {
        this.decoder.close();
      } catch {
        /* already closed */
      }
      this.decoder = null;
    }
    this.configured = false;
  }
}

export function parseVideoInit(msg: {
  codec?: string;
  description?: string;
  width?: number;
  height?: number;
}): H264Init | null {
  if (!msg.codec || !msg.description) return null;
  return {
    codec: msg.codec,
    description: b64ToBytes(msg.description),
    width: msg.width ?? 0,
    height: msg.height ?? 0,
  };
}
