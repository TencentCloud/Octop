/**
 * Resolve tool-result media URLs for dashboard display.
 */

export type ToolMediaItem = {
  url: string;
  filename?: string;
  kind: "image" | "video";
  mimeType?: string;
};

export function isFileMediaUrl(url: string): boolean {
  const trimmed = url.trim();
  return trimmed.startsWith("file://") || trimmed.startsWith("/");
}

export function isDataUrl(url: string): boolean {
  return url.startsWith("data:");
}

/** URLs that require Authorization and must be fetched via requestBlob. */
export function needsAuthBlobFetch(url: string): boolean {
  const path = url.startsWith("http")
    ? new URL(url).pathname
    : url.split("?")[0];
  if (path === "/api/workspace/media") return true;
  if (/^\/api\/agents\/[^/]+\/media\/preview$/.test(path)) return true;
  if (/^\/api\/agents\/[^/]+\/workspace\/download$/.test(path)) return true;
  return false;
}

export function agentMediaPreviewUrl(
  agentId: string,
  source: string,
  mimeType?: string,
): string {
  const params = new URLSearchParams({ source });
  if (mimeType) params.set("mime_type", mimeType);
  return `/api/agents/${encodeURIComponent(
    agentId,
  )}/media/preview?${params.toString()}`;
}

/** Extract ``inbound/…`` or ``outbound/…`` from dashboard media/download API URLs. */
export function workspacePathFromAccessUrl(url: string): string | undefined {
  try {
    const parsed = url.startsWith("http")
      ? new URL(url)
      : new URL(url, "http://octop.local");
    for (const key of ["source", "path"] as const) {
      const raw = parsed.searchParams.get(key);
      if (!raw) continue;
      const rel = extractWorkspaceRel(raw);
      if (rel) return rel;
    }
  } catch {
    return undefined;
  }
  return undefined;
}

/**
 * Normalize an arbitrary harness-reported file path into a workspace-relative
 * fragment the backend ``download`` endpoint can resolve.
 *
 * Harness tool output often reports an absolute path such as
 * ``/workspace/report.pdf`` (where ``/workspace`` *is* the workspace root) or a
 * ``file:///workspace/…`` URL. The workspace tree and the ``media/preview``
 * endpoint treat such paths as relative to the workspace dir, but the
 * ``download`` endpoint only strips a leading slash. Mirroring that
 * normalization here makes chat file cards open exactly like the workspace
 * viewer, which always passes a relative path such as ``report.pdf``.
 */
export function toWorkspaceRel(rawPath: string): string {
  let p = rawPath.trim();
  if (!p) return "";
  if (p.startsWith("file://")) p = p.slice("file://".length);
  const marker = "/workspace/";
  const idx = p.lastIndexOf(marker);
  if (idx >= 0) {
    p = p.slice(idx + marker.length);
  } else if (p === "/workspace") {
    p = "";
  } else if (p.startsWith("/workspace")) {
    p = p.slice("/workspace".length);
  }
  return p.replace(/^\/+/, "");
}

/** Extract a workspace-relative fragment from a filesystem / file-URL / tool path. */
export function extractWorkspaceRel(path: string): string | null {
  const rel = toWorkspaceRel(path);
  return rel || null;
}

