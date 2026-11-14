import { useEffect, useRef, useState, type ReactNode } from "react";
import { Alert, Button, Checkbox, Popconfirm, Space } from "antd";
import { useTranslation } from "react-i18next";
import {
  knowledgeBasesApi,
  type KnowledgeDocument,
} from "../../api/modules/knowledgeBases";
import { apiErrorMessage } from "../../utils/apiError";
import styles from "./DocumentBatchActions.module.less";

interface Selection {
  keys: string[];
  busy: boolean;
  setKeys: (keys: string[]) => void;
}
interface Props {
  kbId: string;
  documents: KnowledgeDocument[];
  writable: boolean;
  onChanged: () => Promise<void>;
  isCurrent?: () => boolean;
  children: (selection: Selection) => ReactNode;
}
type Action = "delete" | "reindex";
type Failure = { id: string; filename: string; error: string };

// Key by knowledge base, folder and write access. Leaving that scope stops
// unsent requests; already accepted mutations cannot be rolled back.
export default function DocumentBatchActions({
  kbId,
  documents,
  writable,
  onChanged,
  isCurrent = () => true,
  children,
}: Props) {
  const { t } = useTranslation();
  const [selected, setSelected] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [completed, setCompleted] = useState(0);
  const [total, setTotal] = useState(0);
  const [result, setResult] = useState<{
    action: Action;
    succeeded: number;
    failures: Failure[];
  } | null>(null);
  const [refreshFailed, setRefreshFailed] = useState(false);
  const mounted = useRef(true);
  const running = useRef(false);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  const files = documents.filter((d) => !d.is_dir);
  const allowed = new Set(files.map((d) => d.id));
  const keys = writable ? selected.filter((id) => allowed.has(id)) : [];
  const chosen = files.filter((d) => keys.includes(d.id));
  const setKeys = (next: string[]) => {
    if (!running.current && writable)
      setSelected([...new Set(next.filter((id) => allowed.has(id)))]);
  };

  const run = async (action: Action) => {
    if (
      !mounted.current ||
      !isCurrent() ||
      running.current ||
      !writable ||
      !chosen.length
    )
      return;
    running.current = true;
    setBusy(true);
    setCompleted(0);
    setResult(null);
    setRefreshFailed(false);
    const snapshot = [...chosen];
    setTotal(snapshot.length);
    const failures: Failure[] = [];
    let cursor = 0;
    let done = 0;
    const worker = async () => {
      while (mounted.current && isCurrent() && cursor < snapshot.length) {
        const document = snapshot[cursor++];
        try {
          if (action === "delete")
            await knowledgeBasesApi.deleteDocument(kbId, document.id);
          else await knowledgeBasesApi.reindexDocument(kbId, document.id);
        } catch (error) {
          failures.push({
            id: document.id,
            filename: document.filename,
            error: apiErrorMessage(
              error,
              t("knowledgeBases.batchRequestFailed"),
              t,
            ),
          });
        }
        done++;
        if (mounted.current) setCompleted(done);
      }
    };
    try {
      await Promise.all(
        Array.from({ length: Math.min(3, snapshot.length) }, worker),
      );
      if (!mounted.current || !isCurrent()) return;
      setSelected(failures.map((f) => f.id));
      setResult({ action, succeeded: done - failures.length, failures });
      try {
        await onChanged();
      } catch {
        if (mounted.current) setRefreshFailed(true);
      }
    } finally {
      running.current = false;
      if (mounted.current) setBusy(false);
    }
  };

  return (
    <>
      {writable && files.length > 0 ? (
        <div className={styles.toolbar}>
          <Space wrap>
            <Checkbox
              checked={keys.length === files.length}
              indeterminate={keys.length > 0 && keys.length < files.length}
              disabled={busy}
              onChange={(e) =>
                setKeys(e.target.checked ? files.map((d) => d.id) : [])
              }
            >
              {t("knowledgeBases.batchSelectAll")}
            </Checkbox>
            <span role="status">
              {busy
                ? t("knowledgeBases.batchProgress", {
                    completed,
                    total,
                  })
                : t("knowledgeBases.batchSelected", { count: keys.length })}
            </span>
            <Button
              size="small"
              disabled={busy || !keys.length}
              onClick={() => setKeys([])}
            >
              {t("knowledgeBases.batchClear")}
            </Button>
            <Button
              size="small"
              disabled={busy || !keys.length}
              onClick={() => void run("reindex")}
            >
              {t("knowledgeBases.batchReindex")}
            </Button>
            <Popconfirm
              title={t("knowledgeBases.batchDeleteConfirm", {
                count: keys.length,
              })}
              okText={t("common.confirm")}
              cancelText={t("common.cancel")}
              disabled={busy || !keys.length}
              onConfirm={() => run("delete")}
            >
              <Button danger size="small" disabled={busy || !keys.length}>
                {t("knowledgeBases.batchDelete")}
              </Button>
            </Popconfirm>
          </Space>
        </div>
      ) : null}
      {result ? (
        <Alert
          className={styles.result}
          type={result.failures.length ? "warning" : "success"}
          showIcon
          message={t(
            result.action === "delete"
              ? "knowledgeBases.batchDeleted"
              : "knowledgeBases.batchReindexed",
            { count: result.succeeded, failed: result.failures.length },
          )}
          description={
            result.failures.length ? (
              <ul className={styles.failures}>
                {result.failures.map((f) => (
                  <li key={f.id}>
                    <strong>{f.filename}</strong>: <span>{f.error}</span>
                  </li>
                ))}
              </ul>
            ) : undefined
          }
        />
      ) : null}
      {refreshFailed ? (
        <Alert
          type="warning"
          showIcon
          message={t("knowledgeBases.batchRefreshFailed")}
        />
      ) : null}
      {children({ keys, busy, setKeys })}
    </>
  );
}
