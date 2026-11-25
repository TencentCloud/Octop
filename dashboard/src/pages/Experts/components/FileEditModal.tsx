// dashboard/src/pages/Experts/components/FileEditModal.tsx
import { useEffect, useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button, Drawer, Form, Input, Spin } from "antd";
import { message } from "@/utils/antdMessage";

import { request } from "../../../api/request";
import { withFromWorkspace } from "../../../utils/fromWorkspace";
import styles from "./FileEditModal.module.less";

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
  createLocalFile?: {
    existingNames: string[];
    onCreate: (filename: string, content: string) => void;
  };
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
  createLocalFile,
}: FileEditModalProps) {
  const { t } = useTranslation();
  const newNameId = useId();
  const creating = Boolean(createLocalFile);
  const editingLocally = Boolean(onLocalSave);
  const [newName, setNewName] = useState("");
  const [nameError, setNameError] = useState("");
  const [value, setValue] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    if (creating) {
      setNewName("");
      setNameError("");
      setValue("");
      setLoading(false);
      return;
    }
    if (!filePath) return;
    if (editingLocally) {
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
      .catch(() => {
        if (!cancelled) setValue("");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [open, agentId, filePath, localValue, editingLocally, creating]);

  const handleSave = async () => {
    if (createLocalFile) {
      const input = newName.trim();
      const filename = input.endsWith(".md") ? input : `${input}.md`;
      if (!/^[A-Za-z0-9][A-Za-z0-9._-]*\.md$/.test(filename)) {
        setNameError(t("experts.promptFilenameInvalid"));
        return;
      }
      if (
        createLocalFile.existingNames.some(
          (name) => name.toLowerCase() === filename.toLowerCase(),
        )
      ) {
        setNameError(t("experts.promptFilenameExists", { filename }));
        return;
      }
      createLocalFile.onCreate(filename, value);
      onClose();
      return;
    }
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

  const title = creating
    ? t("experts.addPromptFile")
    : filePath
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
      {creating && (
        <Form.Item
          label={t("workspace.newFileName")}
          htmlFor={newNameId}
          validateStatus={nameError ? "error" : undefined}
          help={nameError}
          style={{ padding: "16px 20px 0" }}
        >
          <Input
            id={newNameId}
            aria-invalid={Boolean(nameError)}
            autoFocus
            value={newName}
            onChange={(event) => {
              setNewName(event.target.value);
              setNameError("");
            }}
          />
        </Form.Item>
      )}
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
        <textarea
          className={styles.editor}
          aria-label={title}
          value={value}
          spellCheck={false}
          autoFocus={!creating}
          onChange={(event) => setValue(event.target.value)}
        />
      )}
    </Drawer>
  );
}
