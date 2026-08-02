import { useEffect, useMemo, useState } from "react";
import { Drawer, Empty, Spin, Switch } from "antd";
import { Info } from "lucide-react";
import { useTranslation } from "react-i18next";
import { skillPackagesApi } from "../../../../api/modules/skillPackages";
import type {
  SkillPackage,
  SkillPackageDetail,
  SkillPackageSkill,
} from "../../../../api/types/skillPackage";
import { PackageIcon } from "../../../SkillPackages/PackageIcon";
import { showApiError } from "../../../../utils/showApiToast";
import type { SkillSpec } from "../useSkills";
import { hubInfoBySlugFromCache } from "./skillHubCache";
import styles from "../index.module.less";

interface SkillPackagesTabProps {
  agentId: string;
  skills: SkillSpec[];
  fetchSkills: () => Promise<void>;
  toggleEnabled: (skill: SkillSpec) => Promise<boolean>;
}

function resolvePackageSkillIcon(
  packageSkill: SkillPackageSkill,
  installed: SkillSpec | undefined,
  hubIconUrl?: string | null,
): { iconUrl?: string; emoji?: string } {
  const iconUrl =
    hubIconUrl || packageSkill.icon_url || installed?.iconUrl || undefined;
  const emoji = packageSkill.emoji || installed?.emoji;
  return { iconUrl, emoji };
}

function PackageSkillIcon({
  iconUrl,
  emoji,
}: {
  iconUrl?: string;
  emoji?: string;
}) {
  if (iconUrl) {
    return (
      <img src={iconUrl} alt="" className={styles.packageSkillRowIconImg} />
    );
  }
  if (emoji) {
    return <span className={styles.packageSkillRowEmoji}>{emoji}</span>;
  }
  return <span className={styles.packageSkillRowEmoji}>⚡</span>;
}

