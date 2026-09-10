// dashboard/src/pages/Experts/components/FileEditModal.tsx
import { lazy, Suspense, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button, Drawer, Spin } from "antd";
import { message } from "@/utils/antdMessage";

import { request } from "../../../api/request";
import { withFromWorkspace } from "../../../utils/fromWorkspace";

const MonacoEditor = lazy(() => import("@monaco-editor/react"));

interface FileEditModalProps {
  open: boolean;
  agentId: string;
  /** Workspace path, e.g. "/SOUL.md" */
  filePath: string | null;
  onClose: () => void;
  onSaved: () => void;
}

function fileEditDrawerWidth(): number {
  if (typeof window === "undefined") return 880;
  return Math.min(880, window.innerWidth - 16);
}

export default function FileEditModal({
  open,
  agentId,
  filePath,
  onClose,
  onSaved,
}: FileEditModalProps) {
  const { t } = useTranslation();
  const [value, setValue] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open || !agentId || !filePath) return;
    let cancelled = false;
    setLoading(true);
    setValue("");

    request<{ content: string }>(
      withFromWorkspace(
        `/agents/${agentId}/workspace/file?path=${encodeURIComponent(
          filePath,
        )}`,
      ),
    )
      .then((data) => {
        if (!cancelled) setValue(data.content ?? "");
      })
      .catch(() => {
        if (!cancelled) setValue("");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [open, agentId, filePath]);

  const handleSave = async () => {
    if (!filePath) return;
    setSaving(true);
    const filename = filePath.replace(/^\//, "");
    try {
      await request(
        withFromWorkspace(
          `/agents/${agentId}/workspace/file?path=${encodeURIComponent(
            filePath,
          )}`,
        ),
        { method: "PUT", body: JSON.stringify({ content: value }) },
      );
      await request(`/agents/${agentId}/reload`, { method: "POST" });
      message.success(t("experts.fileSaved", { filename }));
      onSaved();
      onClose();
    } catch {
      message.error(t("experts.fileSaveFailed", { filename }));
    } finally {
      setSaving(false);
    }
  };

  const title = filePath
    ? t("experts.editFileTitle", { filename: filePath.replace(/^\//, "") })
    : "";

  return (
    <Drawer
      open={open}
      placement="right"
      title={title}
      width={fileEditDrawerWidth()}
      onClose={onClose}
      destroyOnHidden
      styles={{
        body: {
          padding: 0,
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
        },
        footer: { padding: "12px 20px" },
      }}
      footer={
        <div
          style={{
            display: "flex",
            justifyContent: "flex-end",
            gap: 8,
          }}
        >
          <Button onClick={onClose} disabled={saving}>
            {t("common.cancel")}
          </Button>
          <Button
            type="primary"
            loading={saving}
            onClick={() => void handleSave()}
          >
            {t("common.save")}
          </Button>
        </div>
      }
    >
      {loading ? (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flex: 1,
            minHeight: 240,
          }}
        >
          <Spin />
        </div>
      ) : (
        <Suspense
          fallback={
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                flex: 1,
                minHeight: 240,
              }}
            >
              <Spin tip="Loading editor…" />
            </div>
          }
        >
          <div style={{ flex: 1, minHeight: 0, height: "100%" }}>
            <MonacoEditor
              height="100%"
              language="markdown"
              value={value}
              onChange={(v) => setValue(v ?? "")}
              options={{
                minimap: { enabled: false },
                wordWrap: "on",
                fontSize: 13,
                lineNumbers: "on",
                scrollBeyondLastLine: false,
              }}
            />
          </div>
        </Suspense>
      )}
    </Drawer>
  );
}
