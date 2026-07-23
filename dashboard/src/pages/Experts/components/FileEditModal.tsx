// dashboard/src/pages/Experts/components/FileEditModal.tsx
import { lazy, Suspense, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Modal, Spin, message } from "antd";
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
    <Modal
      open={open}
      title={title}
      width="min(860px, 90vw)"
      style={{ top: 40 }}
      styles={{ body: { height: "60vh", padding: 0, overflow: "hidden" } }}
      onCancel={onClose}
      onOk={handleSave}
      okText={t("common.save")}
      cancelText={t("common.cancel")}
      confirmLoading={saving}
      destroyOnClose
    >
      {loading ? (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            height: "100%",
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
                height: "100%",
              }}
            >
              <Spin tip="Loading editor…" />
            </div>
          }
        >
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
        </Suspense>
      )}
    </Modal>
  );
}
