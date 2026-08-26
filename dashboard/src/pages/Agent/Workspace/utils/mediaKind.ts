export type MediaKind = "image" | "video" | "audio";

const IMAGE_EXT = new Set([
  "png",
  "jpg",
  "jpeg",
  "gif",
  "webp",
  "bmp",
  "svg",
  "ico",
  "avif",
]);

const VIDEO_EXT = new Set([
  "mp4",
  "webm",
  "mov",
  "m4v",
  "ogv",
  "mkv",
  "avi",
  "mpeg",
  "mpg",
]);

const AUDIO_EXT = new Set([
  "mp3",
  "wav",
  "ogg",
  "m4a",
  "aac",
  "flac",
  "opus",
  "weba",
]);

export function getMediaKind(path: string): MediaKind | null {
  const ext = path.split(".").pop()?.toLowerCase() ?? "";
  if (IMAGE_EXT.has(ext)) return "image";
  if (VIDEO_EXT.has(ext)) return "video";
  if (AUDIO_EXT.has(ext)) return "audio";
  return null;
}
