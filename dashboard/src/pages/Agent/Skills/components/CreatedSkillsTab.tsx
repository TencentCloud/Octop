import { useCallback, useEffect, useState } from "react";
import { Empty, Tag, Tooltip } from "antd";
import { Download, RefreshCw, Sparkles } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  createdSkillsApi,
  type CreatedSkill,
} from "../../../../api/modules/createdSkills";
import { CardSkeleton } from "../../../../components/Skeleton";
import { message } from "../../../../utils/antdMessage";
import { showApiError } from "../../../../utils/showApiToast";
import styles from "../index.module.less";

interface CreatedSkillsTabProps {
  agentId: string;
}

export default function CreatedSkillsTab({ agentId }: CreatedSkillsTabProps) {
  const { t } = useTranslation();
  const [items, setItems] = useState<CreatedSkill[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [installing, setInstalling] = useState<string | null>(null);

  const fetchItems = useCallback(
    async (refresh = false) => {
      if (refresh) setRefreshing(true);
      else setLoading(true);
      try {
        setItems(await createdSkillsApi.list(agentId));
      } catch (error) {
        showApiError(error, t("skills.createdLoadFailed"), t);
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [agentId, t],
  );

  useEffect(() => {
    void fetchItems();
  }, [fetchItems]);

  const install = async (skill: CreatedSkill) => {
    setInstalling(skill.slug);
    try {
      await createdSkillsApi.install(agentId, skill.slug, skill.installed);
      message.success(
        skill.installed
          ? t("skills.createdReinstallSuccess")
          : t("skills.installSuccess"),
      );
      await fetchItems(true);
    } catch (error) {
      showApiError(error, t("skills.installFailed"), t);
    } finally {
      setInstalling(null);
    }
  };

  return (
    <>
      <div className={styles.gridToolbar}>
        <span className={styles.gridCount}>
          {t("skills.createdCount", { count: items.length })}
        </span>
        <Tooltip title={t("common.refresh")}>
          <button
            type="button"
            className={styles.toolbarIconBtn}
            onClick={() => void fetchItems(true)}
            disabled={refreshing || loading}
          >
            <RefreshCw
              size={14}
              className={refreshing ? styles.spinning : undefined}
            />
          </button>
        </Tooltip>
      </div>

      <div className={styles.skillsListArea}>
        {loading && items.length === 0 ? (
          <CardSkeleton count={3} />
        ) : items.length === 0 ? (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={t("skills.createdEmpty")}
          />
        ) : (
          <div className={styles.skillsGrid}>
            {items.map((skill) => (
              <article key={skill.slug} className={styles.skillCard}>
                <div className={styles.cardBody}>
                  <div className={styles.cardHeader}>
                    <div
                      className={styles.iconWrapper}
                      style={{ color: "#8b5cf6", backgroundColor: "#8b5cf618" }}
                    >
                      <Sparkles size={22} />
                    </div>
                    <div className={styles.cardMeta}>
                      <div className={styles.cardTitle}>{skill.name}</div>
                      <div className={styles.cardBadges}>
                        <Tag color="purple" bordered={false}>
                          {t("skills.createdByBuilder")}
                        </Tag>
                        {skill.artifact_type === "hybrid" ? (
                          <Tag bordered={false}>Hybrid</Tag>
                        ) : null}
                      </div>
                    </div>
                  </div>
                  <div className={styles.cardDesc} title={skill.description}>
                    {skill.description || t("skills.noDescription")}
                  </div>
                  <div className={styles.cardFooter}>
                    <span className={styles.createdSkillSlug}>
                      {skill.slug}
                    </span>
                    <button
                      type="button"
                      className={`${styles.applyBtn} ${styles.applyActiveBtn}`}
                      disabled={installing === skill.slug}
                      onClick={() => void install(skill)}
                    >
                      <Download size={14} />
                      {installing === skill.slug
                        ? t("skills.installing")
                        : skill.installed
                        ? t("skills.reinstall")
                        : t("skills.install")}
                    </button>
                  </div>
                </div>
              </article>
            ))}
          </div>
        )}
      </div>
    </>
  );
}
