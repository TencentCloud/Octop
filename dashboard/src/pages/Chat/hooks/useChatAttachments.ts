import { useCallback, useEffect, useRef, useState } from "react";
import type { ChangeEvent, ClipboardEvent, DragEvent } from "react";
import { useTranslation } from "react-i18next";
import {
  type NativeCaptureMode,
  uploadFile,
  nativeCaptureAvailability,
  captureNativeAttachment,
} from "../../../api/modules/upload";
import { agentAttachmentAccessUrl } from "../../../utils/toolMediaBlocks";
import type { ChatAttachment } from "./useChat";
import { message as antMessage } from "@/utils/antdMessage";
import { apiErrorMessage } from "../../../utils/apiError";

import {
  inferAttachmentKind,
  inferKindFromNameAndMime,
} from "../utils/chatAttachments";
import { useServerUploadLimit } from "../../../hooks/useServerUploadLimit";

export function useChatAttachments(
  agentId: string | null | undefined,
  threadId?: string | null,
) {
  const { t } = useTranslation();
  const { maxUploadBytes, maxUploadMb } = useServerUploadLimit();
  const [attachments, setAttachments] = useState<ChatAttachment[]>([]);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [nativeCaptureAvailable, setNativeCaptureAvailable] = useState(false);
  const [captureBusy, setCaptureBusy] = useState(false);
  const capturePending = useRef(false);
  const captureScope = useRef(0);

  useEffect(() => {
    // A capture started in another chat must not attach files to this draft.
    captureScope.current += 1;
    return () => {
      captureScope.current += 1;
    };
  }, [agentId, threadId]);

  useEffect(() => {
    let active = true;
    setNativeCaptureAvailable(false);
    if (agentId && !agentId.startsWith("bridge:")) {
      void nativeCaptureAvailability(agentId).then(
        (result) => {
          if (active) setNativeCaptureAvailable(result.available);
        },
        () => {},
      );
    }
    return () => {
      active = false;
    };
  }, [agentId]);

  const handleNativeCapture = useCallback(
    async (mode: NativeCaptureMode = "scan") => {
      if (!agentId || capturePending.current) return;
      capturePending.current = true;
      setCaptureBusy(true);
      const scope = captureScope.current;
      try {
        const result = await captureNativeAttachment(agentId, mode);
        if (scope !== captureScope.current) return;
        if (result.status === "ok") {
          const next = result.attachments.map(
            (file) =>
              ({
                ...(file.preview_url ? { previewUrl: file.preview_url } : {}),
                url: file.access_url || file.url,
                filename: file.filename,
                mediaType: file.media_type,
                workspacePath: file.workspace_path || file.path,
                kind: inferKindFromNameAndMime(file.media_type, file.filename),
              }) satisfies ChatAttachment,
          );
          setAttachments((prev) => [...prev, ...next]);
        } else if (result.status !== "cancelled") {
          antMessage.error(t(`upload.capture.${result.status}`));
        }
      } catch (err) {
        if (scope === captureScope.current) {
          antMessage.error(apiErrorMessage(err, t("upload.capture.error"), t));
        }
      } finally {
        capturePending.current = false;
        setCaptureBusy(false);
      }
    },
    [agentId, t],
  );

  const processFiles = useCallback(
    async (files: FileList | File[]) => {
      const fileArr = Array.from(files).filter((f) => {
        if (f.size > maxUploadBytes) {
          antMessage.error(
            t("upload.tooLarge", "File too large (max {{maxMb}}MB): {{name}}", {
              name: f.name,
              maxMb: maxUploadMb,
            }),
          );
          return false;
        }
        return true;
      });

      if (fileArr.length === 0) return;

      if (!agentId) {
        antMessage.error(t("upload.failed", "Upload failed"));
        return;
      }

      setUploading(true);
      try {
        const results = await Promise.all(
          fileArr.map(async (file) => {
            const res = await uploadFile(agentId, file);
            const workspacePath = res.path || res.workspace_path;
            const previewUrl =
              res.access_url ||
              res.url ||
              (workspacePath
                ? agentAttachmentAccessUrl(
                    agentId,
                    workspacePath,
                    res.media_type,
                  )
                : "");
            return {
              url: previewUrl,
              filename: res.filename,
              mediaType: res.media_type,
              workspacePath,
              kind: inferAttachmentKind(file, res.media_type),
            } satisfies ChatAttachment;
          }),
        );
        setAttachments((prev) => [...prev, ...results]);
      } catch (err: unknown) {
        antMessage.error(
          apiErrorMessage(err, t("upload.failed", "Upload failed"), t),
        );
      } finally {
        setUploading(false);
      }
    },
    [agentId, maxUploadBytes, maxUploadMb, t],
  );

  const handleFileSelect = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const handleFileChange = useCallback(
    (e: ChangeEvent<HTMLInputElement>) => {
      if (e.target.files && e.target.files.length > 0) {
        void processFiles(e.target.files);
      }
      e.target.value = "";
    },
    [processFiles],
  );

  const removeAttachment = useCallback((index: number) => {
    setAttachments((prev) => prev.filter((_, i) => i !== index));
  }, []);

  const clearAttachments = useCallback(() => {
    setAttachments([]);
  }, []);

  const restoreAttachments = useCallback((next: ChatAttachment[]) => {
    setAttachments(next.map((a) => ({ ...a })));
  }, []);

  const handlePaste = useCallback(
    (e: ClipboardEvent) => {
      const items = e.clipboardData?.items;
      if (!items) return;
      const pastedFiles: File[] = [];
      for (let i = 0; i < items.length; i++) {
        const item = items[i];
        if (item.kind === "file") {
          const file = item.getAsFile();
          if (file) pastedFiles.push(file);
        }
      }
      if (pastedFiles.length > 0) {
        e.preventDefault();
        void processFiles(pastedFiles);
      }
    },
    [processFiles],
  );

  const handleDragEnter = useCallback((e: DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e: DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(false);
  }, []);

  const handleDragOver = useCallback((e: DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  }, []);

  const handleDrop = useCallback(
    (e: DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      setDragOver(false);
      if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        void processFiles(e.dataTransfer.files);
      }
    },
    [processFiles],
  );

  return {
    attachments,
    uploading: uploading || captureBusy,
    nativeCaptureAvailable,
    capturing: captureBusy,
    handleNativeCapture,
    dragOver,
    fileInputRef,
    processFiles,
    handleFileSelect,
    handleFileChange,
    removeAttachment,
    clearAttachments,
    restoreAttachments,
    handlePaste,
    handleDragEnter,
    handleDragLeave,
    handleDragOver,
    handleDrop,
  };
}
