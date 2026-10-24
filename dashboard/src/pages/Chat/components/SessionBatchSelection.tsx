import { useRef, useState, type ReactNode } from "react";
import { Button, Checkbox } from "antd";
import { useTranslation } from "react-i18next";
import { showConfirmModal } from "../../../utils/confirmModal";
import { message } from "../../../utils/antdMessage";
import {
  isPendingThread,
  type DeleteSessionsResult,
  type Session,
} from "../hooks/useSessions";
import styles from "./SessionBatchSelection.module.less";

export interface SessionSelection {
  selectedIds: ReadonlySet<string>;
  disabled: boolean;
  toggle: (id: string) => void;
}

export type BatchDeleteSessions = (
  agentId: string,
  ids: string[],
) => Promise<DeleteSessionsResult>;

/** Selection belongs to one expert and only includes currently listed conversations. */
export default function SessionBatchSelection({
  agentId,
  sessions,
  onDelete,
  children,
}: {
  agentId: string;
  sessions: Session[];
  onDelete: BatchDeleteSessions;
  children: (selection: SessionSelection | undefined) => ReactNode;
}) {
  const { t } = useTranslation();
  const [selecting, setSelecting] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const [deleting, setDeleting] = useState(false);
  const inFlight = useRef(false);
  const selectableIds = sessions
    .filter((s) => !isPendingThread(s.id))
    .map((s) => s.id);
  const selectedIds = new Set(
    selected.filter((id) => selectableIds.includes(id)),
  );
  const allSelected =
    selectableIds.length > 0 && selectedIds.size === selectableIds.length;

  const cancel = () => {
    if (inFlight.current) return;
    setSelecting(false);
    setSelected([]);
  };

  const confirmDelete = () => {
    const ids = [...selectedIds];
    if (ids.length === 0 || inFlight.current) return;
    showConfirmModal({
      title: t("chat.batchDeleteConfirm", { count: ids.length }),
      okText: t("common.delete"),
      cancelText: t("common.cancel"),
      okButtonProps: { danger: true },
      onOk: async () => {
        if (inFlight.current) return;
        inFlight.current = true;
        setDeleting(true);
        try {
          const { deletedIds, failedIds } = await onDelete(agentId, ids);
          setSelected(failedIds);
          if (failedIds.length > 0) {
            message.error(
              t("chat.batchDeletePartial", {
                succeeded: deletedIds.length,
                failed: failedIds.length,
              }),
            );
          } else {
            setSelecting(false);
            message.success(
              t("chat.batchDeleteSuccess", { count: deletedIds.length }),
            );
          }
        } catch {
          message.error(t("common.deleteFailed"));
        } finally {
          inFlight.current = false;
          setDeleting(false);
        }
      },
    });
  };

  const selection: SessionSelection | undefined = selecting
    ? {
        selectedIds,
        disabled: deleting,
        toggle: (id) => {
          if (inFlight.current || !selectableIds.includes(id)) return;
          setSelected((prev) =>
            selectedIds.has(id)
              ? prev.filter((item) => item !== id)
              : [...selectedIds, id],
          );
        },
      }
    : undefined;

  return (
    <>
      <div className={styles.toolbar}>
        {selecting ? (
          <>
            <Checkbox
              checked={allSelected}
              indeterminate={selectedIds.size > 0 && !allSelected}
              disabled={deleting || selectableIds.length === 0}
              onChange={(e) =>
                setSelected(e.target.checked ? selectableIds : [])
              }
            >
              {t("chat.selectListedSessions")}
            </Checkbox>
            <div className={styles.actions}>
              <Button
                size="small"
                danger
                disabled={selectedIds.size === 0}
                loading={deleting}
                onClick={confirmDelete}
              >
                {t("chat.deleteSelectedSessions", { count: selectedIds.size })}
              </Button>
              <Button size="small" disabled={deleting} onClick={cancel}>
                {t("common.cancel")}
              </Button>
            </div>
          </>
        ) : (
          <Button
            type="text"
            size="small"
            disabled={selectableIds.length === 0}
            onClick={() => setSelecting(true)}
          >
            {t("chat.selectSessions")}
          </Button>
        )}
      </div>
      {children(selection)}
    </>
  );
}
