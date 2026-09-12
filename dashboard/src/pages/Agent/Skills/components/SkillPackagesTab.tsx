import { useEffect, useMemo, useState } from "react";
import { Alert, Checkbox, Drawer, Empty, Modal, Spin, Switch } from "antd";
import { Copy, Info } from "lucide-react";
import { message } from "@/utils/antdMessage";
import { useTranslation } from "react-i18next";
import { skillPackagesApi } from "../../../../api/modules/skillPackages";
import type {
  SkillPackage,
  SkillPackageDetail,
  SkillPackageSkill,
} from "../../../../api/types/skillPackage";
import { useAgent } from "../../../../context/AgentContext";
import { PackageIcon } from "../../../SkillPackages/PackageIcon";
import { showApiError } from "../../../../utils/showApiToast";
import { supportsHostSkillPackagesFromConfig } from "../../../Experts/components/agentBackendForm";
import type { SkillSpec } from "../useSkills";
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
): { iconUrl?: string; emoji?: string } {
  const iconUrl = packageSkill.icon_url || installed?.iconUrl || undefined;
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
  const { agents } = useAgent();
  const agent = useMemo(
    () => agents.find((row) => row.agent_id === agentId) ?? null,
    [agents, agentId],
  );
  const packagesSupported = supportsHostSkillPackagesFromConfig(
    agent?.config ?? null,
  );
  const [catalog, setCatalog] = useState<SkillPackage[]>([]);
  const [mountedIds, setMountedIds] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [mountingId, setMountingId] = useState<string | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailPackage, setDetailPackage] = useState<SkillPackageDetail | null>(
    null,
  );
  const [detailLoading, setDetailLoading] = useState(false);
  const [copyPackage, setCopyPackage] = useState<SkillPackageDetail | null>(
    null,
  );
  const [copyModalOpen, setCopyModalOpen] = useState(false);
  const [copyLoading, setCopyLoading] = useState(false);
  const [copying, setCopying] = useState(false);
  const [selectedCopySlugs, setSelectedCopySlugs] = useState<string[]>([]);
  const [copyOverwrite, setCopyOverwrite] = useState(false);

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
    if (enabled && !packagesSupported) return;
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

  const openCopyModal = async (pack: SkillPackage) => {
    setCopyModalOpen(true);
    setCopyLoading(true);
    setCopyPackage(null);
    setSelectedCopySlugs([]);
    setCopyOverwrite(false);
    try {
      const detail = await skillPackagesApi.get(pack.id);
      setCopyPackage(detail);
      setSelectedCopySlugs(detail.skills.map((skill) => skill.slug));
    } catch (error) {
      showApiError(error, t("skills.packagesLoadFailed"), t);
      setCopyModalOpen(false);
    } finally {
      setCopyLoading(false);
    }
  };

  const handleCopySkills = async () => {
    if (!copyPackage || selectedCopySlugs.length === 0) {
      message.warning(t("skills.selectAtLeastOneSkill"));
      return;
    }
    setCopying(true);
    try {
      const result = await skillPackagesApi.copyToWorkspace(
        agentId,
        copyPackage.id,
        {
          skill_slugs: selectedCopySlugs,
          overwrite: copyOverwrite,
        },
      );
      await fetchSkills();
      message.success(
        t("skills.copySkillsSuccess", { count: result.copied.length }),
      );
      setCopyModalOpen(false);
    } catch (error) {
      showApiError(error, t("skills.copySkillsFailed"), t);
    } finally {
      setCopying(false);
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
      {packagesSupported ? (
        <p className={styles.packageMountHint}>
          {t("skills.mountBackendHint")}
        </p>
      ) : (
        <Alert
          type="info"
          showIcon
          className={styles.packageMountAlert}
          message={t("skills.skillPackagesUnsupportedHint")}
        />
      )}
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
                  <div
                    className={styles.packageCardSwitch}
                    onClick={(e) => e.stopPropagation()}
                  >
                    <Switch
                      checked={mounted}
                      disabled={!packagesSupported && !mounted}
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
                    <button
                      type="button"
                      className={styles.detailBtn}
                      onClick={() => void openCopyModal(pack)}
                    >
                      <Copy size={14} />
                      {t("skills.copySkills")}
                    </button>
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
        destroyOnHidden
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
                  const { iconUrl, emoji } = resolvePackageSkillIcon(
                    packageSkill,
                    installed,
                  );
                  const displayName = packageSkill.name || packageSkill.slug;
                  const displayDesc =
                    packageSkill.description || t("skills.noDescription");
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

      <Modal
        title={t("skills.copyPackageSkillsTitle", {
          name: copyPackage?.name ?? "",
        })}
        open={copyModalOpen}
        onCancel={() => setCopyModalOpen(false)}
        onOk={() => void handleCopySkills()}
        okText={t("skills.copySkills")}
        confirmLoading={copying}
        okButtonProps={{
          disabled: copyLoading || selectedCopySlugs.length === 0,
        }}
        destroyOnHidden
      >
        <Alert
          type="info"
          showIcon
          className={styles.skillTransferAlert}
          message={t("skills.copySnapshotWarning")}
        />
        {copyLoading ? (
          <Spin className={styles.skillPackagesLoading} />
        ) : copyPackage?.skills.length ? (
          <Checkbox.Group
            value={selectedCopySlugs}
            onChange={(values) =>
              setSelectedCopySlugs(values.map((value) => String(value)))
            }
            className={styles.skillTransferList}
          >
            {copyPackage.skills.map((skill) => (
              <Checkbox key={skill.slug} value={skill.slug}>
                <span className={styles.skillTransferSkillName}>
                  {skill.name || skill.slug}
                </span>
                <span className={styles.skillTransferSkillSlug}>
                  {skill.slug}
                </span>
              </Checkbox>
            ))}
          </Checkbox.Group>
        ) : (
          <Empty description={t("skillPackages.emptySkills")} />
        )}
        {!copyLoading && copyPackage?.skills.length ? (
          <Checkbox
            checked={copyOverwrite}
            onChange={(event) => setCopyOverwrite(event.target.checked)}
          >
            {t("skills.overwriteExisting")}
          </Checkbox>
        ) : null}
      </Modal>
    </>
  );
}