/** Read agent id embedded in ``…/agents/{id}/…`` workspace paths. */
export function agentIdFromWorkspacePath(path: string): string | null {
  const match = path.match(/\/agents\/([A-Z0-9]+)\//i);
  return match?.[1] ?? null;
}

export function workspaceDownloadUrl(
  agentId: string,
  workspaceRel: string,
): string {
  const rel = toWorkspaceRel(workspaceRel);
  const safe = rel || "";
  return `/api/agents/${encodeURIComponent(
    agentId,
  )}/workspace/download?path=${encodeURIComponent(`/${safe}`)}`;
}

/**
 * Dashboard access URL for an attachment: images/videos use media preview;
 * everything else uses workspace download (JWT blob fetch).
 */
export function agentAttachmentAccessUrl(
  agentId: string,
  workspacePath: string,
  mimeType?: string,
): string {
  const mime = (mimeType || "").toLowerCase();
  if (mime.startsWith("image/") || mime.startsWith("video/")) {
    return agentMediaPreviewUrl(agentId, workspacePath, mimeType);
  }
  return workspaceDownloadUrl(agentId, workspacePath);
}

export function guessImageMime(
  filename?: string,
  fallback = "image/png",
): string {
  const ext = (filename || "").split(".").pop()?.toLowerCase();
  if (ext === "jpg" || ext === "jpeg") return "image/jpeg";
  if (ext === "gif") return "image/gif";
  if (ext === "webp") return "image/webp";
  if (ext === "svg") return "image/svg+xml";
  if (ext === "bmp") return "image/bmp";
  return fallback;
}

export function asImageBlob(blob: Blob, filename?: string): Blob {
  if (blob.type && blob.type !== "application/octet-stream") return blob;
  return new Blob([blob], { type: guessImageMime(filename) });
}

function resolveMediaAgentId(chatAgentId: string, rawPath: string): string {
  return agentIdFromWorkspacePath(rawPath) || chatAgentId;
}

/** Rewrite mistaken ``workspace/download?path=/abs/…`` or cross-agent ``media/preview`` links. */
export function canonicalizeMediaApiUrl(
  url: string,
  chatAgentId?: string | null,
): string {
  try {
    const parsed = url.startsWith("http")
      ? new URL(url)
      : new URL(url, "http://octop.local");
    const pathMatch = parsed.pathname.match(
      /^\/api\/agents\/([^/]+)\/(media\/preview|workspace\/download)$/,
    );
    if (!pathMatch) return url;

    const urlAgent = pathMatch[1];
    const endpoint = pathMatch[2];

    if (endpoint === "workspace/download") {
      const pathParam = parsed.searchParams.get("path") || "";
      const rel = extractWorkspaceRel(pathParam);
      if (rel) {
        const mediaAgent = agentIdFromWorkspacePath(pathParam) || urlAgent;
        return workspaceDownloadUrl(mediaAgent, rel);
      }
      return url;
    }

    const source = parsed.searchParams.get("source") || "";
    if (!source) return url;
    const rel = extractWorkspaceRel(source);
    const mediaAgent =
      agentIdFromWorkspacePath(source) || chatAgentId || urlAgent;
    const mimeType = parsed.searchParams.get("mime_type") || undefined;
    if (rel) {
      return workspaceDownloadUrl(mediaAgent, rel);
    }
    if (mediaAgent !== urlAgent && source.startsWith("file://")) {
      return agentMediaPreviewUrl(mediaAgent, source, mimeType);
    }
  } catch {
    return url;
  }
  return url;
}

export function normalizeStoredMediaUrl(
  agentId: string | null | undefined,
  url: string,
): string {
  if (!url.includes("/api/agents/")) return url;
  const canonical = canonicalizeMediaApiUrl(url, agentId);
  if (canonical !== url) return canonical;

  if (!agentId || !url.includes("/workspace/download?")) return url;
  try {
    const parsed = url.startsWith("http")
      ? new URL(url)
      : new URL(url, "http://octop.local");
    const pathParam = parsed.searchParams.get("path") || "";
    if (!pathParam) return url;
    const rel = extractWorkspaceRel(pathParam);
    if (rel) {
      const mediaAgent = agentIdFromWorkspacePath(pathParam) || agentId;
      return workspaceDownloadUrl(mediaAgent, rel);
    }
  } catch {
    return url;
  }
  return url;
}

/**
 * Turn harness tool-result media references into browser-loadable URLs.
 */
export function resolveToolMediaUrl(
  agentId: string | null | undefined,
  rawUrl: string,
  options?: { previewUrl?: string; mimeType?: string },
): string {
  const preview = options?.previewUrl?.trim();
  if (preview) {
    const normalized = agentId
      ? canonicalizeMediaApiUrl(
          normalizeStoredMediaUrl(agentId, preview),
          agentId,
        )
      : canonicalizeMediaApiUrl(preview);
    if (
      normalized.startsWith("/api/") ||
      normalized.startsWith("http") ||
      isDataUrl(normalized)
    ) {
      return normalized;
    }
  }

  const url = rawUrl.trim();
  if (!url) return preview || "";

  if (
    isDataUrl(url) ||
    url.startsWith("http://") ||
    url.startsWith("https://")
  ) {
    return url;
  }

  if (url.startsWith("/api/agents/")) {
    return url;
  }

  if (
    agentId &&
    (isFileMediaUrl(url) ||
      url.startsWith("outbound/") ||
      url.startsWith("/outbound/"))
  ) {
    const rel = extractWorkspaceRel(url);
    const mediaAgent = resolveMediaAgentId(agentId, url);
    if (rel) {
      return workspaceDownloadUrl(mediaAgent, rel);
    }
    const source =
      url.startsWith("outbound/") || url.startsWith("inbound/")
        ? `file://${url}`
        : url;
    return agentMediaPreviewUrl(mediaAgent, source, options?.mimeType);
  }

  return preview || url;
}

export interface StructuredToolMedia {
  images: ToolMediaItem[];
  videos: ToolMediaItem[];
  files: Array<{ url: string; filename?: string }>;
  textOutput: string;
}

function mediaBlocksFromParsed(parsed: unknown): Record<string, unknown>[] {
  if (Array.isArray(parsed)) {
    return parsed.filter(
      (block) => block && typeof block === "object",
    ) as Record<string, unknown>[];
  }
  if (parsed && typeof parsed === "object") {
    const obj = parsed as Record<string, unknown>;
    if (typeof obj.type === "string") {
      return [obj];
    }
  }
  return [];
}

export function parseStructuredToolOutput(
  rawOutput: string | undefined,
  agentId?: string | null,
): StructuredToolMedia {
  if (!rawOutput) {
    return { images: [], videos: [], files: [], textOutput: "" };
  }

  try {
    const parsed = JSON.parse(rawOutput);
    const blocks = mediaBlocksFromParsed(parsed);
    if (blocks.length === 0) {
      return fallbackTextToolMedia(rawOutput, agentId);
    }

    const images: ToolMediaItem[] = [];
    const videos: ToolMediaItem[] = [];
    const files: Array<{ url: string; filename?: string }> = [];
    const textParts: string[] = [];

    for (const typedBlock of blocks) {
      const type = String(typedBlock.type || "");
      const source = typedBlock.source as
        | { type?: string; url?: string; media_type?: string; data?: string }
        | undefined;
      const previewUrl =
        typeof typedBlock.preview_url === "string"
          ? typedBlock.preview_url
          : undefined;
      const filename =
        typeof typedBlock.filename === "string"
          ? typedBlock.filename
          : undefined;
      const workspacePath =
        typeof typedBlock.path === "string"
          ? typedBlock.path
          : typeof typedBlock.workspace_path === "string"
          ? typedBlock.workspace_path
          : undefined;
      const mimeType =
        (typeof source?.media_type === "string"
          ? source.media_type
          : undefined) ||
        (typeof typedBlock.media_type === "string"
          ? typedBlock.media_type
          : undefined) ||
        (typeof typedBlock.mime_type === "string"
          ? typedBlock.mime_type
          : undefined);

      if (
        type === "text" &&
        typeof typedBlock.text === "string" &&
        typedBlock.text
      ) {
        textParts.push(typedBlock.text);
        continue;
      }

      if (type === "image") {
        if (source?.type === "base64" && source.data) {
          images.push({
            url: `data:${mimeType || "image/png"};base64,${source.data}`,
            filename,
            kind: "image",
            mimeType,
          });
          continue;
        }
        const raw = source?.type === "url" && source.url ? source.url : "";
        const resolved = resolveToolMediaUrl(agentId, raw, {
          previewUrl,
          mimeType,
        });
        if (resolved) {
          images.push({ url: resolved, filename, kind: "image", mimeType });
        }
        continue;
      }

      if (type === "video") {
        const raw = source?.type === "url" && source.url ? source.url : "";
        const resolved = resolveToolMediaUrl(agentId, raw, {
          previewUrl,
          mimeType,
        });
        if (resolved) {
          videos.push({ url: resolved, filename, kind: "video", mimeType });
        }
        continue;
      }

      if (type === "audio" || type === "file") {
        const rel =
          (workspacePath && extractWorkspaceRel(workspacePath)) ||
          workspacePath ||
          null;
        if (type === "file" && agentId && rel) {
          files.push({
            url: workspaceDownloadUrl(agentId, rel),
            filename,
          });
          continue;
        }
        const raw = source?.type === "url" && source.url ? source.url : "";
        const resolved = resolveToolMediaUrl(agentId, raw, {
          previewUrl,
          mimeType,
        });
        if (resolved) {
          files.push({ url: resolved, filename });
        }
      }
    }

    const textOutput = textParts.join("\n").trim();
    if (images.length === 0 && agentId && textOutput) {
      const path = extractImagePathFromText(textOutput);
      if (path) {
        images.push(imageItemFromPath(agentId, path));
      }
    }

    return {
      images,
      videos,
      files,
      textOutput,
    };
  } catch {
    return fallbackTextToolMedia(rawOutput, agentId);
  }
}

const IMAGE_EXT = "(?:png|jpe?g|gif|webp|bmp|svg)";

/** Pull a filesystem image path from plain tool output (browser screenshot, send_file). */
export function extractImagePathFromText(text: string): string | null {
  const trimmed = text.trim();
  if (!trimmed) return null;

  const patterns = [
    new RegExp(
      `(?:saved to|written to|file(?:\\s+path)?[:\\s]+)\\s*([^\\s(]+\\.${IMAGE_EXT})`,
      "i",
    ),
    new RegExp(`(file://[^\\s"'()]+\\.${IMAGE_EXT})`, "i"),
    new RegExp(`(/[^\\s"'()]+/outbound/[^\\s"'()]+\\.${IMAGE_EXT})`, "i"),
    new RegExp(`(/Users/[^\\s"'()]+\\.${IMAGE_EXT})`, "i"),
    new RegExp(`(/tmp/[^\\s"'()]+\\.${IMAGE_EXT})`, "i"),
  ];

  for (const re of patterns) {
    const match = trimmed.match(re);
    if (match?.[1]) return match[1];
  }
  return null;
}

/** Read ``file_path`` / ``path`` from tool-call JSON arguments. */
export function extractImagePathFromToolArgs(
  argumentsJson: string | undefined,
): string | null {
  if (!argumentsJson?.trim()) return null;
  try {
    const args = JSON.parse(argumentsJson) as Record<string, unknown>;
    const candidates = [args.file_path, args.path, args.filepath, args.source];
    for (const raw of candidates) {
      if (typeof raw !== "string" || !raw.trim()) continue;
      if (new RegExp(`\\.${IMAGE_EXT}$`, "i").test(raw.trim())) {
        return raw.trim();
      }
    }
  } catch {
    const match = argumentsJson.match(
      /"(?:file_path|path|filepath)"\s*:\s*"([^"]+\.(?:png|jpe?g|gif|webp|bmp|svg))"/i,
    );
    if (match?.[1]) return match[1];
  }
  return null;
}

