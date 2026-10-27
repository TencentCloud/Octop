import { useEffect, useRef, useState } from "react";
import { Button, Spin } from "antd";
import { useTranslation } from "react-i18next";
import { request } from "../../../api/request";
import HtmlArtifactPreview from "../../../components/HtmlArtifactPreview";
import { isNotFoundApiError } from "../../../utils/apiError";
import { toWorkspaceApiPath } from "../utils/dockFilePath";

export default function InlineHtmlArtifact({
  agentId,
  path,
  title,
}: {
  agentId: string;
  path: string;
  title: string;
}) {
  const { t } = useTranslation();
  const host = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  const [content, setContent] = useState<string | null>(null);
  const [error, setError] = useState<"missing" | "error" | null>(null);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const element = host.current;
    if (!element) return;
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) {
        setVisible(true);
        observer.disconnect();
      }
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    setContent(null);
    setError(null);
    if (!visible) return;
    const controller = new AbortController();
    void request<{ content: string }>(
      `/agents/${encodeURIComponent(
        agentId,
      )}/workspace/file?path=${encodeURIComponent(
        toWorkspaceApiPath(path),
      )}&from_workspace=false`,
      { signal: controller.signal },
    ).then(
      (result) => {
        if (!controller.signal.aborted) setContent(result.content);
      },
      (err: unknown) => {
        if (!controller.signal.aborted)
          setError(isNotFoundApiError(err) ? "missing" : "error");
      },
    );
    return () => controller.abort();
  }, [agentId, path, visible, retry]);
  return (
    <div ref={host} style={{ minHeight: 200 }}>
      {error ? (
        <div role="alert" style={{ padding: 16 }}>
          <p>
            {t(
              error === "missing"
                ? "workspace.fileMaybeDeleted"
                : "workspace.mediaLoadFailed",
            )}
          </p>
          <Button onClick={() => setRetry((value) => value + 1)}>
            {t("workspace.retryPreview")}
          </Button>
        </div>
      ) : content !== null ? (
        <HtmlArtifactPreview content={content} title={title} mode="inline" />
      ) : (
        <div role="status" style={{ padding: 24 }}>
          <Spin />
        </div>
      )}
    </div>
  );
}
