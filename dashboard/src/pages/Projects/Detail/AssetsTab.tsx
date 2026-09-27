import { Button, Spin, Typography } from "antd";
import { ExternalLink, RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import {
  knowledgeBasesApi,
  type KnowledgeBase,
} from "../../../api/modules/knowledgeBases";
import { EmptyState } from "../../../components/EmptyState";
import { useAsyncResource } from "../../../hooks/useAsyncResource";
import { useServerTimezone } from "../../../hooks/useServerTimezone";
import { formatServerDateTime } from "../../../utils/formatMessageTime";
import styles from "./AssetsTab.module.less";

const { Text } = Typography;

/**
 * Assets tab — the project's knowledge base (PLAN §19.3 / §8).
 *
 * There is deliberately **no asset model**: `projects.kb_id` is the whole data
 * source, and this component reads it through the existing knowledge-base API
 * wrapper. Nothing here invents a table, a column, or an "asset type".
 *
 * A `NULL` `kb_id` (feature off, or the KB could not be created) is an explicit
 * **non-error surface**: the tab renders the empty state with a way to bind one.
 * It must not raise, must not surface a failure, and must not be counted as an
 * acceptance failure anywhere.
 */
interface AssetsTabProps {
  /**
   * `projects.kb_id`. `null` means no knowledge base is bound — a supported
   * state, not a failure.
   */
  kbId: string | null;
}

function AssetsTab({ kbId }: AssetsTabProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const timeZone = useServerTimezone();

  // `enabled: false` is what keeps the empty branch honest: with no kb_id the
  // fetcher never runs, so the tab provably makes zero knowledge-base requests
  // instead of firing one and discarding the answer.
  const {
    data: kb,
    loading,
    refresh,
  } = useAsyncResource<KnowledgeBase | null>(
    null,
    () => knowledgeBasesApi.get(kbId as string),
    [kbId],
    {
      enabled: kbId !== null,
      errorFallback: t("projects.loadFailed"),
      t,
      logLabel: "project-assets",
    },
  );

  const openKnowledgeBases = () => navigate("/knowledge-bases");

  if (!kbId) {
    return (
      <div className={styles.section} data-testid="project-assets-empty">
        <EmptyState
          variant="empty"
          title={t("projects.assetEmpty")}
          actionLabel={t("projects.assetBind")}
          onAction={openKnowledgeBases}
        />
      </div>
    );
  }

  return (
    <div className={styles.section} data-testid="project-assets">
      <div className={styles.sectionTitle}>
        {t("projects.assetTitle")}
        <span className={styles.headerActions}>
          <Button
            type="text"
            size="small"
            icon={<RefreshCw size={14} />}
            aria-label={t("common.refresh")}
            loading={loading}
            onClick={() => void refresh()}
          />
          <Button
            type="link"
            size="small"
            icon={<ExternalLink size={14} />}
            onClick={() =>
              navigate(`/knowledge-bases?kb=${encodeURIComponent(kbId)}`)
            }
          >
            {t("projects.assetOpen")}
          </Button>
        </span>
      </div>
      {loading && !kb ? (
        <div className={styles.centered}>
          <Spin />
        </div>
      ) : kb ? (
        <div className={styles.meta}>
          <Text strong className={styles.name}>
            {kb.name}
          </Text>
          <Text type="secondary">
            {t("projects.assetDocCount", { count: kb.doc_count })}
          </Text>
          <Text type="secondary">
            {formatServerDateTime(kb.updated_at, timeZone)}
          </Text>
        </div>
      ) : null}
    </div>
  );
}

export default AssetsTab;
