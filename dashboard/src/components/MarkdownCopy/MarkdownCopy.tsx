import { useState, useEffect, useMemo } from "react";
import { Button, Switch, Input } from "antd";
import { message } from "@/utils/antdMessage";

import { Copy } from "lucide-react";
import Markdown from "../Markdown/LazyMarkdown";
import { useTranslation } from "react-i18next";
import type { CSSProperties } from "react";
import { stripFrontmatter } from "../../utils/markdown";
import { copyText } from "../../utils/copyText";
import styles from "./index.module.less";

interface MarkdownCopyProps {
  content: string;
  showMarkdown?: boolean;
  onShowMarkdownChange?: (show: boolean) => void;
  copyButtonProps?: {
    type?: "text" | "link" | "default" | "primary" | "dashed" | undefined;
    size?: "small" | "middle" | "large" | undefined;
    style?: CSSProperties;
  };
  markdownViewerProps?: {
    style?: CSSProperties;
    className?: string;
  };
  textareaProps?: {
    rows?: number;
    placeholder?: string;
    disabled?: boolean;
    style?: CSSProperties;
    className?: string;
  };
  showControls?: boolean;
  editable?: boolean;
  onContentChange?: (content: string) => void;
}

export function MarkdownCopy({
  content,
  showMarkdown = true,
  onShowMarkdownChange,
  copyButtonProps = {},
  markdownViewerProps = {},
  textareaProps = {},
  showControls = true,
  editable = false,
  onContentChange,
}: MarkdownCopyProps) {
  const { t } = useTranslation();
  const [isCopying, setIsCopying] = useState(false);
  const [editContent, setEditContent] = useState(content);
  const [localShowMarkdown, setLocalShowMarkdown] = useState(showMarkdown);
  const markdownContent = useMemo(
    () => stripFrontmatter(content || ""),
    [content],
  );

  useEffect(() => {
    setEditContent(content);
  }, [content]);

  useEffect(() => {
    if (editable && !textareaProps.disabled) {
      setLocalShowMarkdown(false);
    } else {
      setLocalShowMarkdown(showMarkdown);
    }
  }, [editable, textareaProps.disabled, showMarkdown]);

  const copyToClipboard = async () => {
    const contentToCopy =
      localShowMarkdown && !(editable && !textareaProps.disabled)
        ? content
        : editable
        ? editContent
        : content;

    if (!contentToCopy) return;

    setIsCopying(true);
    try {
      const ok = await copyText(contentToCopy);
      if (ok) message.success(t("common.copied"));
      else message.error(t("common.copyFailed"));
    } catch (err) {
      console.error("Failed to copy text: ", err);
      message.error(t("common.copyFailed"));
    } finally {
      setIsCopying(false);
    }
  };

  const handleContentChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const newContent = e.target.value;
    setEditContent(newContent);
    if (onContentChange) {
      onContentChange(newContent);
    }
  };

  const handleShowMarkdownChange = (show: boolean) => {
    setLocalShowMarkdown(show);
    if (onShowMarkdownChange) {
      onShowMarkdownChange(show);
    }
  };

  const defaultCopyButtonProps = {
    type: "text" as const,
    size: "small" as const,
    ...copyButtonProps,
  };

  const defaultMarkdownViewerProps = {
    style: {
      padding: 16,
      height: "100%",
      overflow: "auto",
      backgroundColor: "var(--fn-bg-primary)",
      borderRadius: 6,
      ...markdownViewerProps.style,
    },
    ...markdownViewerProps,
  };

  const defaultTextareaProps = {
    rows: 12,
    placeholder: t("common.contentPlaceholder"),
    ...textareaProps,
  };

  return (
    <div className={styles.markdownCopy}>
      {showControls && (
        <div className={styles.controls}>
          <div>{t("common.content")}</div>
          <div className={styles.controlGroup}>
            <div className={styles.previewToggle}>
              <span className={styles.previewLabel}>{t("common.preview")}</span>
              <Switch
                checked={localShowMarkdown}
                onChange={handleShowMarkdownChange}
                size="small"
              />
            </div>
            <Button
              icon={<Copy size={16} />}
              {...defaultCopyButtonProps}
              onClick={copyToClipboard}
              loading={isCopying}
            />
          </div>
        </div>
      )}

      {localShowMarkdown ? (
        <div className={styles.markdownViewer}>
          <Markdown content={markdownContent} {...defaultMarkdownViewerProps} />
        </div>
      ) : (
        <div className={styles.textareaContainer}>
          <Input.TextArea
            value={editable ? editContent : content}
            onChange={handleContentChange}
            {...defaultTextareaProps}
            className={styles.textarea}
            readOnly={!editable || textareaProps.disabled}
          />
        </div>
      )}
    </div>
  );
}
