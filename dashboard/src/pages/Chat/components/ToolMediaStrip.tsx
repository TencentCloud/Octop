import { useLayoutEffect, useState } from "react";
import { Image } from "antd";
import { useTranslation } from "react-i18next";
import { requestBlob, getAuthToken } from "../../../api/request";
import { getApiUrl } from "../../../api/config";
import { useAuthImageSrc } from "../../../hooks/useAuthImageSrc";
import {
  needsAuthBlobFetch,
  type ToolMediaItem,
} from "../../../utils/toolMediaBlocks";
import { MessageFileCard } from "./MessageFileCard";
import styles from "../index.module.less";

function RefreshableImage({
  url,
  filename,
  idx,
}: {
  url: string;
  filename?: string;
  idx: number;
}) {
  const { t } = useTranslation();
  const { src, loadState } = useAuthImageSrc(url, filename);

  if (loadState === "error") {
    return (
      <span className={styles.toolMediaFallback}>
        {filename || t("chat.imageLoadFailed")}
      </span>
    );
  }

  if (loadState === "loading" || !src) {
    return <span className={styles.toolMediaFallback}>…</span>;
  }

  return (
    <Image
      src={src}
      alt={filename || `image-${idx}`}
      className={styles.toolMediaImage}
    />
  );
}

function RefreshableVideo({ item }: { item: ToolMediaItem }) {
  const [src, setSrc] = useState<string>("");

  useLayoutEffect(() => {
    let cancelled = false;
    let objectUrl: string | undefined;

    const load = async () => {
      if (needsAuthBlobFetch(item.url)) {
        const apiPath = item.url.replace(/^\/api/, "");
        const blob = await requestBlob(apiPath);
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setSrc(objectUrl);
        return;
      }
      if (item.url.startsWith("/api/")) {
        const token = getAuthToken();
        const base = getApiUrl(item.url.replace(/^\/api/, ""));
        setSrc(
          token
            ? `${base}${
                base.includes("?") ? "&" : "?"
              }token=${encodeURIComponent(token)}`
            : base,
        );
        return;
      }
      setSrc(item.url);
    };

    void load().catch(() => {
      if (!cancelled) setSrc("");
    });

    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [item.url]);

  if (!src) {
    return (
      <span className={styles.toolMediaFallback}>
        {item.filename || "video"}
      </span>
    );
  }

  return (
    <video
      className={styles.toolMediaVideo}
      src={src}
      controls
      preload="metadata"
      playsInline
    />
  );
}

export function ToolMediaStrip({
  images,
  videos,
  files = [],
  agentId,
}: {
  images: ToolMediaItem[];
  videos: ToolMediaItem[];
  files?: Array<{ url: string; filename?: string }>;
  agentId?: string | null;
}) {
  if (images.length === 0 && videos.length === 0 && files.length === 0) {
    return null;
  }

  return (
    <div className={styles.toolMediaStrip}>
      {images.length > 0 && (
        <div className={styles.messageImages}>
          <Image.PreviewGroup>
            {images.map((img, idx) => (
              <RefreshableImage
                key={`${img.url}-${idx}`}
                url={img.url}
                filename={img.filename}
                idx={idx}
              />
            ))}
          </Image.PreviewGroup>
        </div>
      )}
      {videos.map((video, idx) => (
        <RefreshableVideo key={`${video.url}-${idx}`} item={video} />
      ))}
      {files.length > 0 && (
        <div className={styles.messageFiles}>
          {files.map((file, idx) => (
            <MessageFileCard
              key={`${file.url}-${idx}`}
              url={file.url}
              filename={file.filename}
              agentId={agentId}
            />
          ))}
        </div>
      )}
    </div>
  );
}
