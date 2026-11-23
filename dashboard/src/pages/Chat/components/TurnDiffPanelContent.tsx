/**
 * TurnDiffPanelContent — right-side dock body for one turn's before→after
 * diff (server checkpoints), so Review never leaves the code viewer.
 */

import { useEffect, useState } from "react";
import { Spin } from "antd";
import { useTranslation } from "react-i18next";
import { fileCheckpointsApi } from "../../../api/modules/fileCheckpoints";
import { apiErrorMessage } from "../../../utils/apiError";
import GitDiffView from "../../Agent/Workspace/components/GitDiffView";
import styles from "../../Agent/Workspace/index.module.less";

interface TurnDiffPanelContentProps {
  agentId: string;
  threadId: string;
  messageId: string;
  path: string;
  displayPath: string;
}

export default function TurnDiffPanelContent({
  agentId,
  threadId,
  messageId,
  path,
  displayPath,
}: TurnDiffPanelContentProps) {
  const { t } = useTranslation();
  const [diff, setDiff] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setDiff("");
    fileCheckpointsApi
      .turnDiff(agentId, threadId, messageId, path)
      .then((res) => {
        if (!cancelled) setDiff(res.diff);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(apiErrorMessage(err, t("workspace.readFailed", "读取失败")));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [agentId, threadId, messageId, path, t]);

  return (
    <>
      <div className={styles.gitDiffHeader}>
        <span className={styles.gitDiffHeaderPath} title={displayPath}>
          {displayPath}
          <span style={{ opacity: 0.6 }}>
            {" "}
            · {t("git.turnDiffLabel", "本轮改动")}
          </span>
        </span>
      </div>
      {loading ? (
        <div className={styles.viewerLoading}>
          <Spin />
        </div>
      ) : error ? (
        <div className={styles.gitNotice}>{error}</div>
      ) : (
        <GitDiffView diff={diff} />
      )}
    </>
  );
}