export default function SkillPackagesTab({
  agentId,
  skills,
  fetchSkills,
  toggleEnabled,
}: SkillPackagesTabProps) {
  const { t } = useTranslation();
  const [catalog, setCatalog] = useState<SkillPackage[]>([]);
  const [mountedIds, setMountedIds] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [mountingId, setMountingId] = useState<string | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailPackage, setDetailPackage] = useState<SkillPackageDetail | null>(
    null,
  );
  const [detailLoading, setDetailLoading] = useState(false);

  const hubSkillsBySlug = useMemo(() => hubInfoBySlugFromCache(), []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([
      skillPackagesApi.list(),
      skillPackagesApi.listMounted(agentId),
    ])
      .then(([packages, mounted]) => {
        if (cancelled) return;
        setCatalog(packages);
        setMountedIds(mounted.package_ids);
      })
      .catch((error) => {
        if (!cancelled) {
          showApiError(error, t("skills.packagesLoadFailed"), t);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [agentId, t]);

  const skillsBySlug = useMemo(
    () => new Map(skills.map((skill) => [skill.slug, skill])),
    [skills],
  );
  const workspaceSlugs = useMemo(
    () =>
      new Set(
        skills
          .filter((skill) => skill.kind === "workspace")
          .map((skill) => skill.slug),
      ),
    [skills],
  );
  const mountedSet = useMemo(() => new Set(mountedIds), [mountedIds]);

  const updateMounts = async (packageIds: string[], touchedId: string) => {
    setMountingId(touchedId);
    try {
      const result = await skillPackagesApi.replaceMounted(agentId, packageIds);
      setMountedIds(result.package_ids);
      await fetchSkills();
    } catch (error) {
      showApiError(error, t("skills.packagesUpdateFailed"), t);
    } finally {
      setMountingId(null);
    }
  };

  const handleToggleMount = (pack: SkillPackage, enabled: boolean) => {
    const next = enabled
      ? [...mountedIds, pack.id]
      : mountedIds.filter((id) => id !== pack.id);
    void updateMounts(next, pack.id);
  };

  const openDetail = async (pack: SkillPackage) => {
    setDetailOpen(true);
    setDetailLoading(true);
    setDetailPackage(null);
    try {
      const detail = await skillPackagesApi.get(pack.id);
      setDetailPackage(detail);
    } catch (error) {
      showApiError(error, t("skills.packagesLoadFailed"), t);
      setDetailOpen(false);
    } finally {
      setDetailLoading(false);
    }
  };

  if (loading) {
    return <Spin className={styles.skillPackagesLoading} />;
  }

  if (catalog.length === 0) {
    return (
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description={t("skills.noSkillPackages")}
      />
    );
  }

  const detailMounted =
    detailPackage != null && mountedSet.has(detailPackage.id);

  return (
    <>
      <p className={styles.packageMountHint}>{t("skills.mountBackendHint")}</p>
      <div className={styles.skillsGrid}>
        {catalog.map((pack) => {
          const mounted = mountedSet.has(pack.id);
          return (
            <div
              key={pack.id}
              className={styles.skillCard}
              onClick={() => void openDetail(pack)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => e.key === "Enter" && void openDetail(pack)}
            >
              <div className={styles.cardBody}>
                <div className={styles.cardHeader}>
                  <div
                    className={styles.iconWrapper}
                    style={{
                      color: "#8B5CF6",
                      backgroundColor: "#8B5CF618",
                    }}
                  >
                    <PackageIcon
                      iconUrl={pack.icon_url}
                      iconName={pack.icon_name}
                      size={22}
                      imageClassName={styles.packageIconImage}
                    />
                  </div>
                  <div className={styles.cardMeta}>
                    <div className={styles.cardTitle}>{pack.name}</div>
                    <div className={styles.cardBadges}>
                      <span className={styles.builtinBadge}>
                        {t("skillPackages.skillCount", {
                          count: pack.skill_count,
                        })}
                      </span>
                      {mounted ? (
                        <span className={styles.enabledBadge}>
                          ✓ {t("common.enabled")}
                        </span>
                      ) : null}
                    </div>
                  </div>
                </div>

                <div
                  className={styles.cardDesc}
                  title={pack.description || undefined}
                >
                  {pack.description || t("skills.noDescription")}
                </div>

                <div className={styles.cardFooter}>
                  <button
                    type="button"
                    className={styles.detailBtn}
                    onClick={(e) => {
                      e.stopPropagation();
                      void openDetail(pack);
                    }}
                  >
                    <Info size={14} />
                    {t("common.viewDetail")}
                  </button>
                  <div
                    className={styles.footerActions}
                    onClick={(e) => e.stopPropagation()}
                  >
                    <Switch
                      checked={mounted}
                      loading={mountingId === pack.id}
                      onChange={(checked) => handleToggleMount(pack, checked)}
                      aria-label={
                        mounted
                          ? t("skills.unmountPackage")
                          : t("skills.mountPackage")
                      }
                    />
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <Drawer
        title={detailPackage?.name ?? t("skills.skillPackages")}
        open={detailOpen}
        onClose={() => {
          setDetailOpen(false);
          setDetailPackage(null);
        }}
        width={480}
        destroyOnClose
      >
        {detailLoading ? (
          <Spin className={styles.skillPackagesLoading} />
        ) : !detailPackage ? null : (
          <>
            {detailPackage.description ? (
              <p className={styles.packageDetailDesc}>
                {detailPackage.description}
              </p>
            ) : null}
            {!detailMounted ? (
              <p className={styles.packageDetailHint}>
                {t("skills.mountPackageToToggleSkills")}
              </p>
            ) : null}
            {detailPackage.skills.length === 0 ? (
              <Empty description={t("skillPackages.emptySkills")} />
            ) : (
              <div className={styles.packageSkillRowList}>
                {detailPackage.skills.map((packageSkill) => {
                  const installed = skillsBySlug.get(packageSkill.slug);
                  const hubInfo = hubSkillsBySlug.get(packageSkill.slug);
                  const { iconUrl, emoji } = resolvePackageSkillIcon(
                    packageSkill,
                    installed,
                    hubInfo?.iconUrl,
                  );
                  const displayName =
                    hubInfo?.name || packageSkill.name || packageSkill.slug;
                  const displayDesc =
                    hubInfo?.description_zh ||
                    packageSkill.description ||
                    t("skills.noDescription");
                  const shadows = workspaceSlugs.has(packageSkill.slug);
                  const canToggle = detailMounted && !!installed && !shadows;

                  return (
                    <div key={packageSkill.slug}>
                      <div className={styles.packageSkillRow}>
                        <div className={styles.packageSkillRowMain}>
                          <div
                            className={styles.packageSkillRowIcon}
                            style={{
                              color: "#059669",
                              background: iconUrl ? "transparent" : "#0596691a",
                            }}
                          >
                            <PackageSkillIcon iconUrl={iconUrl} emoji={emoji} />
                          </div>
                          <div className={styles.packageSkillRowMeta}>
                            <div className={styles.packageSkillRowLabel}>
                              {displayName}
                            </div>
                            <div
                              className={styles.packageSkillRowDesc}
                              title={displayDesc}
                            >
                              {displayDesc}
                            </div>
                          </div>
                        </div>
                        <div className={styles.packageSkillRowAction}>
                          <Switch
                            size="small"
                            checked={installed?.enabled ?? true}
                            disabled={!canToggle}
                            onChange={() => {
                              if (canToggle && installed) {
                                void toggleEnabled(installed);
                              }
                            }}
                          />
                        </div>
                      </div>
                      {shadows ? (
                        <small className={styles.packageConflictHint}>
                          {t("skills.packageConflictHint", {
                            slug: packageSkill.slug,
                          })}
                        </small>
                      ) : null}
                    </div>
                  );
                })}
              </div>
            )}
          </>
        )}
      </Drawer>
    </>
  );
}
