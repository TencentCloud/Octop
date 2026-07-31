/**
 * SubagentManager — reusable subagent management content.
 * Used inside SubagentCatalogDrawer (Drawer) and Subagents page.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { Alert, Empty, Input, Modal, Spin, Tabs } from "antd";
import { message } from "@/utils/antdMessage";

import { CircleCheck, Download, RefreshCw, Search } from "lucide-react";
import { Eye, Pencil, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  installSubagent,
  listAgentSubagents,
  listSubagentCatalog,
  listSubagentDivisions,
  type AgentSubagentSummary,
  type SubagentCatalogDivision,
  type SubagentCatalogItem,
} from "../../../api/modules/subagents";
import { workspaceApi } from "../../../api/modules/workspace";
import { apiErrorMessage } from "../../../utils/apiError";
import { isAgentChatReady } from "../../../utils/agentError";
import { normalizeUiLocale } from "../../../utils/locale";
import { pickLocale } from "../../../utils/localizedText";
import type { LocalizedText } from "../../../utils/localizedText";
import FileEditModal from "./FileEditModal";
import SubagentPreviewDrawer from "./SubagentPreviewDrawer";
import styles from "../index.module.less";

const INSTALLED_TAB = "installed";
const ALL_TAB = "all";

function subagentFilePath(path: string): string {
  return path.startsWith("/") ? path : `/${path}`;
}

export interface SubagentManagerProps {
  agentId: string;
  agentState?: string;
  /** Optional set of initially known installed slugs (used by Drawer). */
  installedSlugs?: Set<string>;
  /** Callback after install/uninstall. */
  onInstalled?: () => void;
  /** Fill parent height with internal scroll (mobile subagents page). */
  fillHeight?: boolean;
}