function imageItemFromPath(
  chatAgentId: string,
  rawPath: string,
): ToolMediaItem {
  const agentId = resolveMediaAgentId(chatAgentId, rawPath);
  const rel = extractWorkspaceRel(rawPath);
  if (rel) {
    return {
      url: workspaceDownloadUrl(agentId, rel),
      filename: rawPath.split("/").pop(),
      kind: "image",
    };
  }
  const path = rawPath.startsWith("file://") ? rawPath : `file://${rawPath}`;
  return {
    url: agentMediaPreviewUrl(agentId, path),
    filename: rawPath.split("/").pop(),
    kind: "image",
  };
}

function withCanonicalUrls(
  items: ToolMediaItem[],
  chatAgentId?: string | null,
): ToolMediaItem[] {
  if (!chatAgentId) return items;
  return items.map((item) => ({
    ...item,
    url: canonicalizeMediaApiUrl(item.url, chatAgentId),
  }));
}

function dedupeByUrl<T extends { url: string }>(items: T[]): T[] {
  const seen = new Set<string>();
  return items.filter((item) => {
    if (seen.has(item.url)) return false;
    seen.add(item.url);
    return true;
  });
}

/** When tool output is plain text (e.g. browser screenshot summary), infer image path. */
function fallbackTextToolMedia(
  rawOutput: string,
  agentId?: string | null,
): StructuredToolMedia {
  const images: ToolMediaItem[] = [];
  if (agentId) {
    const path = extractImagePathFromText(rawOutput);
    if (path) {
      images.push(imageItemFromPath(agentId, path));
    }
  }
  return { images, videos: [], files: [], textOutput: rawOutput };
}

