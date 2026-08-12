import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type CSSProperties,
} from "react";
import {
  Button,
  Drawer,
  Empty,
  Form,
  Input,
  List,
  Modal,
  Popconfirm,
  Select,
  Segmented,
  Spin,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import { message } from "@/utils/antdMessage";

import {
  ChevronLeft,
  Download,
  LayoutGrid,
  List as ListIcon,
  Pencil,
  Plus,
  RefreshCw,
  Store,
  Trash2,
} from "lucide-react";
import { useTranslation } from "react-i18next";

import { authApi, type OctopUser } from "../../api/modules/auth";
import { skillPackagesApi } from "../../api/modules/skillPackages";
import type {
  SkillPackage,
  SkillPackageDetail,
  SkillPackageSkillDetail,
} from "../../api/types/skillPackage";
import { CardSkeleton } from "../../components/Skeleton";
import { EmptyState, OctopEmptyMascot } from "../../components/EmptyState";
import { useCardTableView } from "../../hooks/useCardTableView";
import { useHorizontalResize } from "../../hooks/useHorizontalResize";
import { useIsMobile } from "../../hooks/useIsMobile";
import PageShell from "../../layouts/PageShell";
import { apiErrorMessage, parseApiError } from "../../utils/apiError";
import {
  SkillDrawer,
  type SkillFormValues,
} from "../Agent/Skills/components/SkillDrawer";
import {
  SkillImportModal,
  type ZipImportSummary,
} from "../Agent/Skills/components/SkillImportModal";
import SkillHubTab from "../Agent/Skills/components/SkillHubTab";
import skillStyles from "../Agent/Skills/index.module.less";
import type { ParsedZipSkill } from "../Agent/Skills/components/parseSkillZip";
import {
  EXPERT_ICON_NAMES,
  iconForName,
} from "../Experts/components/iconForName";
import { createDetailRequestGate } from "./detailRequestGate";
import { PackageIcon } from "./PackageIcon";
import { PackageSkillCard } from "./PackageSkillCard";
import PackageSkillsTable from "./PackageSkillsTable";
import { SkillsetFromHubDrawer } from "./SkillsetFromHubDrawer";
import styles from "./index.module.less";

type PackageFormValues = {
  name: string;
  description?: string;
  icon_name?: string;
  icon_url?: string;
};

const EMPTY_SKILL = "---\nname: \ndescription: \n---\n\n";
const SKILL_URL_PREFIXES = [
  "https://skills.sh/",
  "https://clawhub.ai/",
  "https://skillsmp.com/",
  "https://github.com/",
];

function formatPackageCreator(
  item: Pick<
    SkillPackage,
    "creator_display_name" | "creator_username" | "created_by"
  >,
): string {
  const displayName = item.creator_display_name?.trim() || "";
  const username = item.creator_username?.trim() || "";
  return displayName || username || item.created_by;
}

export default function SkillPackagesPage() {
  const { t } = useTranslation();
  const isMobile = useIsMobile();
  const { viewMode, setViewMode, showCardView } = useCardTableView("card");
  const [packages, setPackages] = useState<SkillPackage[]>([]);
  const [selected, setSelected] = useState<SkillPackageDetail | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [mobilePane, setMobilePane] = useState<"list" | "detail">("list");
  const [user, setUser] = useState<OctopUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [packageModalOpen, setPackageModalOpen] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [importModalOpen, setImportModalOpen] = useState(false);
  const [hubOpen, setHubOpen] = useState(false);
  const [skillsetHubOpen, setSkillsetHubOpen] = useState(false);
  const [importing, setImporting] = useState(false);
  const [editingPackage, setEditingPackage] = useState(false);
  const [editingSkill, setEditingSkill] =
    useState<SkillPackageSkillDetail | null>(null);
  const [packageForm] = Form.useForm<PackageFormValues>();
  const [skillForm] = Form.useForm<SkillFormValues>();
  const iconName = Form.useWatch("icon_name", packageForm);
  const iconUrl = Form.useWatch("icon_url", packageForm);
  const detailRequestGate = useRef(createDetailRequestGate());
  const initialLoadDone = useRef(false);

  const {
    size: sidebarWidth,
    isResizing,
    onResizeStart,
  } = useHorizontalResize({
    min: 200,
    max: 480,
    defaultSize: 280,
    storageKey: "octop:skill-packages:sidebar-width",
  });

  const loadPackages = useCallback(
    async (opts?: { silent?: boolean }) => {
      const silent = Boolean(opts?.silent || initialLoadDone.current);
      if (!silent) setLoading(true);
      try {
        const rows = await skillPackagesApi.list();
        setPackages(rows);
        setSelected((current) =>
          current && !rows.some((row) => row.id === current.id)
            ? null
            : current,
        );
        setSelectedId((currentId) =>
          currentId && !rows.some((row) => row.id === currentId)
            ? null
            : currentId,
        );
        initialLoadDone.current = true;
      } catch (error) {
        message.error(apiErrorMessage(error, t("skillPackages.loadFailed"), t));
      } finally {
        if (!silent) setLoading(false);
      }
    },
    [t],
  );

  const loadDetail = useCallback(
    async (packageId: string) => {
      const requestId = detailRequestGate.current.begin();
      setDetailLoading(true);
      try {
        const detail = await skillPackagesApi.get(packageId);
        if (detailRequestGate.current.isCurrent(requestId)) {
          setSelected(detail);
          setSelectedId(detail.id);
        }
      } catch (error) {
        if (detailRequestGate.current.isCurrent(requestId)) {
          message.error(
            apiErrorMessage(error, t("skillPackages.loadFailed"), t),
          );
        }
      } finally {
        if (detailRequestGate.current.isCurrent(requestId)) {
          setDetailLoading(false);
        }
      }
    },
    [t],
  );

  useEffect(() => {
    void loadPackages();
    void authApi
      .me()
      .then(setUser)
      .catch(() => setUser(null));
  }, [loadPackages]);

  useEffect(() => {
    if (
      isMobile ||
      loading ||
      detailLoading ||
      selectedId ||
      packages.length === 0
    ) {
      return;
    }
    void loadDetail(packages[0].id);
  }, [isMobile, loading, detailLoading, selectedId, packages, loadDetail]);

  useEffect(() => {
    if (!isMobile) setMobilePane("list");
  }, [isMobile]);

  const canMutate = Boolean(
    selected &&
      user &&
      (user.role === "admin" || selected.created_by === String(user.id)),
  );

  const selectPackage = (item: SkillPackage) => {
    if (item.id !== selectedId) {
      setSelectedId(item.id);
      void loadDetail(item.id);
    }
    if (isMobile) setMobilePane("detail");
  };

  const refreshSelected = async () => {
    if (!selectedId) {
      await loadPackages({ silent: true });
      return;
    }
    const packageId = selectedId;
    await Promise.all([loadDetail(packageId), loadPackages({ silent: true })]);
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      await refreshSelected();
    } finally {
      setRefreshing(false);
    }
  };

  const openCreatePackage = () => {
    setEditingPackage(false);
    packageForm.setFieldsValue({
      name: "",
      description: "",
      icon_name: undefined,
      icon_url: "",
    });
    setPackageModalOpen(true);
  };

  const openEditPackage = () => {
    if (!selected) return;
    setEditingPackage(true);
    packageForm.setFieldsValue({
      name: selected.name,
      description: selected.description,
      icon_name: selected.icon_name,
      icon_url: selected.icon_url,
    });
    setPackageModalOpen(true);
  };

  const savePackage = async () => {
    const values = await packageForm.validateFields();
    const payload = {
      ...values,
      icon_url: values.icon_url?.trim() || undefined,
    };
    try {
      const next =
        editingPackage && selected
          ? await skillPackagesApi.update(selected.id, payload)
          : await skillPackagesApi.create(payload);
      setPackageModalOpen(false);
      await loadPackages({ silent: true });
      setSelected(next);
      setSelectedId(next.id);
      if (isMobile) setMobilePane("detail");
      message.success(
        t(editingPackage ? "skillPackages.updated" : "skillPackages.created"),
      );
    } catch (error) {
      message.error(apiErrorMessage(error, t("skillPackages.saveFailed"), t));
    }
  };

  const deletePackage = async () => {
    if (!selected) return;
    const deletedId = selected.id;
    try {
      await skillPackagesApi.delete(deletedId);
      // Drop current selection immediately so refresh cannot hit the deleted id.
      detailRequestGate.current.begin();
      setSelected(null);
      setSelectedId(null);
      setDetailLoading(false);
      const rows = await skillPackagesApi.list();
      setPackages(rows);
      initialLoadDone.current = true;
      if (isMobile) {
        setMobilePane("list");
      } else if (rows.length > 0) {
        setSelectedId(rows[0].id);
        await loadDetail(rows[0].id);
      }
      message.success(t("skillPackages.deleted"));
    } catch (error) {
      message.error(apiErrorMessage(error, t("skillPackages.deleteFailed"), t));
    }
  };

  const openCreateSkill = () => {
    setEditingSkill(null);
    skillForm.setFieldsValue({
      name: "",
      description: "",
      body: "",
      content: EMPTY_SKILL,
    });
    setDrawerOpen(true);
  };

  const openEditSkill = async (slug: string) => {
    if (!selected) return;
    try {
      const detail = await skillPackagesApi.getSkill(selected.id, slug);
      setEditingSkill(detail);
      skillForm.setFieldsValue({
        name: detail.slug,
        description: detail.description,
        body: detail.body,
        content: detail.raw,
      });
      setDrawerOpen(true);
    } catch (error) {
      message.error(apiErrorMessage(error, t("skillPackages.loadFailed"), t));
    }
  };

  const saveSkill = async (values: SkillFormValues) => {
    if (!selected) return;
    try {
      if (editingSkill) {
        await skillPackagesApi.updateSkill(selected.id, editingSkill.slug, {
          content: values.content,
        });
      } else {
        await skillPackagesApi.createSkill(selected.id, {
          name: values.name,
          content: values.content,
        });
      }
      setDrawerOpen(false);
      await refreshSelected();
      message.success(t("skillPackages.skillSaved"));
    } catch (error) {
      message.error(apiErrorMessage(error, t("skillPackages.saveFailed"), t));
    }
  };

  const deleteSkill = async (slug: string) => {
    if (!selected) return;
    try {
      await skillPackagesApi.deleteSkill(selected.id, slug);
      await refreshSelected();
      message.success(t("skillPackages.skillDeleted"));
    } catch (error) {
      message.error(apiErrorMessage(error, t("skillPackages.deleteFailed"), t));
    }
  };

  const confirmImport = async (
    bundleUrl: string,
    options?: { overwrite?: boolean },
  ): Promise<boolean> => {
    if (!selected || importing) return false;
    setImporting(true);
    try {
      await skillPackagesApi.importSkill(selected.id, {
        bundle_url: bundleUrl,
        overwrite: Boolean(options?.overwrite),
      });
      await refreshSelected();
      message.success(t("skills.importSuccess"));
      return true;
    } catch (error) {
      message.error(apiErrorMessage(error, t("skills.importFailed"), t));
      return false;
    } finally {
      setImporting(false);
    }
  };

  const confirmImportZip = async (
    skillsToImport: ParsedZipSkill[],
    options?: { overwrite?: boolean },
  ): Promise<ZipImportSummary | false> => {
    if (!selected || importing) return false;
    const overwrite = Boolean(options?.overwrite);
    let imported = 0;
    let skipped = 0;
    let failed = 0;
    setImporting(true);
    try {
      for (const skill of skillsToImport) {
        try {
          await skillPackagesApi.createSkill(selected.id, {
            name: skill.slug,
            files: skill.files.map((file) => ({
              path: file.path,
              content_base64: file.contentBase64,
            })),
            overwrite,
          });
          imported += 1;
        } catch (error) {
          const code = parseApiError(error)?.code;
          if (!overwrite && code === "SKILL_ALREADY_EXISTS") {
            skipped += 1;
            continue;
          }
          failed += 1;
        }
      }
      await refreshSelected();
      message.success(
        t("skills.zipImportSummary", { imported, skipped, failed }),
      );
      return { imported, skipped, failed };
    } finally {
      setImporting(false);
    }
  };

  const skills = selected?.skills ?? [];
  const skillsContent =
    detailLoading && !selected ? (
      <CardSkeleton count={6} />
    ) : skills.length === 0 ? (
      <EmptyState
        variant="mascot"
        title={t("skillPackages.emptySkills")}
        description={t("skillPackages.subtitle")}
        actionLabel={canMutate ? t("skillPackages.createSkill") : undefined}
        onAction={canMutate ? openCreateSkill : undefined}
      />
    ) : showCardView ? (
      <div className={skillStyles.skillsGrid}>
        {skills.map((skill) => (
          <PackageSkillCard
            key={skill.slug}
            skill={skill}
            canMutate={canMutate}
            onClick={() => void openEditSkill(skill.slug)}
            onDelete={
              canMutate ? () => void deleteSkill(skill.slug) : undefined
            }
          />
        ))}
      </div>
    ) : (
      <PackageSkillsTable
        skills={skills}
        canMutate={canMutate}
        onView={(skill) => void openEditSkill(skill.slug)}
        onDelete={
          canMutate ? (skill) => void deleteSkill(skill.slug) : undefined
        }
      />
    );

  const showListPane = !isMobile || mobilePane === "list";
  const showDetailPane = !isMobile || mobilePane === "detail";

  return (
    <PageShell
      title={t("skillPackages.title")}
      subtitle={isMobile ? undefined : t("skillPackages.subtitle")}
      fill
    >
      <div
        className={`${styles.layout}${
          isResizing ? ` ${styles.layoutResizing}` : ""
        }${isMobile ? ` ${styles.layoutMobile}` : ""}`}
        style={
          {
            "--skill-packages-sidebar-width": `${sidebarWidth}px`,
          } as CSSProperties
        }
      >
        {showListPane ? (
          <aside className={styles.packageList}>
            <div className={styles.packageListActions}>
              <Button
                type="primary"
                icon={<Plus size={15} />}
                onClick={openCreatePackage}
              >
                {t("skillPackages.createPackage")}
              </Button>
              <Tooltip title={t("skillPackages.fromSkillHub")}>
                <Button
                  icon={<Store size={15} />}
                  aria-label={t("skillPackages.fromSkillHub")}
                  onClick={() => setSkillsetHubOpen(true)}
                />
              </Tooltip>
            </div>
            {loading && packages.length === 0 ? (
              <div className={styles.centered}>
                <Spin />
              </div>
            ) : (
              <List
                className={styles.list}
                split={false}
                dataSource={packages}
                locale={{
                  emptyText: (
                    <Empty
                      image={Empty.PRESENTED_IMAGE_SIMPLE}
                      description={t("skillPackages.empty")}
                    />
                  ),
                }}
                renderItem={(item) => (
                  <List.Item
                    className={styles.listRow}
                    onClick={() => selectPackage(item)}
                  >
                    <div
                      className={`${styles.listItem} ${
                        item.id === selectedId ? styles.active : ""
                      }`}
                    >
                      <div className={styles.listName}>
                        <span className={styles.listIcon}>
                          <PackageIcon
                            iconUrl={item.icon_url}
                            iconName={item.icon_name}
                            size={24}
                            imageClassName={styles.listIconImage}
                          />
                        </span>
                        <span>{item.name}</span>
                      </div>
                      <div className={styles.listDescription}>
                        {item.description || "—"}
                      </div>
                      <div className={styles.listMeta}>
                        <span className={styles.listCreator}>
                          {t("skillPackages.createdBy", {
                            name: formatPackageCreator(item),
                          })}
                        </span>
                        <Tag className={styles.listCountTag}>
                          {t("skillPackages.skillCount", {
                            count: item.skill_count,
                          })}
                        </Tag>
                      </div>
                    </div>
                  </List.Item>
                )}
              />
            )}
          </aside>
        ) : null}

        {!isMobile ? (
          <div data-split-divider="" className={styles.splitDivider}>
            <div
              className={styles.resizeHandle}
              role="separator"
              aria-orientation="vertical"
              aria-label={t("skillPackages.resizeSidebar")}
              onPointerDown={onResizeStart}
            />
          </div>
        ) : null}

        {showDetailPane ? (
          <section className={styles.detail}>
            {detailLoading ? (
              <div className={styles.detailLoadingOverlay}>
                <Spin />
              </div>
            ) : null}
            {!selected && !detailLoading ? (
              <div className={styles.emptyDetail}>
                <OctopEmptyMascot size={180} />
                <p className={styles.emptyDetailText}>
                  {t("skillPackages.selectPackage")}
                </p>
              </div>
            ) : !selected ? null : (
              <>
                <div className={styles.detailHeader}>
                  <div className={styles.detailTitleRow}>
                    <div className={styles.detailTitleGroup}>
                      {isMobile ? (
                        <button
                          type="button"
                          className={styles.mobileBackBtn}
                          onClick={() => setMobilePane("list")}
                          aria-label={t("skillPackages.backToList")}
                        >
                          <ChevronLeft size={18} />
                        </button>
                      ) : null}
                      <Typography.Title
                        level={4}
                        className={styles.detailTitle}
                      >
                        {selected.name}
                      </Typography.Title>
                    </div>
                    {canMutate ? (
                      <div className={styles.actions}>
                        <Button
                          icon={<Pencil size={14} />}
                          onClick={openEditPackage}
                        >
                          {t("common.edit")}
                        </Button>
                        <Popconfirm
                          title={t("skillPackages.deletePackageConfirm")}
                          description={t(
                            "skillPackages.deletePackageMountedHint",
                          )}
                          okText={t("common.delete")}
                          cancelText={t("common.cancel")}
                          onConfirm={() => void deletePackage()}
                        >
                          <Button danger icon={<Trash2 size={14} />}>
                            {t("common.delete")}
                          </Button>
                        </Popconfirm>
                      </div>
                    ) : null}
                  </div>
                  <Typography.Paragraph
                    type="secondary"
                    className={styles.detailDescription}
                  >
                    {selected.description || t("skillPackages.noDescription")}
                  </Typography.Paragraph>
                  <Typography.Paragraph
                    type="secondary"
                    className={styles.detailCreator}
                  >
                    {t("skillPackages.createdBy", {
                      name: formatPackageCreator(selected),
                    })}
                  </Typography.Paragraph>
                </div>

                  <div className={styles.detailBody}>
                  <div
                    className={`${skillStyles.gridToolbar} ${styles.skillsToolbar}`}
                  >
                    <span className={skillStyles.gridCount}>
                      {t("skills.totalCount", { count: skills.length })}
                    </span>
                    <div className={skillStyles.gridToolbarRight}>
                      <Segmented
                        size="small"
                        value={viewMode}
                        onChange={(value) =>
                          setViewMode(value === "table" ? "table" : "card")
                        }
                        options={[
                          {
                            value: "card",
                            label: (
                              <span className={skillStyles.viewModeLabel}>
                                <LayoutGrid size={14} />
                                {t("experts.viewCard")}
                              </span>
                            ),
                          },
                          {
                            value: "table",
                            label: (
                              <span className={skillStyles.viewModeLabel}>
                                <ListIcon size={14} />
                                {t("experts.viewTable")}
                              </span>
                            ),
                          },
                        ]}
                      />
                      <Tooltip title={t("common.refresh")}>
                        <button
                          type="button"
                          className={skillStyles.toolbarIconBtn}
                          onClick={() => void handleRefresh()}
                          disabled={refreshing || detailLoading}
                        >
                          <RefreshCw
                            size={14}
                            className={
                              refreshing ? skillStyles.spinning : undefined
                            }
                          />
                        </button>
                      </Tooltip>
                      {canMutate ? (
                        <>
                          <button
                            type="button"
                            className={skillStyles.toolbarBtn}
                            onClick={() => setHubOpen(true)}
                          >
                            <Store size={14} />
                            {t("skills.tencentSkillHub")}
                          </button>
                          <button
                            type="button"
                            className={skillStyles.toolbarBtn}
                            onClick={() => setImportModalOpen(true)}
                          >
                            <Download size={14} />
                            {t("skills.importSkills")}
                          </button>
                          <button
                            type="button"
                            className={skillStyles.toolbarBtnPrimary}
                            onClick={openCreateSkill}
                          >
                            <Plus size={14} />
                            {t("skillPackages.createSkill")}
                          </button>
                        </>
                      ) : null}
                    </div>
                  </div>
                  <div className={skillStyles.skillsListArea}>
                    {skillsContent}
                  </div>
                </div>
              </>
            )}
          </section>
        ) : null}
      </div>

      <Modal
        title={t(
          editingPackage
            ? "skillPackages.editPackage"
            : "skillPackages.createPackage",
        )}
        open={packageModalOpen}
        onCancel={() => setPackageModalOpen(false)}
        onOk={() => void savePackage()}
        okText={t(editingPackage ? "common.save" : "common.create")}
        cancelText={t("common.cancel")}
      >
        {!editingPackage ? (
          <Typography.Paragraph type="secondary" style={{ marginTop: 0 }}>
            {t("skillPackages.createPackageHint")}
          </Typography.Paragraph>
        ) : null}
        <Form form={packageForm} layout="vertical">
          <Form.Item
            name="name"
            label={t("skillPackages.packageName")}
            rules={[
              {
                required: true,
                whitespace: true,
                message: t("skillPackages.packageNameRequired"),
              },
            ]}
          >
            <Input
              autoFocus
              placeholder={t("skillPackages.packageNamePlaceholder")}
            />
          </Form.Item>
          <Form.Item
            name="description"
            label={t("skillPackages.packageDescription")}
          >
            <Input.TextArea
              autoSize={{ minRows: 3, maxRows: 6 }}
              placeholder={t("skillPackages.packageDescriptionPlaceholder")}
            />
          </Form.Item>
          <Form.Item name="icon_name" label={t("skillPackages.iconName")}>
            <Select
              allowClear
              showSearch
              placeholder={t("skillPackages.iconNamePlaceholder")}
              filterOption={(input, option) => {
                const name = String(option?.value ?? "");
                const label = t(`experts.iconLabels.${name}`, {
                  defaultValue: name,
                });
                const q = input.trim().toLowerCase();
                return (
                  name.toLowerCase().includes(q) ||
                  label.toLowerCase().includes(q)
                );
              }}
              options={EXPERT_ICON_NAMES.map((name) => ({
                value: name,
                label: (
                  <span className={styles.iconOption}>
                    {iconForName(name, 18)}
                    <span>
                      {t(`experts.iconLabels.${name}`, { defaultValue: name })}
                    </span>
                  </span>
                ),
              }))}
            />
          </Form.Item>
          <Form.Item name="icon_url" label={t("skillPackages.iconUrl")}>
            <Input
              type="url"
              placeholder={t("skillPackages.iconUrlPlaceholder")}
              suffix={
                <span className={styles.iconPreview}>
                  <PackageIcon
                    iconUrl={iconUrl}
                    iconName={iconName}
                    size={18}
                    className={styles.iconPreviewImage}
                  />
                </span>
              }
            />
          </Form.Item>
        </Form>
      </Modal>

      <SkillImportModal
        open={importModalOpen}
        importing={importing}
        onClose={() => setImportModalOpen(false)}
        onImportUrl={confirmImport}
        onImportZip={confirmImportZip}
        urlPrefixes={SKILL_URL_PREFIXES}
      />

      <SkillsetFromHubDrawer
        open={skillsetHubOpen}
        onClose={() => setSkillsetHubOpen(false)}
        onCreated={async (pkg) => {
          await loadPackages({ silent: true });
          setSelected(pkg);
          setSelectedId(pkg.id);
          if (isMobile) setMobilePane("detail");
          setSkillsetHubOpen(false);
          message.success(t("skillPackages.created"));
        }}
      />

      <SkillDrawer
        open={drawerOpen}
        editingSkill={
          editingSkill
            ? {
                slug: editingSkill.slug,
                name: editingSkill.name,
                description: editingSkill.description,
                enabled: true,
                kind: "workspace",
                frontmatter: editingSkill.frontmatter,
                body: editingSkill.body,
                raw: editingSkill.raw,
              }
            : null
        }
        form={skillForm}
        onClose={() => setDrawerOpen(false)}
        onSubmit={(values) => void saveSkill(values)}
      />

      <Drawer
        title={t("skills.tencentSkillHub")}
        open={hubOpen}
        onClose={() => setHubOpen(false)}
        width={860}
        destroyOnClose
      >
        {selected ? (
          <SkillHubTab
            target={{ type: "package", packageId: selected.id }}
            onInstalled={() => void refreshSelected()}
          />
        ) : null}
      </Drawer>
    </PageShell>
  );
}