export default function SubagentManager({
  agentId,
  agentState = "stopped",
  installedSlugs: initialInstalled,
  onInstalled,
  fillHeight = false,
}: SubagentManagerProps) {
  const { t, i18n } = useTranslation();
  const lang = normalizeUiLocale(i18n.language);
  const [divisions, setDivisions] = useState<SubagentCatalogDivision[]>([]);
  const [allItems, setAllItems] = useState<SubagentCatalogItem[]>([]);
  const [installedSubagents, setInstalledSubagents] = useState<
    AgentSubagentSummary[]
  >([]);
  const [loading, setLoading] = useState(false);
  const [loadingInstalled, setLoadingInstalled] = useState(false);
  const [activeTab, setActiveTab] = useState(INSTALLED_TAB);
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [installingSlug, setInstallingSlug] = useState<string | null>(null);
  const [installedSlugs, setInstalledSlugs] = useState<Set<string>>(
    () => new Set(initialInstalled ?? []),
  );
  const [fileModalOpen, setFileModalOpen] = useState(false);
  const [editingFile, setEditingFile] = useState<string | null>(null);
  const [previewItem, setPreviewItem] = useState<SubagentCatalogItem | null>(
    null,
  );

  const agentReady = isAgentChatReady(agentState);

  const installedKey = useMemo(
    () => [...(initialInstalled ?? [])].sort().join("\0"),
    [initialInstalled],
  );

  useEffect(() => {
    if (initialInstalled) setInstalledSlugs(new Set(initialInstalled));
  }, [installedKey, initialInstalled]);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search.trim()), 250);
    return () => clearTimeout(timer);
  }, [search]);

  const loadInstalled = useCallback(async () => {
    if (!agentReady) {
      setInstalledSubagents([]);
      setInstalledSlugs(new Set());
      return;
    }
    setLoadingInstalled(true);
    try {
      const rows = await listAgentSubagents(agentId);
      setInstalledSubagents(rows);
      setInstalledSlugs(new Set(rows.map((r) => r.slug)));
    } catch (err) {
      message.error(apiErrorMessage(err, t("subagents.loadFailed")));
      setInstalledSubagents([]);
    } finally {
      setLoadingInstalled(false);
    }
  }, [agentId, agentReady, t]);

  const loadCatalog = useCallback(async () => {
    setLoading(true);
    try {
      const [divs, rows] = await Promise.all([
        listSubagentDivisions(),
        listSubagentCatalog(),
      ]);
      setDivisions(divs);
      setAllItems(rows);
    } catch (err) {
      message.error(apiErrorMessage(err, t("subagents.loadFailed")));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    setActiveTab(INSTALLED_TAB);
    setSearch("");
    setDebouncedSearch("");
    void loadCatalog();
    void loadInstalled();
  }, [agentId, loadCatalog, loadInstalled]);

  const itemName = useCallback(
    (item: SubagentCatalogItem) => pickLocale(item.name, lang),
    [lang],
  );
  const itemDescription = useCallback(
    (item: SubagentCatalogItem) => pickLocale(item.description, lang),
    [lang],
  );

  const divisionLabel = useCallback(
    (id: string, fallback?: string, labels?: LocalizedText) =>
      pickLocale(labels, lang) ||
      t(`subagents.divisions.${id}`, { defaultValue: fallback ?? id }),
    [lang, t],
  );

  const filteredCatalogItems = useMemo(() => {
    const q = debouncedSearch.toLowerCase();
    let rows = allItems;
    if (q) {
      rows = rows.filter((item) => {
        const name = itemName(item);
        const desc = itemDescription(item);
        return (
          name.toLowerCase().includes(q) ||
          desc.toLowerCase().includes(q) ||
          item.slug.toLowerCase().includes(q) ||
          divisionLabel(item.division).toLowerCase().includes(q)
        );
      });
    } else if (activeTab !== ALL_TAB && activeTab !== INSTALLED_TAB) {
      rows = rows.filter((item) => item.division === activeTab);
    }
    return rows.slice().sort((a, b) => itemName(a).localeCompare(itemName(b)));
  }, [
    allItems,
    activeTab,
    debouncedSearch,
    divisionLabel,
    itemName,
    itemDescription,
  ]);

  const filteredInstalled = useMemo(() => {
    const q = debouncedSearch.toLowerCase();
    let rows = installedSubagents;
    if (q) {
      rows = rows.filter(
        (item) =>
          item.name.toLowerCase().includes(q) ||
          (item.description ?? "").toLowerCase().includes(q) ||
          item.slug.toLowerCase().includes(q),
      );
    }
    return rows.slice().sort((a, b) => a.name.localeCompare(b.name));
  }, [installedSubagents, debouncedSearch]);

  const tabItems = useMemo(
    () => [
      {
        key: INSTALLED_TAB,
        label: t("subagents.installedTab"),
      },
      {
        key: ALL_TAB,
        label: t("subagents.allDivisions"),
      },
      ...divisions.map((d) => ({
        key: d.id,
        label: `${divisionLabel(d.id, d.label, d.labels)} (${d.count})`,
      })),
    ],
    [divisions, divisionLabel, t],
  );

  const syncAfterChange = useCallback(async () => {
    await loadInstalled();
    onInstalled?.();
  }, [loadInstalled, onInstalled]);

  const handleInstall = async (item: SubagentCatalogItem) => {
    if (!agentReady) {
      message.warning(t("subagents.agentNotReady"));
      return;
    }
    setInstallingSlug(item.slug);
    try {
      await installSubagent(agentId, item.slug);
      await syncAfterChange();
      message.success(t("subagents.installSuccess", { name: itemName(item) }));
    } catch (err) {
      message.error(apiErrorMessage(err, t("subagents.installFailed")));
    } finally {
      setInstallingSlug(null);
    }
  };

  const openFileEditor = (path: string) => {
    setEditingFile(subagentFilePath(path));
    setFileModalOpen(true);
  };

  const confirmDeleteSubagent = (subagent: AgentSubagentSummary) => {
    Modal.confirm({
      title: t("workspace.deleteConfirm"),
      okText: t("common.delete"),
      cancelText: t("common.cancel"),
      okButtonProps: { danger: true },
      onOk: async () => {
        await workspaceApi.deleteWorkspaceFile(
          agentId,
          subagentFilePath(subagent.path),
        );
        message.success(t("workspace.deleteSuccess"));
        await syncAfterChange();
      },
    });
  };

  const renderCatalogGrid = () => {
    if (loading) {
      return (
        <div className={styles.catalogLoading}>
          <Spin />
        </div>
      );
    }
    if (filteredCatalogItems.length === 0) {
      return <Empty description={t("subagents.noResults")} />;
    }
    return (
      <div className={styles.catalogGrid}>
        {filteredCatalogItems.map((item) => {
          const installed = installedSlugs.has(item.slug);
          const accent = item.color?.startsWith("#") ? item.color : "#6366f1";
          return (
            <div key={item.slug} className={styles.catalogCard}>
              <div className={styles.catalogCardHeader}>
                <div
                  className={styles.catalogCardIcon}
                  style={{ color: accent, background: `${accent}1a` }}
                >
                  {item.emoji ?? "🤖"}
                </div>
                <div className={styles.catalogCardTitle}>{itemName(item)}</div>
                <span
                  className={styles.catalogCardInstalledSlot}
                  title={installed ? t("subagents.installed") : undefined}
                >
                  {installed ? (
                    <CircleCheck
                      size={16}
                      className={styles.catalogCardInstalled}
                    />
                  ) : null}
                </span>
              </div>
              <p className={styles.catalogCardDesc}>
                {itemDescription(item) || t("subagents.noDescription")}
              </p>
              <div className={styles.catalogCardFooter}>
                <span className={styles.catalogCardSlug}>{item.slug}</span>
                <div className={styles.catalogCardActions}>
                  <button
                    type="button"
                    className={styles.catalogCardActionBtn}
                    onClick={() => setPreviewItem(item)}
                  >
                    <Eye size={13} />
                    {t("common.view")}
                  </button>
                  <button
                    type="button"
                    className={`${styles.catalogCardActionBtn} ${
                      installed ? "" : styles.catalogCardActionBtnPrimary
                    }`}
                    disabled={!agentReady || installingSlug === item.slug}
                    onClick={() => void handleInstall(item)}
                  >
                    {installingSlug === item.slug ? (
                      t("subagents.installing")
                    ) : (
                      <>
                        {installed ? (
                          <RefreshCw size={13} />
                        ) : (
                          <Download size={13} />
                        )}
                        {installed
                          ? t("subagents.reinstall")
                          : t("subagents.install")}
                      </>
                    )}
                  </button>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    );
  };

  const renderInstalledGrid = () => {
    if (!agentReady) {
      return <Empty description={t("subagents.agentNotReady")} />;
    }
    if (loadingInstalled) {
      return (
        <div className={styles.catalogLoading}>
          <Spin />
        </div>
      );
    }
    if (filteredInstalled.length === 0) {
      return <Empty description={t("subagents.noInstalled")} />;
    }
    return (
      <div className={styles.catalogGrid}>
        {filteredInstalled.map((subagent) => {
          const accent = "#6366f1";
          return (
            <div key={subagent.slug} className={styles.catalogCard}>
              <div className={styles.catalogCardHeader}>
                <div
                  className={styles.catalogCardIcon}
                  style={{ color: accent, background: `${accent}1a` }}
                >
                  {subagent.emoji ?? "🤖"}
                </div>
                <div className={styles.catalogCardTitle}>{subagent.name}</div>
                <span
                  className={styles.catalogCardInstalledSlot}
                  title={t("subagents.installed")}
                >
                  <CircleCheck
                    size={16}
                    className={styles.catalogCardInstalled}
                  />
                </span>
              </div>
              <p className={styles.catalogCardDesc}>
                {subagent.description || t("subagents.noDescription")}
              </p>
              <div className={styles.catalogCardFooter}>
                <span className={styles.catalogCardSlug}>{subagent.slug}</span>
                <div className={styles.catalogCardActions}>
                  <button
                    type="button"
                    className={styles.catalogCardActionBtn}
                    onClick={() => openFileEditor(subagent.path)}
                  >
                    <Pencil size={13} />
                    {t("common.edit")}
                  </button>
                  <button
                    type="button"
                    className={`${styles.catalogCardActionBtn} ${styles.catalogCardActionBtnIcon} ${styles.catalogCardActionBtnDanger}`}
                    onClick={() => confirmDeleteSubagent(subagent)}
                    aria-label={t("common.delete")}
                    title={t("common.delete")}
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    );
  };

  return (
    <>
      <div
        className={`${styles.catalogDrawer} ${
          fillHeight ? styles.catalogDrawerMobile : ""
        }`}
      >
        {!agentReady && activeTab !== INSTALLED_TAB && (
          <Alert
            type="warning"
            showIcon
            message={t("subagents.agentNotReady")}
            style={{ marginBottom: 12 }}
          />
        )}

        <Input
          allowClear
          prefix={<Search size={14} />}
          placeholder={t("subagents.searchPlaceholder")}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className={styles.catalogSearch}
        />

        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={tabItems}
          className={styles.catalogTabs}
        />

        {activeTab === INSTALLED_TAB
          ? renderInstalledGrid()
          : renderCatalogGrid()}
      </div>

      <FileEditModal
        open={fileModalOpen}
        agentId={agentId}
        filePath={editingFile}
        onClose={() => {
          setFileModalOpen(false);
          setEditingFile(null);
        }}
        onSaved={() => {
          void syncAfterChange();
        }}
      />

      <SubagentPreviewDrawer
        open={previewItem !== null}
        slug={previewItem?.slug ?? null}
        title={previewItem ? itemName(previewItem) : ""}
        onClose={() => setPreviewItem(null)}
      />
    </>
  );
}
