import type { DownloadState } from "../api/types/embedding";

export function formatBytes(value?: number): string {
  if (value === undefined || value === null || Number.isNaN(value)) {
    return "0 B";
  }

  if (value < 1024) {
    return `${value} B`;
  }

  const units = ["KB", "MB", "GB", "TB"];
  let current = value / 1024;
  let unitIndex = 0;
  while (current >= 1024 && unitIndex < units.length - 1) {
    current /= 1024;
    unitIndex += 1;
  }

  const digits = current >= 100 ? 0 : current >= 10 ? 1 : 2;
  return `${current.toFixed(digits)} ${units[unitIndex]}`;
}

/** Approximate ONNX catalog size from gigabytes (fastembed `size_in_GB`). */
export function formatSizeGb(sizeGb?: number | null): string | null {
  if (sizeGb == null || Number.isNaN(sizeGb) || sizeGb < 0) {
    return null;
  }
  if (sizeGb < 1) {
    const mb = sizeGb * 1024;
    return `${mb >= 10 ? mb.toFixed(0) : mb.toFixed(1)} MB`;
  }
  return `${sizeGb < 10 ? sizeGb.toFixed(1) : sizeGb.toFixed(0)} GB`;
}

export function formatDuration(seconds?: number): string {
  if (seconds === undefined || seconds === null || Number.isNaN(seconds)) {
    return "0s";
  }

  const totalSeconds = Math.max(0, Math.round(seconds));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const secs = totalSeconds % 60;

  if (hours > 0) {
    return `${hours}h ${minutes}m`;
  }
  if (minutes > 0) {
    return `${minutes}m ${secs}s`;
  }
  return `${secs}s`;
}

export function getDownloadTransferred(state: DownloadState): string {
  if (state.total_bytes && state.total_bytes > 0) {
    return `${formatBytes(state.downloaded_bytes)} / ${formatBytes(
      state.total_bytes,
    )}`;
  }
  return formatBytes(state.downloaded_bytes);
}

export function getDownloadSpeed(state: DownloadState): string {
  if (!state.speed_bytes_per_sec || state.speed_bytes_per_sec <= 0) {
    return "-";
  }
  return `${formatBytes(state.speed_bytes_per_sec)}/s`;
}
