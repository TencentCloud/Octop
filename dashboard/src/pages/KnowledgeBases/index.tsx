import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type CSSProperties,
} from "react";
import {
  Alert,
  Button,
  Empty,
  Form,
  Input,
  List,
  Modal,
  Popconfirm,
  Radio,
  Segmented,
  Select,
  Spin,
  Switch,
  Table,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import { message } from "@/utils/antdMessage";
import {
  ChevronLeft,
  Eye,
  FileUp,
  LayoutGrid,
  List as ListIcon,
  PanelLeftClose,
  PanelLeftOpen,
  Pencil,
  Plus,
  RefreshCw,
  Settings,
  Trash2,
  CircleHelp,
} from "lucide-react";
import { useTranslation } from "react-i18next";

import { useCurrentUser } from "../../hooks/useCurrentUser";
import { userCan } from "../../utils/permissions";
import {
  DEFAULT_KNOWLEDGE_LIMITS,
  knowledgeBasesApi,
  type KnowledgeBase,
  type KnowledgeCapability,
  type KnowledgeDocument,
} from "../../api/modules/knowledgeBases";
import { OctopEmptyMascot } from "../../components/EmptyState";
import { CopyableResourceId } from "../../components/CopyableResourceId";
import { useCardTableView } from "../../hooks/useCardTableView";
import { useHorizontalResize } from "../../hooks/useHorizontalResize";
import { useIsMobile } from "../../hooks/useIsMobile";
import { useListPanelCollapsed } from "../../hooks/useListPanelCollapsed";
import { useServerTimezone } from "../../hooks/useServerTimezone";
import PageShell from "../../layouts/PageShell";
import { apiErrorMessage, isNotFoundApiError } from "../../utils/apiError";
import { createDetailRequestGate } from "../../utils/detailRequestGate";
import { formatBytes } from "../../utils/embeddingDownload";
import { fileTreeIconSpec } from "../../utils/fileTreeIcon";
import { formatServerDateTime } from "../../utils/formatMessageTime";
import skillStyles from "../Agent/Skills/index.module.less";
import { KNOWLEDGE_ICON_NAMES, knowledgeIconForName } from "./knowledgeIcons";
import styles from "./index.module.less";

type BaseFormValues = {
  name: string;
  description?: string;
  default_open?: boolean;
  shared?: boolean;
  icon_name?: string;
};

type DocsViewMode = "card" | "table";
const DOCS_VIEW_STORAGE_KEY = "octop:knowledge-bases-docs-view";

const SUPPORTED_DOCUMENT_TYPES = ".md,.txt,.pdf,.docx,.pptx";

function loadDocsViewMode(): DocsViewMode {
  const stored = localStorage.getItem(DOCS_VIEW_STORAGE_KEY);
  return stored === "table" ? "table" : "card";
}

function documentStatusColor(status: KnowledgeDocument["status"]) {
  if (status === "ready") return "success";
  if (status === "failed") return "error";
  if (status === "processing") return "processing";
  return "default";
}

function fileExtensionLabel(filename: string): string {
  const ext = filename.includes(".")
    ? filename.slice(filename.lastIndexOf(".") + 1)
    : "";
  return ext.trim().toUpperCase().slice(0, 5);
}

function formatKnowledgeOwner(
  base: Pick<
    KnowledgeBase,
    "owner_display_name" | "owner_username" | "owner_user_id"
  >,
): string {
  const displayName = base.owner_display_name?.trim() || "";
  const username = base.owner_username?.trim() || "";
  return displayName || username || String(base.owner_user_id);
}

function DocumentFormatIcon({
  filename,
  size = 14,
  className,
}: {
  filename: string;
  size?: number;
  className?: string;
}) {
  const { Icon, color } = fileTreeIconSpec(filename);
  return (
    <span
      className={className ?? styles.docFormatIcon}
      style={{ color, background: `${color}14` }}
      aria-hidden
    >
      <Icon size={size} strokeWidth={2} />
    </span>
  );
}

function KnowledgeIconPicker({
  value,
  onChange,
}: {
  value?: string;
  onChange?: (value?: string) => void;
}) {
  const { t } = useTranslation();
  return (
    <div className={styles.iconPicker}>
      {KNOWLEDGE_ICON_NAMES.map((name) => {
        const selected = value === name;
        return (
          <button
            key={name}
            type="button"
            className={`${styles.iconPickerItem}${
              selected ? ` ${styles.iconPickerItemActive}` : ""
            }`}
            onClick={() => onChange?.(selected ? undefined : name)}
            title={t(`knowledgeBases.iconLabels.${name}`)}
          >
            <span className={styles.iconPickerGlyph}>
              {knowledgeIconForName(name, 18)}
            </span>
            <span className={styles.iconPickerLabel}>
              {t(`knowledgeBases.iconLabels.${name}`)}
            </span>
          </button>
        );
      })}
    </div>
  );
}

export default function KnowledgeBasesPage() {
  const { t } = useTranslation();
  const isMobile = useIsMobile();
  const timeZone = useServerTimezone();
  const user = useCurrentUser();
  const canConfigureKb = userCan(user, "knowledge_bases");
  const { viewMode, setViewMode, showCardView } = useCardTableView(
    loadDocsViewMode(),
  );
  const [bases, setBases] = useState<KnowledgeBase[]>([]);
  const [selected, setSelected] = useState<KnowledgeBase | null>(null);
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [capability, setCapability] = useState<KnowledgeCapability | null>(
    null,
  );
  const [catalog, setCatalog] = useState<
    { id: string; name: string; downloaded: boolean }[]
  >([]);
  const [remoteProviders, setRemoteProviders] = useState<
    {
      provider_id: string;
      provider_name: string;
      models: { id: string; name: string }[];
    }[]
  >([]);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [mobilePane, setMobilePane] = useState<"list" | "detail">("list");
  const [baseModalOpen, setBaseModalOpen] = useState(false);
  const [editingBase, setEditingBase] = useState(false);
  const [featureModalOpen, setFeatureModalOpen] = useState(false);
  const [featureEnabledDraft, setFeatureEnabledDraft] = useState(false);
  const [featureModel, setFeatureModel] = useState<string>();
  const [featureBackend, setFeatureBackend] = useState<"onnx" | "remote">(
    "onnx",
  );
  const [featureProviderId, setFeatureProviderId] = useState<string>();
  const [featureOptionsLoading, setFeatureOptionsLoading] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewFilename, setPreviewFilename] = useState("");
  const [previewText, setPreviewText] = useState("");
  const [baseForm] = Form.useForm<BaseFormValues>();
  const uploadRef = useRef<HTMLInputElement>(null);
  const detailRequestGate = useRef(createDetailRequestGate());
  const {
    size: sidebarWidth,
    isResizing,
    onResizeStart,
  } = useHorizontalResize({
    min: 220,
    max: 480,
    defaultSize: 280,
    storageKey: "octop:knowledge-bases:sidebar-width",
  });
  const { collapsed: listPanelCollapsed, toggle: toggleListPanel } =
    useListPanelCollapsed("octop:knowledge-bases:list-collapsed");

  const canManageSelected = Boolean(
    selected &&
      user &&
      (user.role === "admin" || selected.owner_user_id === user.id),
  );
  const canWriteSelected = canManageSelected;
  const usable = Boolean(capability?.usable);
  const limits = capability?.limits ?? DEFAULT_KNOWLEDGE_LIMITS;
  const ownedBaseCount = user
    ? bases.filter((base) => base.owner_user_id === user.id).length
    : 0;
  const atBaseLimit = ownedBaseCount >= limits.max_bases_per_owner;
  const isAtDocumentLimit = documents.length >= limits.max_docs_per_kb;

  const loadBases = useCallback(async () => {
    try {
      const rows = await knowledgeBasesApi.list();
      setBases(rows);
      setSelected((current) =>
        current && !rows.some((row) => row.id === current.id) ? null : current,
      );
    } catch (error) {
      message.error(apiErrorMessage(error, t("knowledgeBases.loadFailed"), t));
    }
  }, [t]);

  const loadCapability = useCallback(async () => {
    try {
      const nextCapability = await knowledgeBasesApi.getCapability();
      setCapability(nextCapability);
      setFeatureModel(nextCapability.selected_model || undefined);
      setFeatureBackend(nextCapability.backend);
      setFeatureProviderId(nextCapability.provider_id || undefined);
      setFeatureEnabledDraft(Boolean(nextCapability.feature_enabled));
    } catch (error) {
      message.error(apiErrorMessage(error, t("knowledgeBases.loadFailed"), t));
    }
  }, [t]);

  const loadEmbeddingOptions = useCallback(async () => {
    setFeatureOptionsLoading(true);
    try {
      const options = await knowledgeBasesApi.getEmbeddingOptions();
      setCatalog(options.onnx);
      setRemoteProviders(options.remote);
    } catch (error) {
      message.error(apiErrorMessage(error, t("knowledgeBases.loadFailed"), t));
    } finally {
      setFeatureOptionsLoading(false);
    }
  }, [t]);

  const loadDetail = useCallback(
    async (id: string, options?: { silent?: boolean }) => {
      const requestId = detailRequestGate.current.begin();
      if (!options?.silent) setDetailLoading(true);
      try {
        const [base, nextDocuments] = await Promise.all([
          knowledgeBasesApi.get(id),
          knowledgeBasesApi.listDocuments(id),
        ]);
        if (!detailRequestGate.current.isCurrent(requestId)) return;
        setSelected(base);
        setDocuments(nextDocuments);
      } catch (error) {
        if (!detailRequestGate.current.isCurrent(requestId)) return;
        if (isNotFoundApiError(error)) {
          setSelected(null);
          setDocuments([]);
          return;
        }
        if (!options?.silent) {
          message.error(
            apiErrorMessage(error, t("knowledgeBases.loadFailed"), t),
          );
        }
      } finally {
        if (
          !options?.silent &&
          detailRequestGate.current.isCurrent(requestId)
        ) {
          setDetailLoading(false);
        }
      }
    },
    [t],
  );

  useEffect(() => {
    void Promise.all([loadBases(), loadCapability()]).finally(() =>
      setLoading(false),
    );
  }, [loadBases, loadCapability]);

  useEffect(() => {
    const indexing = documents.some(
      (document) =>
        document.status === "pending" || document.status === "processing",
    );
    if (!selected || !indexing) return;
    const timer = window.setInterval(() => {
      void loadDetail(selected.id, { silent: true });
    }, 2500);
    return () => window.clearInterval(timer);
  }, [documents, loadDetail, selected]);
  useEffect(() => {
    if (!isMobile && !selected && bases.length > 0 && !detailLoading) {
      void loadDetail(bases[0].id);
    }
  }, [bases, detailLoading, isMobile, loadDetail, selected]);

  useEffect(() => {
    if (!isMobile) setMobilePane("list");
  }, [isMobile]);

  const refresh = async () => {
    setRefreshing(true);
    try {
      await Promise.all([
        loadBases(),
        loadCapability(),
        selected ? loadDetail(selected.id) : Promise.resolve(),
      ]);
    } finally {
      setRefreshing(false);
    }
  };

  const selectBase = (base: KnowledgeBase) => {
    if (base.id !== selected?.id) void loadDetail(base.id);
    if (isMobile) setMobilePane("detail");
  };

  const openCreate = () => {
    if (atBaseLimit) {
      message.warning(
        t("knowledgeBases.baseLimitReached", {
          count: limits.max_bases_per_owner,
        }),
      );
      return;
    }
    baseForm.setFieldsValue({
      name: "",
      description: "",
      default_open: false,
      shared: false,
      icon_name: "book-open",
    });
    setEditingBase(false);
    setBaseModalOpen(true);
  };

  const openEdit = () => {
    if (!selected) return;
    baseForm.setFieldsValue({
      name: selected.name,
      description: selected.description,
      default_open: selected.default_open,
      shared: selected.shared,
      icon_name: selected.icon_name || undefined,
    });
    setEditingBase(true);
    setBaseModalOpen(true);
  };

  const saveBase = async () => {
    const values = await baseForm.validateFields();
    try {
      const next =
        editingBase && selected
          ? await knowledgeBasesApi.update(selected.id, values)
          : await knowledgeBasesApi.create(values);
      setBaseModalOpen(false);
      await loadBases();
      await loadDetail(next.id);
      if (isMobile) setMobilePane("detail");
      message.success(
        t(editingBase ? "knowledgeBases.updated" : "knowledgeBases.created"),
      );
    } catch (error) {
      message.error(apiErrorMessage(error, t("knowledgeBases.saveFailed"), t));
    }
  };

  const deleteBase = async () => {
    if (!selected) return;
    const deletedId = selected.id;
    detailRequestGate.current.begin();
    setSelected(null);
    setDocuments([]);
    setDetailLoading(false);
    try {
      await knowledgeBasesApi.delete(deletedId);
      const rows = await knowledgeBasesApi.list();
      setBases(rows);
      if (isMobile) {
        setMobilePane("list");
      } else if (rows.length > 0) {
        await loadDetail(rows[0].id);
      }
      message.success(t("knowledgeBases.deleted"));
    } catch (error) {
      message.error(
        apiErrorMessage(error, t("knowledgeBases.deleteFailed"), t),
      );
    }
  };

  const saveFeature = async (confirmed = false) => {
    if (!featureEnabledDraft) {
      try {
        setCapability(await knowledgeBasesApi.setFeature({ enabled: false }));
        setFeatureModalOpen(false);
        message.success(t("knowledgeBases.featureDisabled"));
      } catch (error) {
        message.error(
          apiErrorMessage(error, t("knowledgeBases.featureSaveFailed"), t),
        );
      }
      return;
    }
    if (!featureModel || (featureBackend === "remote" && !featureProviderId)) {
      return;
    }
    if (
      !confirmed &&
      capability?.feature_enabled &&
      (capability.backend !== featureBackend ||
        capability.selected_model !== featureModel ||
        capability.provider_id !==
          (featureBackend === "remote" ? featureProviderId : ""))
    ) {
      Modal.confirm({
        title: t("knowledgeBases.rebuildConfirmTitle"),
        content: t("knowledgeBases.rebuildConfirmDescription"),
        onOk: () => void saveFeature(true),
      });
      return;
    }
    try {
      const next = await knowledgeBasesApi.setFeature({
        enabled: true,
        backend: featureBackend,
        model: featureModel,
        provider_id: featureBackend === "remote" ? featureProviderId : "",
      });
      setCapability(next);
      setFeatureModalOpen(false);
      message.success(t("knowledgeBases.featureEnabled"));
    } catch (error) {
      message.error(
        apiErrorMessage(error, t("knowledgeBases.featureSaveFailed"), t),
      );
    }
  };

  const openSettings = () => {
    setFeatureEnabledDraft(Boolean(capability?.feature_enabled));
    setFeatureBackend(capability?.backend ?? "onnx");
    setFeatureModel(capability?.selected_model || undefined);
    setFeatureProviderId(capability?.provider_id || undefined);
    setFeatureModalOpen(true);
    void loadEmbeddingOptions();
  };

  const uploadDocuments = async (files: FileList | null) => {
    if (!selected || !files || !usable || isAtDocumentLimit) return;
    const remaining = Math.max(0, limits.max_docs_per_kb - documents.length);
    const chosen = Array.from(files).slice(0, remaining);
    const oversized = chosen.filter(
      (file) => file.size > limits.max_document_bytes,
    );
    if (oversized.length > 0) {
      message.error(
        t("knowledgeBases.documentTooLarge", {
          sizeMb: Math.round(limits.max_document_bytes / (1024 * 1024)),
        }),
      );
      if (uploadRef.current) uploadRef.current.value = "";
      return;
    }
    try {
      for (const file of chosen) {
        await knowledgeBasesApi.uploadDocument(selected.id, file);
      }
      await loadDetail(selected.id);
      await loadBases();
      message.success(t("knowledgeBases.uploaded"));
    } catch (error) {
      message.error(
        apiErrorMessage(error, t("knowledgeBases.uploadFailed"), t),
      );
    } finally {
      if (uploadRef.current) uploadRef.current.value = "";
    }
  };

  const deleteDocument = async (documentId: string) => {
    if (!selected) return;
    try {
      await knowledgeBasesApi.deleteDocument(selected.id, documentId);
      await loadDetail(selected.id);
      await loadBases();
    } catch (error) {
      message.error(
        apiErrorMessage(error, t("knowledgeBases.deleteFailed"), t),
      );
    }
  };

  const rebuildDocument = async (documentId: string) => {
    if (!selected) return;
    try {
      await knowledgeBasesApi.reindexDocument(selected.id, documentId);
      message.success(t("knowledgeBases.rebuildDocumentSuccess"));
      await loadDetail(selected.id);
    } catch (error) {
      message.error(
        apiErrorMessage(error, t("knowledgeBases.rebuildDocumentFailed"), t),
      );
    }
  };

  const openDocumentPreview = async (documentId: string) => {
    if (!selected) return;
    setPreviewOpen(true);
    setPreviewLoading(true);
    setPreviewFilename("");
    setPreviewText("");
    try {
      const preview = await knowledgeBasesApi.previewDocument(
        selected.id,
        documentId,
      );
      setPreviewFilename(preview.filename);
      setPreviewText(
        preview.text.trim() ? preview.text : t("knowledgeBases.previewEmpty"),
      );
    } catch (error) {
      setPreviewOpen(false);
      message.error(
        apiErrorMessage(error, t("knowledgeBases.previewFailed"), t),
      );
    } finally {
      setPreviewLoading(false);
    }
  };

  const renderDocumentActions = (document: KnowledgeDocument) => (
    <div className={styles.docCardActions}>
      <Tooltip title={t("knowledgeBases.previewDocument")}>
        <Button
          type="text"
          size="small"
          icon={<Eye size={14} />}
          aria-label={t("knowledgeBases.previewDocument")}
          onClick={() => void openDocumentPreview(document.id)}
        />
      </Tooltip>
      {canWriteSelected ? (
        <>
          <Popconfirm
            title={t("knowledgeBases.rebuildDocumentConfirm")}
            onConfirm={() => void rebuildDocument(document.id)}
          >
            <Tooltip title={t("knowledgeBases.rebuildDocument")}>
              <Button
                type="text"
                size="small"
                icon={<RefreshCw size={14} />}
                aria-label={t("knowledgeBases.rebuildDocument")}
              />
            </Tooltip>
          </Popconfirm>
          <Popconfirm
            title={t("knowledgeBases.deleteDocumentConfirm")}
            onConfirm={() => void deleteDocument(document.id)}
          >
            <Button
              type="text"
              danger
              size="small"
              icon={<Trash2 size={14} />}
              aria-label={t("common.delete")}
            />
          </Popconfirm>
        </>
      ) : null}
    </div>
  );

  const showListPane = !isMobile || mobilePane === "list";
  const showDetailPane = !isMobile || mobilePane === "detail";
  const showListPanel = showListPane && (isMobile || !listPanelCollapsed);

  const onDocsViewChange = (value: string | number) => {
    const mode = value === "table" ? "table" : "card";
    setViewMode(mode);
    localStorage.setItem(DOCS_VIEW_STORAGE_KEY, mode);
  };

  return (
    <PageShell
      title={t("knowledgeBases.title")}
      subtitle={t("knowledgeBases.subtitle")}
      fill
      actions={
        canConfigureKb ? (
          <Button icon={<Settings size={15} />} onClick={openSettings}>
            {t("knowledgeBases.settingsTitle")}
          </Button>
        ) : undefined
      }
    >
      <div
        className={`${styles.layout}${
          isResizing ? ` ${styles.layoutResizing}` : ""
        }${isMobile ? ` ${styles.layoutMobile}` : ""}`}
        style={
          {
            "--knowledge-bases-sidebar-width": `${sidebarWidth}px`,
          } as CSSProperties
        }
      >
        {showListPanel ? (
          <aside className={styles.baseList}>
            <div className={styles.listPanelHeader}>
              <span className={styles.listPanelTitle}>
                {t("knowledgeBases.title")}
              </span>
              {!isMobile ? (
                <Tooltip title={t("knowledgeBases.collapseListPanel")}>
                  <button
                    type="button"
                    className={styles.listPanelToggle}
                    onClick={toggleListPanel}
                    aria-label={t("knowledgeBases.collapseListPanel")}
                  >
                    <PanelLeftClose size={15} strokeWidth={1.8} />
                  </button>
                </Tooltip>
              ) : null}
            </div>
            <div className={styles.listActions}>
              <Button
                type="primary"
                icon={<Plus size={15} />}
                disabled={!usable || atBaseLimit}
                onClick={openCreate}
              >
                {t("knowledgeBases.create")}
              </Button>
              <Tooltip title={t("common.refresh")}>
                <Button
                  icon={<RefreshCw size={15} />}
                  loading={refreshing}
                  onClick={() => void refresh()}
                />
              </Tooltip>
            </div>
            {loading ? (
              <div className={styles.centered}>
                <Spin />
              </div>
            ) : (
              <List
                className={styles.list}
                split={false}
                dataSource={bases}
                locale={{
                  emptyText: (
                    <Empty
                      image={Empty.PRESENTED_IMAGE_SIMPLE}
                      description={t("knowledgeBases.empty")}
                    />
                  ),
                }}
                renderItem={(base) => (
                  <List.Item
                    className={styles.listRow}
                    onClick={() => selectBase(base)}
                  >
                    <div
                      className={`${styles.listItem} ${
                        base.id === selected?.id ? styles.active : ""
                      }`}
                    >
                      <div className={styles.listName}>
                        <span className={styles.listIcon}>
                          {knowledgeIconForName(base.icon_name, 18)}
                        </span>
                        <span>{base.name}</span>
                      </div>
                      <div className={styles.listDescription}>
                        {base.description || t("knowledgeBases.noDescription")}
                      </div>
                      <div className={styles.listMeta}>
                        <Tag className={styles.listCountTag}>
                          {t("knowledgeBases.documentCount", {
                            count: base.doc_count,
                          })}
                        </Tag>
                        {base.default_open || base.shared ? (
                          <div className={styles.listMetaBadges}>
                            {base.default_open ? (
                              <span
                                className={`${styles.listBadge} ${styles.listBadgeDefaultOpen}`}
                              >
                                {t("knowledgeBases.defaultOpenBadge")}
                              </span>
                            ) : null}
                            {base.shared ? (
                              <span
                                className={`${styles.listBadge} ${styles.listBadgeShared}`}
                              >
                                {t("knowledgeBases.sharedBadge")}
                              </span>
                            ) : null}
                          </div>
                        ) : null}
                      </div>
                    </div>
                  </List.Item>
                )}
              />
            )}
          </aside>
        ) : null}
        {!isMobile && !listPanelCollapsed ? (
          <div data-split-divider="" className={styles.splitDivider}>
            <div
              className={styles.resizeHandle}
              role="separator"
              aria-orientation="vertical"
              aria-label={t("knowledgeBases.resizeSidebar")}
              onPointerDown={onResizeStart}
            />
          </div>
        ) : null}
        {showDetailPane ? (
          <section
            className={`${styles.detail}${
              !isMobile && listPanelCollapsed
                ? ` ${styles.detailListCollapsed}`
                : ""
            }`}
          >
            {!isMobile && listPanelCollapsed ? (
              <Tooltip title={t("knowledgeBases.expandListPanel")}>
                <button
                  type="button"
                  className={styles.listPanelExpandBtn}
                  onClick={toggleListPanel}
                  aria-label={t("knowledgeBases.expandListPanel")}
                >
                  <PanelLeftOpen size={16} strokeWidth={1.8} />
                </button>
              </Tooltip>
            ) : null}
            {detailLoading ? (
              <div className={styles.detailLoading}>
                <Spin />
              </div>
            ) : null}
            {!usable ? (
              <div className={styles.disabledOverlay}>
                <Alert
                  showIcon
                  type="warning"
                  message={t("knowledgeBases.unavailableTitle")}
                  description={
                    canConfigureKb ? (
                      <>
                        {t("knowledgeBases.unavailableDescription")}{" "}
                        <Typography.Link onClick={openSettings}>
                          {t("nav.settings")}
                        </Typography.Link>
                      </>
                    ) : (
                      t("knowledgeBases.unavailableDescriptionNonAdmin")
                    )
                  }
                />
              </div>
            ) : null}
            {!selected && !detailLoading ? (
              <div className={styles.emptyDetail}>
                <OctopEmptyMascot size={180} />
                <p className={styles.emptyDetailText}>
                  {t("knowledgeBases.selectBase")}
                </p>
              </div>
            ) : !selected ? null : (
              <>
                <div className={styles.detailHeader}>
                  <div className={styles.titleRow}>
                    <div className={styles.titleGroup}>
                      {isMobile ? (
                        <button
                          type="button"
                          className={styles.mobileBack}
                          onClick={() => setMobilePane("list")}
                          aria-label={t("knowledgeBases.backToList")}
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
                      {canManageSelected ? (
                        <div className={styles.titleActions}>
                          <Tooltip title={t("common.edit")}>
                            <Button
                              type="text"
                              size="small"
                              className={styles.titleActionBtn}
                              icon={<Pencil size={14} />}
                              aria-label={t("common.edit")}
                              onClick={openEdit}
                            />
                          </Tooltip>
                          <Popconfirm
                            title={t("knowledgeBases.deleteConfirm")}
                            okText={t("common.delete")}
                            cancelText={t("common.cancel")}
                            onConfirm={() => void deleteBase()}
                          >
                            <Tooltip title={t("common.delete")}>
                              <Button
                                type="text"
                                size="small"
                                danger
                                className={styles.titleActionBtn}
                                icon={<Trash2 size={14} />}
                                aria-label={t("common.delete")}
                              />
                            </Tooltip>
                          </Popconfirm>
                        </div>
                      ) : null}
                    </div>
                  </div>
                  <Typography.Paragraph
                    type="secondary"
                    className={styles.detailDescription}
                  >
                    {selected.description || t("knowledgeBases.noDescription")}
                  </Typography.Paragraph>
                  <div className={styles.detailMeta}>
                    <CopyableResourceId
                      inline
                      label={t("knowledgeBases.baseId")}
                      value={selected.id}
                      copyTitle={t("knowledgeBases.copyBaseId")}
                    />
                    <Typography.Text
                      type="secondary"
                      className={styles.detailCreator}
                    >
                      {t("knowledgeBases.createdBy", {
                        name: formatKnowledgeOwner(selected),
                      })}
                    </Typography.Text>
                  </div>
                </div>

                <div className={styles.detailBody}>
                  <div
                    className={`${skillStyles.gridToolbar} ${styles.docsToolbar}`}
                  >
                    <span className={skillStyles.gridCount}>
                      {t("knowledgeBases.documentLimit", {
                        count: documents.length,
                        max: limits.max_docs_per_kb,
                      })}
                    </span>
                    <div className={skillStyles.gridToolbarRight}>
                      <Segmented
                        size="small"
                        value={viewMode}
                        onChange={onDocsViewChange}
                        options={[
                          {
                            value: "card",
                            label: (
                              <span className={skillStyles.viewModeLabel}>
                                <LayoutGrid size={14} />
                                {t("knowledgeBases.viewCard")}
                              </span>
                            ),
                          },
                          {
                            value: "table",
                            label: (
                              <span className={skillStyles.viewModeLabel}>
                                <ListIcon size={14} />
                                {t("knowledgeBases.viewTable")}
                              </span>
                            ),
                          },
                        ]}
                      />
                      <input
                        ref={uploadRef}
                        className={styles.fileInput}
                        type="file"
                        multiple
                        accept={SUPPORTED_DOCUMENT_TYPES}
                        onChange={(event) =>
                          void uploadDocuments(event.target.files)
                        }
                      />
                      {canWriteSelected ? (
                        <Button
                          type="primary"
                          icon={<FileUp size={14} />}
                          disabled={isAtDocumentLimit}
                          onClick={() => uploadRef.current?.click()}
                        >
                          {t("knowledgeBases.upload")}
                        </Button>
                      ) : null}
                    </div>
                  </div>
                  {canWriteSelected ? (
                    <Typography.Text
                      type="secondary"
                      className={styles.uploadHint}
                    >
                      {t("knowledgeBases.uploadHint", {
                        sizeMb: Math.round(
                          limits.max_document_bytes / (1024 * 1024),
                        ),
                      })}
                    </Typography.Text>
                  ) : null}
                  {isAtDocumentLimit ? (
                    <Alert
                      className={styles.limitAlert}
                      type="info"
                      showIcon
                      message={t("knowledgeBases.documentLimitReached", {
                        count: limits.max_docs_per_kb,
                      })}
                    />
                  ) : null}
                  {documents.length === 0 ? (
                    <Empty
                      image={Empty.PRESENTED_IMAGE_SIMPLE}
                      description={t("knowledgeBases.emptyDocuments")}
                    />
                  ) : showCardView ? (
                    <div className={styles.docCardGrid}>
                      {documents.map((document) => (
                        <div key={document.id} className={styles.docCard}>
                          <div className={styles.docCardHeader}>
                            <DocumentFormatIcon
                              filename={document.filename}
                              size={14}
                            />
                            <div className={styles.docCardTitleBlock}>
                              <div className={styles.docCardTitleRow}>
                                <div
                                  className={styles.docCardName}
                                  title={document.filename}
                                >
                                  {document.filename}
                                </div>
                                {fileExtensionLabel(document.filename) ? (
                                  <span className={styles.docExtBadge}>
                                    {fileExtensionLabel(document.filename)}
                                  </span>
                                ) : null}
                              </div>
                              <div className={styles.docCardMeta}>
                                {formatBytes(document.byte_size)}
                                {" · "}
                                {t("knowledgeBases.chunkCount", {
                                  count: document.chunk_count,
                                })}
                              </div>
                            </div>
                            {renderDocumentActions(document)}
                          </div>
                          <div className={styles.docCardFooter}>
                            <Tooltip
                              title={
                                document.error_message ||
                                t(`knowledgeBases.statuses.${document.status}`)
                              }
                            >
                              <Tag
                                className={styles.docStatusTag}
                                color={documentStatusColor(document.status)}
                              >
                                {t(
                                  `knowledgeBases.statusesShort.${document.status}`,
                                )}
                              </Tag>
                            </Tooltip>
                            <span
                              className={styles.docUpdatedAt}
                              title={formatServerDateTime(
                                document.updated_at,
                                timeZone,
                              )}
                            >
                              {formatServerDateTime(
                                document.updated_at,
                                timeZone,
                              )}
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <Table
                      size="small"
                      rowKey="id"
                      pagination={false}
                      dataSource={documents}
                      locale={{
                        emptyText: t("knowledgeBases.emptyDocuments"),
                      }}
                      columns={[
                        {
                          title: t("knowledgeBases.filename"),
                          dataIndex: "filename",
                          key: "filename",
                          ellipsis: true,
                          render: (filename: string) => (
                            <span className={styles.tableFilename}>
                              <DocumentFormatIcon
                                filename={filename}
                                size={13}
                                className={styles.docTableIcon}
                              />
                              <span title={filename}>{filename}</span>
                              {fileExtensionLabel(filename) ? (
                                <span className={styles.docExtBadge}>
                                  {fileExtensionLabel(filename)}
                                </span>
                              ) : null}
                            </span>
                          ),
                        },
                        {
                          title: t("knowledgeBases.status"),
                          key: "status",
                          width: 100,
                          render: (_, document) => (
                            <Tooltip
                              title={document.error_message || undefined}
                            >
                              <Tag color={documentStatusColor(document.status)}>
                                {t(
                                  `knowledgeBases.statusesShort.${document.status}`,
                                )}
                              </Tag>
                            </Tooltip>
                          ),
                        },
                        {
                          title: t("knowledgeBases.chunks"),
                          dataIndex: "chunk_count",
                          key: "chunk_count",
                          width: 80,
                        },
                        {
                          title: t("knowledgeBases.updatedAt"),
                          dataIndex: "updated_at",
                          key: "updated_at",
                          width: 170,
                          render: (updatedAt: number) =>
                            formatServerDateTime(updatedAt, timeZone),
                        },
                        {
                          title: t("common.actions"),
                          key: "actions",
                          width: canWriteSelected ? 120 : 48,
                          render: (_, document) => (
                            <div className={styles.tableActions}>
                              {renderDocumentActions(document)}
                            </div>
                          ),
                        },
                      ]}
                    />
                  )}
                </div>
              </>
            )}
          </section>
        ) : null}
      </div>

      <Modal
        title={previewFilename || t("knowledgeBases.previewDocument")}
        open={previewOpen}
        onCancel={() => setPreviewOpen(false)}
        footer={null}
        width={720}
        destroyOnClose
      >
        <Spin spinning={previewLoading}>
          <pre className={styles.previewBody}>{previewText}</pre>
        </Spin>
      </Modal>

      <Modal
        title={t(editingBase ? "knowledgeBases.edit" : "knowledgeBases.create")}
        open={baseModalOpen}
        onCancel={() => setBaseModalOpen(false)}
        onOk={() => void saveBase()}
        okText={t(editingBase ? "common.save" : "common.create")}
        cancelText={t("common.cancel")}
        width={520}
        destroyOnClose
        className={styles.baseModal}
      >
        <Form
          form={baseForm}
          layout="vertical"
          className={styles.baseForm}
          requiredMark={false}
        >
          <Form.Item
            name="name"
            label={t("knowledgeBases.name")}
            rules={[
              {
                required: true,
                whitespace: true,
                message: t("knowledgeBases.nameRequired"),
              },
            ]}
          >
            <Input autoFocus maxLength={200} />
          </Form.Item>
          <Form.Item name="description" label={t("knowledgeBases.description")}>
            <Input.TextArea
              autoSize={{ minRows: 2, maxRows: 5 }}
              maxLength={2000}
              showCount
            />
          </Form.Item>
          <Form.Item name="icon_name" label={t("knowledgeBases.icon")}>
            <KnowledgeIconPicker />
          </Form.Item>
          <div className={styles.formOptions}>
            <div className={styles.formOptionRow}>
              <span className={styles.switchLabel}>
                {t("knowledgeBases.defaultOpen")}
                <Tooltip title={t("knowledgeBases.defaultOpenHint")}>
                  <CircleHelp size={14} className={styles.helpIcon} />
                </Tooltip>
              </span>
              <Form.Item name="default_open" valuePropName="checked" noStyle>
                <Switch size="small" />
              </Form.Item>
            </div>
            <div className={styles.formOptionRow}>
              <span className={styles.switchLabel}>
                {t("knowledgeBases.shared")}
                <Tooltip title={t("knowledgeBases.sharedHint")}>
                  <CircleHelp size={14} className={styles.helpIcon} />
                </Tooltip>
              </span>
              <Form.Item name="shared" valuePropName="checked" noStyle>
                <Switch size="small" />
              </Form.Item>
            </div>
          </div>
        </Form>
      </Modal>

      <Modal
        title={
          <span className={styles.switchLabel}>
            {t("knowledgeBases.settingsTitle")}
            <Tooltip title={t("knowledgeBases.featureDescription")}>
              <CircleHelp size={14} className={styles.helpIcon} />
            </Tooltip>
          </span>
        }
        open={featureModalOpen}
        onCancel={() => setFeatureModalOpen(false)}
        onOk={() => void saveFeature()}
        okButtonProps={{
          disabled: featureEnabledDraft
            ? !featureModel ||
              (featureBackend === "remote" && !featureProviderId) ||
              featureOptionsLoading
            : false,
        }}
        okText={t("common.save")}
        cancelText={t("common.cancel")}
        destroyOnClose
      >
        <div className={styles.settingsEnableRow}>
          <Typography.Text className={styles.switchLabel}>
            {t("knowledgeBases.settingsOpen")}
            <Tooltip title={t("knowledgeBases.settingsOpenHint")}>
              <CircleHelp size={14} className={styles.helpIcon} />
            </Tooltip>
          </Typography.Text>
          <Switch
            checked={featureEnabledDraft}
            onChange={setFeatureEnabledDraft}
          />
        </div>

        {featureEnabledDraft ? (
          <Spin spinning={featureOptionsLoading}>
            <Typography.Text
              type="secondary"
              className={styles.settingsSection}
            >
              {t("knowledgeBases.selectModel")}
            </Typography.Text>
            <Radio.Group
              className={styles.featureBackend}
              value={featureBackend}
              onChange={(event) => {
                setFeatureBackend(event.target.value);
                setFeatureModel(undefined);
              }}
            >
              <Radio value="onnx">{t("knowledgeBases.localOnnx")}</Radio>
              <Radio value="remote">
                {t("knowledgeBases.remoteEmbedding")}
              </Radio>
            </Radio.Group>
            {featureBackend === "remote" ? (
              <div className={styles.featureFields}>
                <Select
                  value={featureProviderId}
                  onChange={(id) => {
                    setFeatureProviderId(id);
                    setFeatureModel(undefined);
                  }}
                  placeholder={t("knowledgeBases.selectProvider")}
                  options={remoteProviders.map((provider) => ({
                    value: provider.provider_id,
                    label: provider.provider_name,
                  }))}
                  notFoundContent={t("knowledgeBases.noProviders")}
                />
                <Select
                  value={featureModel}
                  onChange={setFeatureModel}
                  placeholder={t("knowledgeBases.selectModel")}
                  options={remoteProviders
                    .find(
                      (provider) => provider.provider_id === featureProviderId,
                    )
                    ?.models.map((model) => ({
                      value: model.id,
                      label: model.name,
                    }))}
                  notFoundContent={t("knowledgeBases.noModels")}
                />
              </div>
            ) : (
              <div className={styles.featureFields}>
                <Select
                  value={featureModel}
                  onChange={setFeatureModel}
                  placeholder={t("knowledgeBases.selectModel")}
                  options={catalog.map((model) => ({
                    value: model.id,
                    label: `${model.name}${
                      model.downloaded
                        ? ""
                        : ` (${t("knowledgeBases.notDownloaded")})`
                    }`,
                    disabled: !model.downloaded,
                  }))}
                  notFoundContent={t("knowledgeBases.noModels")}
                />
              </div>
            )}
            <div className={styles.modalChecks}>
              <Tag color={featureModel ? "success" : "default"}>
                {t("knowledgeBases.modelSelected")}
              </Tag>
              <Tag
                color={
                  featureBackend === "remote"
                    ? featureProviderId
                      ? "success"
                      : "default"
                    : catalog.find((model) => model.id === featureModel)
                        ?.downloaded
                    ? "success"
                    : "default"
                }
              >
                {featureBackend === "remote"
                  ? t("knowledgeBases.providerReady")
                  : t("knowledgeBases.modelDownloaded")}
              </Tag>
              <Tag
                color={
                  capability?.checks.deps_available ? "success" : "default"
                }
              >
                {t("knowledgeBases.dependenciesReady")}
              </Tag>
            </div>
            <Typography.Link href="/admin/models">
              {t("knowledgeBases.manageModels")}
            </Typography.Link>
          </Spin>
        ) : null}
      </Modal>
    </PageShell>
  );
}