export function collectToolMediaFromOutput(
  output: string | undefined,
  agentId?: string | null,
): {
  images: ToolMediaItem[];
  videos: ToolMediaItem[];
  files: Array<{ url: string; filename?: string }>;
} {
  const structured = parseStructuredToolOutput(output, agentId);
  return {
    images: structured.images,
    videos: structured.videos,
    files: structured.files,
  };
}

/** Collect images/videos/files from tool output, call arguments, and streamed attachments. */
export function collectToolMediaFromToolData(
  toolData: { output?: string; arguments?: string; name?: string } | undefined,
  agentId?: string | null,
  attachments?: Array<{
    url?: string;
    kind?: string;
    filename?: string;
    mediaType?: string;
  }>,
): {
  images: ToolMediaItem[];
  videos: ToolMediaItem[];
  files: Array<{ url: string; filename?: string }>;
} {
  const fromOutput = collectToolMediaFromOutput(toolData?.output, agentId);
  const images = [...fromOutput.images];
  const videos = [...fromOutput.videos];
  const files = [...fromOutput.files];

  if (agentId && toolData) {
    const argPath = extractImagePathFromToolArgs(toolData.arguments);
    if (argPath) {
      const already = images.some(
        (img) => img.filename === argPath.split("/").pop(),
      );
      if (!already) {
        images.push(imageItemFromPath(agentId, argPath));
      }
    }
    if (
      images.length === 0 &&
      toolData.output &&
      /send[_-]?file/i.test(toolData.name || "")
    ) {
      const outPath = extractImagePathFromText(toolData.output);
      if (outPath) images.push(imageItemFromPath(agentId, outPath));
    }
  }

  for (const att of attachments || []) {
    if (!att.url) continue;
    if (att.kind === "image") {
      images.push({
        url: agentId ? normalizeStoredMediaUrl(agentId, att.url) : att.url,
        filename: att.filename,
        kind: "image",
        mimeType: att.mediaType,
      });
      continue;
    }
    if (att.kind === "file") {
      files.push({
        url: agentId ? normalizeStoredMediaUrl(agentId, att.url) : att.url,
        filename: att.filename,
      });
    }
  }

  return {
    images: withCanonicalUrls(dedupeByUrl(images), agentId),
    videos: withCanonicalUrls(dedupeByUrl(videos), agentId),
    files: dedupeByUrl(
      files.map((file) => ({
        ...file,
        url: agentId ? canonicalizeMediaApiUrl(file.url, agentId) : file.url,
      })),
    ),
  };
}
