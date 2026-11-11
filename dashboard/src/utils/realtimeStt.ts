/**
 * Browser client for Octop's realtime STT WebSocket (`/api/voice/stt-stream`).
 *
 * Tencent refines a sentence (`interim`) before confirming it (`final`), so the
 * client tracks confirmed sentences by id and reports the *cumulative*
 * transcript of the session. The composer can therefore replace only the tail
 * of the input it owns instead of appending duplicates.
 */

export interface RealtimeSttHandlers {
  /** Cumulative transcript while the current sentence is still being refined. */
  onInterim?: (text: string) => void;
  /** Cumulative transcript once a sentence is confirmed. */
  onFinal?: (text: string) => void;
  /** The audio stream finished server-side. */
  onDone?: () => void;
  /** ``message`` comes from the server; ``null`` means a transport failure. */
  onError?: (message: string | null) => void;
}

interface ServerFrame {
  type?: string;
  text?: string;
  sentence_id?: number;
  message?: string;
}

/** Sentence id used when committing a trailing interim sentence at ``done``. */
const TRAILING_SENTENCE_ID = Number.MAX_SAFE_INTEGER;

export class RealtimeSttClient {
  private socket: WebSocket | null = null;
  private readonly finals = new Map<number, string>();
  private interim = "";
  private pending: Uint8Array[] = [];
  private ready = false;
  private finished = false;
  private endRequested = false;
  private closed = false;
  private readonly url: string;
  private readonly handlers: RealtimeSttHandlers;

  constructor(url: string, handlers: RealtimeSttHandlers = {}) {
    this.url = url;
    this.handlers = handlers;
  }

  /** Open the socket; resolves once the server reports ``ready``. */
  connect(): Promise<void> {
    return new Promise<void>((resolve, reject) => {
      const socket = new WebSocket(this.url);
      socket.binaryType = "arraybuffer";
      this.socket = socket;

      const failConnect = (error: unknown) => reject(error);

      socket.onopen = () => {
        // Nothing to send yet: PCM frames are buffered until `ready`.
      };
      socket.onmessage = (event: MessageEvent) => {
        const frame = parseFrame(event.data);
        if (!frame) return;
        if (frame.type === "ready") {
          this.ready = true;
          this.flushPending();
          resolve();
          return;
        }
        this.handleFrame(frame);
      };
      socket.onerror = () => {
        if (!this.ready) failConnect(new Error("realtime STT socket error"));
        this.fail(null);
      };
      socket.onclose = () => {
        if (!this.ready) {
          failConnect(new Error("realtime STT socket closed before ready"));
        }
        if (!this.finished && !this.closed) this.fail(null);
      };
    });
  }

  /** Queue or send one PCM frame (16 kHz / 16-bit / mono). */
  send(frame: Uint8Array): void {
    if (this.closed) return;
    if (!this.ready) {
      this.pending.push(frame);
      return;
    }
    this.socket?.send(frame);
  }

  /** Tell the server the audio stream ended and wait for its final results. */
  end(): void {
    if (this.closed) return;
    this.endRequested = true;
    if (this.ready) this.socket?.send(JSON.stringify({ type: "end" }));
  }

  /** Tear down without reporting an error (user cancelled). */
  close(): void {
    this.closed = true;
    this.pending = [];
    this.socket?.close();
    this.socket = null;
  }

  private handleFrame(frame: ServerFrame): void {
    if (frame.type === "interim") {
      this.interim = frame.text ?? "";
      this.handlers.onInterim?.(this.transcript());
      return;
    }
    if (frame.type === "final") {
      this.finals.set(frame.sentence_id ?? 0, frame.text ?? "");
      this.interim = "";
      this.handlers.onFinal?.(this.transcript());
      return;
    }
    if (frame.type === "done") {
      this.commitTrailingInterim();
      this.finished = true;
      this.handlers.onDone?.();
      this.close();
      return;
    }
    if (frame.type === "error") {
      this.fail(frame.message ?? null);
    }
  }

  private commitTrailingInterim(): void {
    if (!this.interim) return;
    this.finals.set(TRAILING_SENTENCE_ID, this.interim);
    this.interim = "";
    this.handlers.onFinal?.(this.transcript());
  }

  private transcript(): string {
    const confirmed = [...this.finals.entries()]
      .sort(([a], [b]) => a - b)
      .map(([, text]) => text)
      .filter(Boolean);
    if (this.interim) confirmed.push(this.interim);
    return confirmed.join("");
  }

  private flushPending(): void {
    if (!this.ready) return;
    const queued = this.pending;
    this.pending = [];
    for (const frame of queued) this.socket?.send(frame);
    if (this.endRequested) this.end();
  }

  private fail(message: string | null): void {
    if (this.finished || this.closed) return;
    this.finished = true;
    this.handlers.onError?.(message);
    this.close();
  }
}

function parseFrame(data: unknown): ServerFrame | null {
  if (typeof data !== "string") return null;
  try {
    const parsed: unknown = JSON.parse(data);
    return parsed && typeof parsed === "object"
      ? (parsed as ServerFrame)
      : null;
  } catch {
    return null;
  }
}
