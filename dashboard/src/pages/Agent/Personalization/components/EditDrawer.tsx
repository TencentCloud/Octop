import { Drawer, Button, Input, Switch, Spin } from "antd";
import { Copy, Eye, Pencil, Save, Undo2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import Markdown from "../../../../components/Markdown/LazyMarkdown";
import { stripFrontmatter } from "../../../../utils/markdown";
import type { FileEditorState } from "../hooks/useFileEditor";
import styles from "../index.module.less";

/** Actions the drawer needs — a subset of FileEditorActions with save simplified */
export interface DrawerActions {
  toggleMarkdown: (show?: boolean) => void;
  copyToClipboard: () => Promise<void>;
  setContent: (value: string) => void;
  reset: () => void;
  save: () => void;
}

interface EditDrawerProps {
  open: boolean;
  title: React.ReactNode;
  state: FileEditorState;
  actions: DrawerActions;
  readOnly?: boolean;
  onClose: () => void;
}

export default function EditDrawer({
  open,
  title,
  state,
  actions,
  readOnly = false,
  onClose,
}: EditDrawerProps) {
  const { t } = useTranslation();

  return (
    <Drawer
      width={560}
      placement="right"
      open={open}
      onClose={onClose}
      destroyOnHidden
      title={title}
    >
      <div className={styles.drawerContent}>
        {/* Toolbar */}
        <div className={styles.contentLabel}>
          <div>{t("common.content")}</div>
          <div className={styles.buttonGroup}>
            {!readOnly && (
              <div className={styles.markdownToggle}>
                <span className={styles.toggleLabel}>
                  {t("common.preview")}
                </span>
                <Switch
                  checked={state.showMarkdown}
                  onChange={(v) => actions.toggleMarkdown(v)}
                  size="small"
                />
              </div>
            )}
            <Button
              icon={<Copy size={16} />}
              type="text"
              onClick={actions.copyToClipboard}
              className={styles.copyButton}
              aria-label="Copy"
            />
          </div>
        </div>

        {/* Content area */}
        {state.loading ? (
          <div className={styles.loadingState}>
            <Spin />
          </div>
        ) : readOnly ? (
          /* Read-only mode */
          <div className={styles.readOnlyContent}>
            <div className={styles.readOnlyBanner}>
              <Eye size={14} />
              <span>{t("scenes.readOnlyHint")}</span>
            </div>
            <Markdown
              content={stripFrontmatter(state.content)}
              className={styles.markdownViewer}
            />
          </div>
        ) : state.showMarkdown ? (
          /* Markdown preview (click to edit) */
          <div
            className={styles.markdownClickable}
            onClick={() => actions.toggleMarkdown(false)}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                actions.toggleMarkdown(false);
              }
            }}
          >
            <div className={styles.editHintBanner}>
              <Pencil size={14} />
              <span>{t("personalization.clickToEditContent")}</span>
            </div>
            <Markdown
              content={stripFrontmatter(state.content)}
              className={styles.markdownViewer}
            />
          </div>
        ) : (
          /* Edit mode */
          <Input.TextArea
            value={state.content}
            onChange={(e) => actions.setContent(e.target.value)}
            className={styles.textarea}
            placeholder={t("common.contentPlaceholder")}
            autoSize={{ minRows: 20 }}
            autoFocus
          />
        )}

        {/* Bottom actions (only for editable mode) */}
        {!readOnly && (
          <div className={styles.bottomActions}>
            <Button
              onClick={actions.reset}
              disabled={!state.hasChanges}
              icon={<Undo2 size={14} />}
            >
              {t("common.reset")}
            </Button>
            <Button
              type="primary"
              onClick={actions.save}
              disabled={!state.hasChanges}
              loading={state.saving}
              icon={<Save size={14} />}
            >
              {t("common.save")}
            </Button>
          </div>
        )}
      </div>
    </Drawer>
  );
}
