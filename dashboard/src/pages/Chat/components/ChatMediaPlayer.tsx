import { useLayoutEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { requestBlob } from "../../../api/request";
import {
  agentAttachmentAccessUrl,
  isDataUrl,
  needsAuthBlobFetch,
  workspacePathFromAccessUrl,
} from "../../../utils/toolMediaBlocks";
import { MessageFileCard } from "./MessageFileCard";
import styles from "../index.module.less";

function apiPathFromUrl(url: string): string {
  if (url.startsWith("http")) {
    const parsed = new URL(url);
    return parsed.pathname.replace(/^\/api/, "") + parsed.search;
  }
  return url.replace(/^\/api/, "");
}

function typedBlob(blob: Blob, mimeHint?: string): Blob {
  if (blob.type && blob.type !== "application/octet-stream") return blob;
  if (mimeHint) return new Blob([blob], { type: mimeHint });
  return blob;
}

export function ChatMediaPlayer({
  url,
  filename,
  workspacePath,
  mediaType,
  kind,
  agentId,
  compact = false,
}: {
  url: string;
  filename?: string;
  workspacePath?: string;
  mediaType?: string;
  kind: "video" | "audio";
  agentId?: string | null;
  compact?: boolean;
}) {
  const { t } = useTranslation();
  const resolvedUrl = useMemo(() => {
    if (url && !url.startsWith("workspace://")) return url;
    const path =
      workspacePath ||
      (url.startsWith("workspace://")
        ? url.slice("workspace://".length).replace(/^\/+/, "")
        : "") ||
      workspacePathFromAccessUrl(url);
    if (path && agentId) {
      return agentAttachmentAccessUrl(agentId, path, mediaType);
    }
    return url;
  }, [url, workspacePath, agentId, mediaType]);

  const [src, setSrc] = useState("");
  const [loadState, setLoadState] = useState<"loading" | "ready" | "error">(
    "loading",
  );
  const objectUrlRef = useRef<string | undefined>(undefined);

  useLayoutEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        if (!needsAuthBlobFetch(resolvedUrl) && !isDataUrl(resolvedUrl)) {
          if (!cancelled) {
            setSrc(resolvedUrl);
            setLoadState("ready");
          }
          return;
        }
        const blob = isDataUrl(resolvedUrl)
          ? await (await fetch(resolvedUrl)).blob()
          : await requestBlob(apiPathFromUrl(resolvedUrl), {
              cache: "no-store",
            });
        if (cancelled) return;
        const objectUrl = URL.createObjectURL(typedBlob(blob, mediaType));
        if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current);
        objectUrlRef.current = objectUrl;
        setSrc(objectUrl);
        setLoadState("ready");
      } catch {
        if (!cancelled) {
          setSrc("");
          setLoadState("error");
        }
      }
    };

    setLoadState("loading");
    void load();

    return () => {
      cancelled = true;
    };
  }, [resolvedUrl, mediaType]);

  useLayoutEffect(() => {
    return () => {
      if (objectUrlRef.current) {
        URL.revokeObjectURL(objectUrlRef.current);
        objectUrlRef.current = undefined;
      }
    };
  }, []);

  if (loadState === "error" || (loadState === "ready" && !src)) {
    if (!compact) {
      return (
        <MessageFileCard
          url={resolvedUrl || url}
          filename={filename}
          agentId={agentId}
          workspacePath={workspacePath}
        />
      );
    }
    return (
      <span className={styles.attachmentPreviewName}>
        {filename || t("chat.mediaLoadFailed", "Unable to load media")}
      </span>
    );
  }

  if (loadState === "loading" && !src) {
    return (
      <div
        className={
          compact ? styles.composerMediaSkeleton : styles.messageMediaSkeleton
        }
        aria-hidden
      />
    );
  }

  if (kind === "video") {
    return (
      <video
        className={
          compact ? styles.composerMediaVideo : styles.messageMediaVideo
        }
        src={src}
        controls
        playsInline
        preload="metadata"
        aria-label={filename || "video"}
      />
    );
  }

  return (
    <audio
      className={compact ? styles.composerMediaAudio : styles.messageMediaAudio}
      src={src}
      controls
      preload="metadata"
      aria-label={filename || "audio"}
    />
  );
}
