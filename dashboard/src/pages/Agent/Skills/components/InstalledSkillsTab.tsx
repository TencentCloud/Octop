import { useMemo, useState, useCallback, useEffect } from "react";
import { Checkbox, Form, Segmented, Tooltip } from "antd";
import {
  Download,
  FileDown,
  LayoutGrid,
  List,
  Plus,
  RefreshCw,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { useAgent } from "../../../../context/AgentContext";
import { isAgentChatReady } from "../../../../utils/agentError";
import { CardSkeleton } from "../../../../components/Skeleton";
import { useCardTableView } from "../../../../hooks/useCardTableView";
import { EmptyState } from "../../../../components/EmptyState";
import { SkillCard } from "./SkillCard";
import { SkillDrawer, type SkillFormValues } from "./SkillDrawer";
import { SkillImportModal } from "./SkillImportModal";
import { PushSkillToPackageModal } from "./PushSkillToPackageModal";
import SkillsTable from "./SkillsTable";
import type { SkillDetail, SkillSpec } from "../useSkills";
import styles from "../index.module.less";

interface InstalledSkillsTabProps {
  kind: "custom" | "builtin";
  agentId: string;
  skills: SkillSpec[];
  loading: boolean;
  fetchSkills: () => Promise<void>;
  getDetail: (slug: string) => Promise<SkillDetail | null>;
  createSkill: (name: string, content: string) => Promise<boolean>;
  updateSkill: (slug: string, content: string) => Promise<boolean>;
  importFromUrl: (
    bundleUrl: string,
    options?: { overwrite?: boolean },
  ) => Promise<boolean>;
  importFromZip: (
    skills: Array<{
      slug: string;
      files: Array<{ path: string; contentBase64: string }>;
    }>,
    options?: { overwrite?: boolean },
  ) => Promise<
    | false
    | {
        imported: number;
        skipped: number;
        failed: number;
      }
  >;
  importing: boolean;
  toggleEnabled: (skill: SkillSpec) => Promise<boolean>;
  deleteSkill: (skill: SkillSpec) => Promise<boolean>;
  exportSkills: (slugs: string[]) => Promise<boolean>;
}

export default function InstalledSkillsTab({
  kind,
  agentId,
  skills,
  loading,
  fetchSkills,
  getDetail,
  createSkill,
  updateSkill,
  importFromUrl,
  importFromZip,
  importing,
  toggleEnabled,
  deleteSkill,
  exportSkills,
}: InstalledSkillsTabProps) {
  const { t } = useTranslation();
  const { agents } = useAgent();
  const workspaceReady = useMemo(
    () =>
      isAgentChatReady(
        agents.find((agent) => agent.agent_id === agentId)?.state,
      ),
    [agentId, agents],
  );

  const { viewMode, setViewMode, showCardView } = useCardTableView("card");
  const [refreshing, setRefreshing] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [importModalOpen, setImportModalOpen] = useState(false);
  const [editingSkill, setEditingSkill] = useState<SkillDetail | null>(null);
  const [pushSkill, setPushSkill] = useState<SkillDetail | null>(null);
  const [hoverKey, setHoverKey] = useState<string | null>(null);
  const [form] = Form.useForm<SkillFormValues>();
  const [selectedSlugs, setSelectedSlugs] = useState<Set<string>>(
    () => new Set(),
  );

  const filteredSkills = useMemo(
    () =>
      skills
        .filter((s) =>
          kind === "builtin" ? s.kind === "builtin" : s.kind === "workspace",
        )
        .slice()
        .sort((a, b) => {
          if (a.enabled && !b.enabled) return -1;
          if (!a.enabled && b.enabled) return 1;
          return a.slug.localeCompare(b.slug);
        }),
    [skills, kind],
  );

  useEffect(() => {
    const live = new Set(filteredSkills.map((skill) => skill.slug));
    setSelectedSlugs((current) => {
      const next = new Set([...current].filter((slug) => live.has(slug)));
      return next.size === current.size ? current : next;
    });
  }, [filteredSkills]);

  const selectedSkills = useMemo(
    () => filteredSkills.filter((skill) => selectedSlugs.has(skill.slug)),
    [filteredSkills, selectedSlugs],
  );
  const allSelected =
    filteredSkills.length > 0 &&
    selectedSkills.length === filteredSkills.length;

  const toggleSelected = (slug: string) => {
    setSelectedSlugs((current) => {
      const next = new Set(current);
      if (next.has(slug)) next.delete(slug);
      else next.add(slug);
      return next;
    });
  };

  const toggleSelectAll = () => {
    setSelectedSlugs(
      allSelected
        ? new Set()
        : new Set(filteredSkills.map((skill) => skill.slug)),
    );
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
    const ok = editingSkill
      ? await updateSkill(editingSkill.slug, content)
      : await createSkill(values.name, content);
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
            isHover={hoverKey === skill.slug}
            onClick={() => void handleEdit(skill)}
            onMouseEnter={() => setHoverKey(skill.slug)}
            onMouseLeave={() => setHoverKey(null)}
            onToggleEnabled={(e) => void handleToggleEnabled(skill, e)}
            onDelete={
              kind === "custom" ? (e) => void handleDelete(skill, e) : undefined
            }
            selected={kind === "custom" && selectedSlugs.has(skill.slug)}
            onToggleSelected={
              kind === "custom" ? () => toggleSelected(skill.slug) : undefined
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
        selectedSlugs={kind === "custom" ? selectedSlugs : undefined}
        onSelectedSlugsChange={
          kind === "custom"
            ? (slugs) => setSelectedSlugs(new Set(slugs))
            : undefined
        }
      />
    );

  return (
    <>
      <div className={styles.gridToolbar}>
        <span className={styles.gridCount}>
          {kind === "custom" && showCardView && filteredSkills.length > 0 ? (
            <Checkbox
              checked={allSelected}
              indeterminate={selectedSkills.length > 0 && !allSelected}
              onChange={toggleSelectAll}
            >
              {t("skills.totalCount", { count: filteredSkills.length })}
            </Checkbox>
          ) : (
            t("skills.totalCount", { count: filteredSkills.length })
          )}
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
                disabled={selectedSkills.length === 0}
                onClick={() =>
                  void exportSkills(selectedSkills.map((skill) => skill.slug))
                }
              >
                <FileDown size={14} />
                {t("skills.exportSelected", { count: selectedSkills.length })}
              </button>
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
        <SkillImportModal
          open={importModalOpen}
          importing={importing}
          onClose={() => setImportModalOpen(false)}
          onImportUrl={importFromUrl}
          onImportZip={importFromZip}
        />
      ) : null}

      <div className={styles.skillsListArea}>{listContent}</div>

      <SkillDrawer
        open={drawerOpen}
        editingSkill={editingSkill}
        form={form}
        agentId={agentId}
        workspaceReady={workspaceReady}
        onClose={handleDrawerClose}
        onSubmit={handleSubmit}
        onPushToPackage={
          kind === "custom" ? (skill) => setPushSkill(skill) : undefined
        }
      />
      {kind === "custom" ? (
        <PushSkillToPackageModal
          open={pushSkill != null}
          agentId={agentId}
          skill={pushSkill}
          onClose={() => setPushSkill(null)}
        />
      ) : null}
    </>
  );
}
