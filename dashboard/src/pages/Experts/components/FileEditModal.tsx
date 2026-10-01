// dashboard/src/pages/Experts/components/FileEditModal.tsx
import { lazy, Suspense, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button, Drawer, Modal, Spin } from "antd";
import { message } from "@/utils/antdMessage";

import { request } from "../../../api/request";
import { withFromWorkspace } from "../../../utils/fromWorkspace";

const MonacoEditor = lazy(() => import("@monaco-editor/react"));

interface FileEditModalProps {
  open: boolean;
  agentId?: string;
  /** Workspace path, e.g. "/SOUL.md" */
  filePath: string | null;
  /** When set, edit this value in memory instead of loading from the workspace. */
  localValue?: string;
  onClose: () => void;
  onSaved: () => void;
  onLocalSave?: (content: string) => void;
}

function fileEditDrawerWidth(): number {
  if (typeof window === "undefined") return 880;
  return Math.min(880, window.innerWidth - 16);
}

export default function FileEditModal({
  open,
  agentId,
  filePath,
  localValue,
  onClose,
  onSaved,
  onLocalSave,
}: FileEditModalProps) {
  const { t } = useTranslation();
  const [value, setValue] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [confirmClose, setConfirmClose] = useState(false);

  useEffect(() => {
    if (!open) {
      setDirty(false);
      setConfirmClose(false);
    }
  }, [open]);

  const requestClose = () => {
    // FE-2: silently discarding edits loses work with no confirm, no toast,
    // no undo — ask before closing whenever the editor is dirty.
    if (dirty && !saving) {
      setConfirmClose(true);
      return;
    }
    onClose();
  };

  useEffect(() => {
    if (!open || !filePath) return;
    if (onLocalSave) {
      setValue(localValue ?? "");
      setLoading(false);
      return;
    }
    if (!agentId) return;
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
      .catch((err: unknown) => {
        // FE-2: an empty editor pre-filled on failure lets a save overwrite
        // the real file. Show the error and leave the editor empty-but-clean
        // so the user must explicitly re-load before saving.
        if (!cancelled) {
          setValue("");
          message.error(
            (err instanceof Error ? err.message : String(err)) ||
              t("experts.fileLoadFailed", {
                filename: filePath.replace(/^\//, ""),
              }),
          );
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [open, agentId, filePath, localValue, onLocalSave]);

  const handleSave = async () => {
    if (!filePath) return;
    const filename = filePath.replace(/^\//, "");
    if (onLocalSave) {
      onLocalSave(value);
      message.success(t("experts.fileSaved", { filename }));
      onSaved();
      onClose();
      return;
    }
    if (!agentId) return;
    setSaving(true);
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
      onClose={requestClose}
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
          <Button onClick={requestClose} disabled={saving}>
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
              onChange={(v) => {
                setValue(v ?? "");
                setDirty(true);
              }}
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
      <Modal
        open={confirmClose}
        title={t("experts.unsavedChangesTitle")}
        onCancel={() => setConfirmClose(false)}
        footer={[
          <Button key="cancel" onClick={() => setConfirmClose(false)}>
            {t("experts.unsavedChangesKeepEditing")}
          </Button>,
          <Button
            key="discard"
            danger
            onClick={() => {
              setConfirmClose(false);
              setDirty(false);
              onClose();
            }}
          >
            {t("experts.unsavedChangesDiscard")}
          </Button>,
        ]}
      >
        <p>{t("experts.unsavedChangesBody")}</p>
      </Modal>
    </Drawer>
  );
}
