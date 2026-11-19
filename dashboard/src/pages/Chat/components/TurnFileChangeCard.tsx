import { useMemo, useState } from "react";
import { ChevronRight, FilePen } from "lucide-react";
import { useTranslation } from "react-i18next";
import cx from "classnames";
import { useChatFilePreview } from "../ChatFilePreviewContext";
import { isWriteToolName } from "../constants";
import { collectChatFilePaths } from "../hooks/useChatFileDetection";
import type { ChatMessage } from "../hooks/useChat";
import {
  fileChangeChipLabel,
  summarizeTurnFileChanges,
  type TurnFileChange,
} from "../utils/turnFileChanges";
import styles from "../index.module.less";

const FILE_CHANGE_PREVIEW = 4;

/**
 * Files this reply wrote or edited, each with its line counts.
 * Choosing a row opens that file in the dock.
 */
export default function TurnFileChangeCard({
  messages,
  agentId,
  streaming = false,
  onOpenList,
}: {
  messages: ChatMessage[];
  agentId?: string | null;
  streaming?: boolean;
  onOpenList?: () => void;
}) {
  const { t } = useTranslation();
  const filePreview = useChatFilePreview();
  const [showAll, setShowAll] = useState(false);
  const summary = useMemo(
    () => summarizeTurnFileChanges(messages, agentId),
    [messages, agentId],
  );
  const fallbackCount = useMemo(() => {
    const fromPaths = collectChatFilePaths(messages, agentId).length;
    if (fromPaths > 0) return fromPaths;
    return messages.filter((message) => isWriteToolName(message.toolData?.name))
      .length;
  }, [messages, agentId]);

  if (summary.files.length === 0) {
    return (
      <button
        type="button"
        className={cx(
          styles.openBrowserPrompt,
          streaming && styles.openBrowserPromptActive,
        )}
        onClick={onOpenList}
        aria-label={t("chat.editFileCard", {
          count: Math.max(fallbackCount, 1),
        })}
      >
        <FilePen
          size={16}
          strokeWidth={2}
          className={styles.openBrowserPromptIcon}
          aria-hidden="true"
        />
        <span>
          {t("chat.editFileCard", { count: Math.max(fallbackCount, 1) })}
        </span>
        <ChevronRight
          size={14}
          className={styles.openBrowserPromptArrow}
          aria-hidden="true"
        />
      </button>
    );
  }

  const visible = visibleFileChanges(summary.files, showAll);
  const moreCount = summary.files.length - visible.length;

  return (
    <ul className={styles.fileChangeList}>
      {visible.map((file) => {
        const showStats = file.measured && file.additions + file.deletions > 0;
        const name = fileChangeChipLabel(file.displayPath);
        return (
          <li key={`${file.agentId ?? ""}\0${file.displayPath}`}>
            <button
              type="button"
              className={cx(
                styles.openBrowserPrompt,
                styles.fileChangeRow,
                streaming && file.pending && styles.openBrowserPromptActive,
              )}
              title={file.displayPath}
              onClick={() => {
                if (filePreview) {
                  filePreview.openFilePreview(file.openPath, file.agentId);
                } else {
                  onOpenList?.();
                }
              }}
            >
              <FilePen
                size={16}
                strokeWidth={2}
                className={styles.openBrowserPromptIcon}
                aria-hidden="true"
              />
              <span className={styles.fileChangeName}>{name}</span>
              {file.pending ? (
                <span className={styles.fileChangePending}>
                  {t("chat.fileChangePending")}
                </span>
              ) : null}
              {showStats ? (
                <span className={styles.fileChangeRowStats}>
                  <span className={styles.fileChangeAdd}>
                    +{file.additions}
                  </span>
                  <span className={styles.fileChangeDel}>
                    −{file.deletions}
                  </span>
                </span>
              ) : null}
              <ChevronRight
                size={14}
                className={styles.openBrowserPromptArrow}
                aria-hidden="true"
              />
            </button>
          </li>
        );
      })}
      {moreCount > 0 ? (
        <li>
          <button
            type="button"
            className={cx(styles.openBrowserPrompt, styles.fileChangeRow)}
            onClick={() => setShowAll(true)}
          >
            {t("chat.fileChangeMore", { count: moreCount })}
          </button>
        </li>
      ) : null}
    </ul>
  );
}

function visibleFileChanges(
  files: readonly TurnFileChange[],
  showAll: boolean,
): TurnFileChange[] {
  if (showAll || files.length <= FILE_CHANGE_PREVIEW) return [...files];
  const head = files.slice(0, FILE_CHANGE_PREVIEW);
  const pending = files
    .slice(FILE_CHANGE_PREVIEW)
    .filter((file) => file.pending);
  return [...head, ...pending];
}
