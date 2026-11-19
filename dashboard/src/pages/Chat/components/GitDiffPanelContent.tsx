/**
 * GitDiffPanelContent — dock tab body for a single-file git diff.
 * Fetches the diff on mount and keeps it while the tab stays open.
 */

import { useEffect, useState } from "react";
import { Button, Spin, Tooltip } from "antd";
import { FilePen } from "lucide-react";
import { useTranslation } from "react-i18next";
import { gitApi, type GitDiff } from "../../../api/modules/git";
import { apiErrorMessage } from "../../../utils/apiError";
import GitDiffView from "../../Agent/Workspace/components/GitDiffView";
import styles from "../../Agent/Workspace/index.module.less";

interface GitDiffPanelContentProps {
  agentId: string;
  path: string;
  staged: boolean;
  onOpenFile?: (path: string) => void;
}

export default function GitDiffPanelContent({
  agentId,
  path,
  staged,
  onOpenFile,
}: GitDiffPanelContentProps) {
  const { t } = useTranslation();
  const [data, setData] = useState<GitDiff | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    gitApi
      .diff(agentId, path, staged)
      .then((result) => {
        if (!cancelled) setData(result);
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
  }, [agentId, path, staged, t]);

  const header = (
    <div className={styles.gitDiffHeader}>
      <span className={styles.gitDiffHeaderPath} title={path}>
        {path}
        {staged ? ` · ${t("git.stagedLabel", "已暂存")}` : ""}
      </span>
      {onOpenFile && (
        <Tooltip title={t("git.open", "打开")}>
          <Button
            size="small"
            icon={<FilePen size={13} />}
            onClick={() => onOpenFile(path)}
            aria-label={t("git.open", "打开")}
          >
            {t("git.open", "打开")}
          </Button>
        </Tooltip>
      )}
    </div>
  );

  if (loading) {
    return (
      <>
        {header}
        <div className={styles.viewerLoading}>
          <Spin />
        </div>
      </>
    );
  }

  return (
    <>
      {header}
      {error ? (
        <div className={styles.gitNotice} data-testid="git-diff-error">
          {error}
        </div>
      ) : (
        <GitDiffView diff={data?.diff ?? ""} truncated={data?.truncated} />
      )}
    </>
  );
}
