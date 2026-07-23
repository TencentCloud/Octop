import { useMemo, useState, useCallback } from "react";
import { Form, Modal, Segmented, Tooltip, Button } from "antd";
import { Download, LayoutGrid, List, Plus, RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";
import { CardSkeleton } from "../../../../components/Skeleton";
import { useCardTableView } from "../../../../hooks/useCardTableView";
import { EmptyState } from "../../../../components/EmptyState";
import { SkillCard, type SkillHubInfo } from "./SkillCard";
import { SkillDrawer, type SkillFormValues } from "./SkillDrawer";
import { loadRankingsCache } from "./skillHubCache";
import SkillsTable from "./SkillsTable";
import type { SkillDetail, SkillSpec } from "../useSkills";
import styles from "../index.module.less";

interface InstalledSkillsTabProps {
  kind: "custom" | "builtin";
  skills: SkillSpec[];
  loading: boolean;
  fetchSkills: () => Promise<void>;
  getDetail: (slug: string) => Promise<SkillDetail | null>;
  createSkill: (name: string, content: string) => Promise<boolean>;
  importFromUrl: (bundleUrl: string) => Promise<boolean>;
  importing: boolean;
  toggleEnabled: (skill: SkillSpec) => Promise<boolean>;
  deleteSkill: (skill: SkillSpec) => Promise<boolean>;
}

export default function InstalledSkillsTab({
  kind,
  skills,
  loading,
  fetchSkills,
  getDetail,
  createSkill,
  importFromUrl,
  importing,
  toggleEnabled,
  deleteSkill,
}: InstalledSkillsTabProps) {
  const { t } = useTranslation();

  const { viewMode, setViewMode, showCardView } = useCardTableView("card");
  const [refreshing, setRefreshing] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [importModalOpen, setImportModalOpen] = useState(false);
  const [importUrl, setImportUrl] = useState("");
  const [importUrlError, setImportUrlError] = useState("");
  const [editingSkill, setEditingSkill] = useState<SkillDetail | null>(null);
  const [hoverKey, setHoverKey] = useState<string | null>(null);
  const [form] = Form.useForm<SkillFormValues>();

  const hubSkillsBySlug = useMemo(() => {
    const bySlug = new Map<string, SkillHubInfo>();
    const cached = loadRankingsCache() ?? {};
    for (const rows of Object.values(cached)) {
      for (const row of rows) bySlug.set(row.slug, row);
    }
    return bySlug;
  }, []);

  const filteredSkills = useMemo(
    () =>
      skills
        .filter((s) =>
          kind === "builtin" ? s.kind === "builtin" : s.kind !== "builtin",
        )
        .slice()
        .sort((a, b) => {
          if (a.enabled && !b.enabled) return -1;
          if (!a.enabled && b.enabled) return 1;
          return a.slug.localeCompare(b.slug);
        }),
    [skills, kind],
  );

  const currentSkillUrlPrefixes = [
    "https://skills.sh/",
    "https://clawhub.ai/",
    "https://skillsmp.com/",
    "https://github.com/",
  ];

  const isValidSkillUrl = (value: string) => {
    try {
      const parsed = new URL(value);
      return parsed.protocol === "http:" || parsed.protocol === "https:";
    } catch {
      return false;
    }
  };

  const onViewChange = (value: string | number) => {
    setViewMode(value === "table" ? "table" : "card");
  };

  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    try {
      await fetchSkills();
    } finally {
      setRefreshing(false);
    }
  }, [fetchSkills]);

  const closeImportModal = () => {
    if (importing) return;
    setImportModalOpen(false);
    setImportUrl("");
    setImportUrlError("");
  };

  const handleImportUrlChange = (value: string) => {
    setImportUrl(value);
    const trimmed = value.trim();
    if (trimmed && !isValidSkillUrl(trimmed)) {
      setImportUrlError(t("skills.invalidSkillUrlSource"));
      return;
    }
    setImportUrlError("");
  };

  const handleConfirmImport = async () => {
    if (importing) return;
    const trimmed = importUrl.trim();
    if (!trimmed) return;
    if (!isValidSkillUrl(trimmed)) {
      setImportUrlError(t("skills.invalidSkillUrlSource"));
      return;
    }
    const success = await importFromUrl(trimmed);
    if (success) closeImportModal();
  };

  const handleCreate = () => {
    setEditingSkill(null);
    form.resetFields();
    setDrawerOpen(true);
  };

  const handleEdit = async (skill: SkillSpec) => {
    const detail = await getDetail(skill.slug);
    if (detail) {
      setEditingSkill(detail);
      setDrawerOpen(true);
    }
  };

  const handleToggleEnabled = async (
    skill: SkillSpec,
    e?: React.MouseEvent,
  ) => {
    e?.stopPropagation();
    await toggleEnabled(skill);
  };

  const handleDelete = async (skill: SkillSpec, e?: React.MouseEvent) => {
    e?.stopPropagation();
    await deleteSkill(skill);
  };

  const handleDrawerClose = () => {
    setDrawerOpen(false);
    setEditingSkill(null);
  };

  const handleSubmit = async (values: SkillFormValues) => {
    const content = values.content ?? "";
    const ok = await createSkill(values.name, content);
    if (ok) setDrawerOpen(false);
  };

  const emptyTitle =
    kind === "builtin" ? t("skills.builtinSkills") : t("skills.noSkills");
  const emptyDesc =
    kind === "builtin"
      ? t("skills.builtinSkillsDesc")
      : t("skills.noSkillsDesc");

  const listContent =
    loading && skills.length === 0 ? (
      <CardSkeleton count={6} />
    ) : filteredSkills.length === 0 ? (
      <EmptyState
        title={emptyTitle}
        description={emptyDesc}
        actionLabel={kind === "custom" ? t("skills.createSkill") : undefined}
        onAction={kind === "custom" ? handleCreate : undefined}
      />
    ) : showCardView ? (
      <div className={styles.skillsGrid}>
        {filteredSkills.map((skill) => (
          <SkillCard
            key={`${skill.kind}-${skill.slug}`}
            skill={skill}
            hubInfo={hubSkillsBySlug.get(skill.slug)}
            isHover={hoverKey === skill.slug}
            onClick={() => void handleEdit(skill)}
            onMouseEnter={() => setHoverKey(skill.slug)}
            onMouseLeave={() => setHoverKey(null)}
            onToggleEnabled={(e) => void handleToggleEnabled(skill, e)}
            onDelete={
              kind === "custom" ? (e) => void handleDelete(skill, e) : undefined
            }
          />
        ))}
      </div>
    ) : (
      <SkillsTable
        skills={filteredSkills}
        kind={kind}
        onView={(skill) => void handleEdit(skill)}
        onToggleEnabled={(skill) => void handleToggleEnabled(skill)}
        onDelete={
          kind === "custom" ? (skill) => void handleDelete(skill) : undefined
        }
      />
    );

  return (
    <>
      <div className={styles.gridToolbar}>
        <span className={styles.gridCount}>
          {t("skills.totalCount", { count: filteredSkills.length })}
        </span>
        <div className={styles.gridToolbarRight}>
          <Segmented
            size="small"
            value={viewMode}
            onChange={onViewChange}
            options={[
              {
                value: "card",
                label: (
                  <span className={styles.viewModeLabel}>
                    <LayoutGrid size={14} />
                    {t("experts.viewCard")}
                  </span>
                ),
              },
              {
                value: "table",
                label: (
                  <span className={styles.viewModeLabel}>
                    <List size={14} />
                    {t("experts.viewTable")}
                  </span>
                ),
              },
            ]}
          />
          <Tooltip title={t("common.refresh")}>
            <button
              type="button"
              className={styles.toolbarIconBtn}
              onClick={() => void handleRefresh()}
              disabled={refreshing || loading}
            >
              <RefreshCw
                size={14}
                className={refreshing ? styles.spinning : undefined}
              />
            </button>
          </Tooltip>
          {kind === "custom" ? (
            <>
              <button
                type="button"
                className={styles.toolbarBtn}
                onClick={() => setImportModalOpen(true)}
              >
                <Download size={14} />
                {t("skills.importSkills")}
              </button>
              <button
                type="button"
                className={styles.toolbarBtnPrimary}
                onClick={handleCreate}
              >
                <Plus size={14} />
                {t("skills.createSkill")}
              </button>
            </>
          ) : null}
        </div>
      </div>

      {kind === "custom" ? (
        <Modal
          title={t("skills.importSkills")}
          open={importModalOpen}
          onCancel={closeImportModal}
          maskClosable={!importing}
          closable={!importing}
          keyboard={!importing}
          footer={
            <div style={{ textAlign: "right" }}>
              <Button
                onClick={closeImportModal}
                disabled={importing}
                style={{ marginRight: 8 }}
              >
                {t("common.cancel")}
              </Button>
              <Button
                type="primary"
                onClick={() => void handleConfirmImport()}
                loading={importing}
                disabled={importing || !importUrl.trim() || !!importUrlError}
              >
                {t("skills.importSkills")}
              </Button>
            </div>
          }
          width={760}
        >
          <div className={styles.importHintBlock}>
            <p className={styles.importHintTitle}>
              {t("skills.supportedSkillUrlSources")}
            </p>
            <div className={styles.importHintSources}>
              {currentSkillUrlPrefixes.map((prefix) => (
                <code key={prefix} className={styles.importHintCode}>
                  {prefix}
                </code>
              ))}
            </div>
            <p className={styles.importHintTitle} style={{ marginTop: 10 }}>
              {t("skills.urlExamples")}
            </p>
            <div className={styles.importHintExamples}>
              <code className={styles.importHintCode}>
                https://skills.sh/vercel-labs/skills/find-skills
              </code>
              <code className={styles.importHintCode}>
                https://github.com/anthropics/skills/tree/main/skills/skill-creator
              </code>
            </div>
          </div>

          <input
            className={styles.importUrlInput}
            value={importUrl}
            onChange={(e) => handleImportUrlChange(e.target.value)}
            placeholder={t("skills.enterSkillUrl")}
            disabled={importing}
          />
          {importUrlError ? (
            <div className={styles.importUrlError}>{importUrlError}</div>
          ) : null}
          {importing ? (
            <div className={styles.importLoadingText}>
              {t("common.loading")}
            </div>
          ) : null}
        </Modal>
      ) : null}

      <div className={styles.skillsListArea}>{listContent}</div>

      <SkillDrawer
        open={drawerOpen}
        editingSkill={editingSkill}
        form={form}
        onClose={handleDrawerClose}
        onSubmit={handleSubmit}
      />
    </>
  );
}
