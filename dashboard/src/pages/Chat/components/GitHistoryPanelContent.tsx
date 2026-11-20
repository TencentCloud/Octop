/**
 * GitHistoryPanelContent — git log --graph history with merge lanes,
 * decorations and OpenPGP signature status (git %G?).
 */

import { useCallback, useEffect, useState } from "react";
import { Button, Spin, Tooltip } from "antd";
import {
  History,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  ShieldX,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { gitApi, type GitHistoryRow } from "../../../api/modules/git";
import { apiErrorMessage } from "../../../utils/apiError";
import { useServerTimezone } from "../../../hooks/useServerTimezone";
import { formatServerIsoDateTime } from "../../../utils/formatMessageTime";
import styles from "../../Agent/Workspace/index.module.less";

interface SignatureBadge {
  key: string;
  tone: "good" | "bad" | "warn" | "muted";
  Icon: typeof ShieldCheck;
}

const SIGNATURE_BADGES: Record<string, SignatureBadge> = {
  G: { key: "verified", tone: "good", Icon: ShieldCheck },
  B: { key: "bad", tone: "bad", Icon: ShieldX },
  U: { key: "unknown", tone: "warn", Icon: ShieldAlert },
  X: { key: "expired", tone: "warn", Icon: ShieldAlert },
  Y: { key: "expiredKey", tone: "warn", Icon: ShieldAlert },
  R: { key: "revoked", tone: "bad", Icon: ShieldX },
  E: { key: "missingKey", tone: "warn", Icon: ShieldAlert },
  N: { key: "unsigned", tone: "muted", Icon: ShieldAlert },
};

function SignatureBadgeView({ row }: { row: GitHistoryRow }) {
  const { t } = useTranslation();
  const status = row.signature ?? "N";
  const badge = SIGNATURE_BADGES[status] ?? SIGNATURE_BADGES.N;
  const Icon = badge.Icon;
  return (
    <Tooltip
      title={
        row.signer
          ? t(`git.history.signature.${badge.key}`, badge.key) +
            ` · ${row.signer}`
          : t(`git.history.signature.${badge.key}`, badge.key)
      }
    >
      <span
        className={`${styles.gitHistorySignature} ${
          styles[`gitHistorySignature_${badge.tone}`] ?? ""
        }`}
        data-signature={status}
      >
        <Icon size={12} aria-hidden />
        <span>{t(`git.history.signature.${badge.key}`, badge.key)}</span>
      </span>
    </Tooltip>
  );
}

function refsOf(row: GitHistoryRow): string[] {
  const raw = (row.refs ?? "").trim();
  if (!raw) return [];
  return raw
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);
}

export default function GitHistoryPanelContent({
  agentId,
}: {
  agentId: string;
}) {
  const { t } = useTranslation();
  const timeZone = useServerTimezone();
  const [rows, setRows] = useState<GitHistoryRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setRows(await gitApi.history(agentId, 80));
    } catch (err: unknown) {
      setError(apiErrorMessage(err, t("workspace.readFailed", "读取失败")));
    } finally {
      setLoading(false);
    }
  }, [agentId, t]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className={styles.gitHistory} data-testid="git-history">
      <div className={styles.gitDiffHeader}>
        <History size={14} aria-hidden />
        <span className={styles.gitDiffHeaderPath}>
          {t("git.history.title", "提交历史")}
        </span>
        <Tooltip title={t("common.refresh")}>
          <Button
            size="small"
            icon={
              <RefreshCw
                size={13}
                className={loading ? styles.gitSpin : undefined}
              />
            }
            onClick={() => void load()}
            aria-label={t("common.refresh")}
          />
        </Tooltip>
      </div>
      {loading && rows.length === 0 ? (
        <div className={styles.viewerLoading}>
          <Spin />
        </div>
      ) : error ? (
        <div className={styles.gitNotice}>{error}</div>
      ) : (
        <div className={styles.gitHistoryRows}>
          {rows.map((row, index) =>
            !row.sha ? (
              <div key={`g:${index}`} className={styles.gitHistoryGraphOnly}>
                <span className={styles.gitHistoryGraph}>{row.graph}</span>
              </div>
            ) : (
              <div
                key={row.sha}
                className={styles.gitHistoryRow}
                data-testid="git-history-row"
                data-sha={row.sha}
                data-signature={row.signature ?? "N"}
              >
                <span className={styles.gitHistoryGraph}>{row.graph}</span>
                <span className={styles.gitLogSha}>{row.short}</span>
                <span className={styles.gitHistoryRefs}>
                  {refsOf(row).map((ref) => (
                    <span key={ref} className={styles.gitHistoryRef}>
                      {ref}
                    </span>
                  ))}
                </span>
                <span
                  className={styles.gitHistorySubject}
                  title={row.subject ?? ""}
                >
                  {row.subject}
                </span>
                <span className={styles.gitLogMeta}>
                  {row.date ? formatServerIsoDateTime(row.date, timeZone) : ""}
                </span>
                <SignatureBadgeView row={row} />
              </div>
            ),
          )}
        </div>
      )}
    </div>
  );
}
