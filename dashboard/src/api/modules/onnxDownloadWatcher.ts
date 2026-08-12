/**
 * Background watcher for ONNX model downloads.
 * Survives closing the progress / config modal; notifies once on completion.
 */
import { onnxModelApi, type OnnxDownloadState } from "./onnxModel";

export type OnnxDownloadProgressHandler = (state: OnnxDownloadState) => void;
export type OnnxDownloadTerminalHandler = (
  state: OnnxDownloadState,
) => void | Promise<void>;

interface WatchOptions {
  modelId: string;
  onProgress?: OnnxDownloadProgressHandler;
  onTerminal: OnnxDownloadTerminalHandler;
  intervalMs?: number;
  maxTicks?: number;
}

interface ActiveWatch {
  modelId: string;
  timer: ReturnType<typeof setInterval>;
  onProgress?: OnnxDownloadProgressHandler;
  onTerminal: OnnxDownloadTerminalHandler;
  ticks: number;
  maxTicks: number;
  finished: boolean;
}

let active: ActiveWatch | null = null;

export function isWatchingOnnxDownload(modelId?: string): boolean {
  if (!active || active.finished) return false;
  if (modelId) return active.modelId === modelId;
  return true;
}

export function getActiveOnnxDownloadModelId(): string | null {
  return active && !active.finished ? active.modelId : null;
}

/** Attach/replace UI progress listener without restarting the poll. */
export function setOnnxDownloadProgressHandler(
  handler: OnnxDownloadProgressHandler | undefined,
): void {
  if (active) active.onProgress = handler;
}

export function stopWatchingOnnxDownload(): void {
  if (!active) return;
  clearInterval(active.timer);
  active = null;
}

export function watchOnnxDownload(opts: WatchOptions): void {
  const {
    modelId,
    onProgress,
    onTerminal,
    intervalMs = 500,
    maxTicks = 600,
  } = opts;

  stopWatchingOnnxDownload();

  const watch: ActiveWatch = {
    modelId,
    onProgress,
    onTerminal,
    ticks: 0,
    maxTicks,
    finished: false,
    timer: setInterval(() => {
      void tick();
    }, intervalMs),
  };
  active = watch;

  async function tick(): Promise<void> {
    if (!active || active !== watch || watch.finished) return;
    watch.ticks += 1;
    try {
      const state = await onnxModelApi.getDownloadStatus();
      watch.onProgress?.(state);
      if (state.status === "done" || state.status === "failed") {
        await finish(state);
        return;
      }
      if (watch.ticks >= watch.maxTicks) {
        await finish({
          status: "failed",
          progress: state.progress ?? 0,
          error: "download timed out",
          model_name: modelId,
        });
      }
    } catch (err) {
      await finish({
        status: "failed",
        progress: 0,
        error: err instanceof Error ? err.message : String(err),
        model_name: modelId,
      });
    }
  }

  async function finish(state: OnnxDownloadState): Promise<void> {
    if (watch.finished) return;
    watch.finished = true;
    clearInterval(watch.timer);
    if (active === watch) active = null;
    await watch.onTerminal(state);
  }

  void tick();
}
