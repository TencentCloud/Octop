import { useState, useCallback } from "react";
import { useTranslation } from "react-i18next";

import { message } from "@/utils/antdMessage";
import { copyText } from "@/utils/copyText";

export interface FileEditorState {
  content: string;
  originalContent: string;
  loading: boolean;
  saving: boolean;
  showMarkdown: boolean;
  hasChanges: boolean;
}

export interface FileEditorActions {
  /** Open the editor with content loaded via an async loader */
  open: (loader: () => Promise<string>) => Promise<void>;
  /** Open the editor with content provided directly (no async loading) */
  openWithContent: (content: string) => void;
  /** Update the current content */
  setContent: (value: string) => void;
  /** Save the current content via an async saver */
  save: (saver: () => Promise<void>) => Promise<void>;
  /** Reset content to original */
  reset: () => void;
  /** Close and clear all state */
  close: () => void;
  /** Toggle markdown preview */
  toggleMarkdown: (show?: boolean) => void;
  /** Copy content to clipboard */
  copyToClipboard: () => Promise<void>;
}

export function useFileEditor(): [FileEditorState, FileEditorActions] {
  const { t } = useTranslation();

  const [content, setContent] = useState("");
  const [originalContent, setOriginalContent] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [showMarkdown, setShowMarkdown] = useState(true);

  const hasChanges = content !== originalContent;

  const open = useCallback(
    async (loader: () => Promise<string>) => {
      setLoading(true);
      setShowMarkdown(true);
      try {
        const data = await loader();
        setContent(data);
        setOriginalContent(data);
      } catch {
        message.error(t("personalization.loadFailed"));
      } finally {
        setLoading(false);
      }
    },
    [t],
  );

  const openWithContent = useCallback((c: string) => {
    setContent(c);
    setOriginalContent(c);
    setShowMarkdown(true);
  }, []);

  const save = useCallback(
    async (saver: () => Promise<void>) => {
      setSaving(true);
      try {
        await saver();
        setOriginalContent(content);
        message.success(t("personalization.saveSuccess"));
      } catch {
        message.error(t("personalization.saveFailed"));
      } finally {
        setSaving(false);
      }
    },
    [content, t],
  );

  const reset = useCallback(() => {
    setContent(originalContent);
  }, [originalContent]);

  const close = useCallback(() => {
    setContent("");
    setOriginalContent("");
    setShowMarkdown(true);
    setLoading(false);
    setSaving(false);
  }, []);

  const toggleMarkdown = useCallback((show?: boolean) => {
    setShowMarkdown((prev) => (show !== undefined ? show : !prev));
  }, []);

  const copyToClipboard = useCallback(async () => {
    const ok = await copyText(content);
    if (ok) message.success(t("common.copied"));
    else message.error(t("common.copyFailed"));
  }, [content, t]);

  const state: FileEditorState = {
    content,
    originalContent,
    loading,
    saving,
    showMarkdown,
    hasChanges,
  };

  const actions: FileEditorActions = {
    open,
    openWithContent,
    setContent,
    save,
    reset,
    close,
    toggleMarkdown,
    copyToClipboard,
  };

  return [state, actions];
}
