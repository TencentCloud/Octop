import { Collapse, Button, Tooltip, theme } from "antd";

import { useTextOverflow } from "./useTextOverflow";
import styles from "./expertDrawer.module.less";

export interface ExpertPreviewFile {
  /** Stable key. */
  key: string;
  /** Primary label (localized meta label or display name). */
  label: string;
  /** Secondary monospace path/name. */
  path: string;
  /** File content shown in the preview body. */
  content: string;
}

function PreviewLabelText({
  text,
  className,
}: {
  text: string;
  className: string;
}) {
  const { ref, tooltip } = useTextOverflow<HTMLSpanElement>(text, className);

  return (
    <Tooltip title={tooltip} trigger={["hover", "focus"]}>
      <span ref={ref} className={className} tabIndex={tooltip ? 0 : undefined}>
        {text}
      </span>
    </Tooltip>
  );
}

/**
 * Inline file preview list shared by the create / managed / team drawers
 * (decision: keep inline previews, only compress nesting and unify font
 * sizes). One level of antd Collapse (size="small"); every row offers an
 * inline "edit" action via `onEdit`.
 */
export default function ExpertFilePreviewList({
  files,
  onEdit,
  editLabel,
  defaultActiveKeys,
}: {
  files: ExpertPreviewFile[];
  /** Called with the file key when the inline edit action is clicked. */
  onEdit?: (key: string) => void;
  /** Label for the edit action (e.g. t("experts.editFile")). */
  editLabel?: string;
  /** Keys expanded by default; defaults to all (single-level preview). */
  defaultActiveKeys?: string[];
}) {
  const { token } = theme.useToken();
  if (files.length === 0) return null;

  return (
    <Collapse
      className={styles.previewList}
      size="small"
      defaultActiveKey={
        defaultActiveKeys ? defaultActiveKeys : files.map((file) => file.key)
      }
      items={files.map((file) => ({
        key: file.key,
        styles: {
          body: {
            paddingBlock: 6,
            // Small Collapse positions its leading arrow at paddingSM.
            paddingInlineStart: token.paddingSM,
            paddingInlineEnd: token.paddingXS,
          },
        },
        label: (
          <span className={styles.previewLabel}>
            <PreviewLabelText
              text={file.label}
              className={styles.previewLabelText}
            />
            <PreviewLabelText
              text={file.path}
              className={styles.previewLabelPath}
            />
          </span>
        ),
        extra: onEdit ? (
          <Button
            type="link"
            size="small"
            onClick={(event) => {
              event.stopPropagation();
              onEdit(file.key);
            }}
          >
            {editLabel}
          </Button>
        ) : undefined,
        children: <pre className={styles.previewContent}>{file.content}</pre>,
      }))}
    />
  );
}
