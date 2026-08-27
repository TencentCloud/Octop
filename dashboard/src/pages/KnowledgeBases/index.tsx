import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type CSSProperties,
} from "react";
import {
  Alert,
  App,
  Button,
  Drawer,
  Empty,
  Form,
  Input,
  InputNumber,
  List,
  Modal,
  Popconfirm,
  Progress,
  Radio,
  Segmented,
  Select,
  Spin,
  Switch,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import { ResizableTable } from "@/components/ResizableTable";
import {
  Check,
  ChevronLeft,
  Download,
  Eye,
  FilePlus,
  FileUp,
  Folder,
  FolderPlus,
  LayoutGrid,
  List as ListIcon,
  PanelLeftClose,
  PanelLeftOpen,
  Pencil,
  PencilLine,
  Plus,
  RefreshCw,
  Settings,
  Trash2,
  X,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { useCurrentUser } from "../../hooks/useCurrentUser";
import { userCan } from "../../utils/permissions";
import {
  DEFAULT_KNOWLEDGE_LIMITS,
  knowledgeBasesApi,
  type KnowledgeBase,
  type KnowledgeCapability,
  type KnowledgeDocument,
  type KnowledgeOnnxModel,
} from "../../api/modules/knowledgeBases";
import { OctopEmptyMascot } from "../../components/EmptyState";
import StreamSetupGuide from "../../components/StreamSetupGuide/StreamSetupGuide";
import { CopyableResourceId } from "../../components/CopyableResourceId";
import { useCardTableView } from "../../hooks/useCardTableView";
import { useHorizontalResize } from "../../hooks/useHorizontalResize";
import { useIsMobile } from "../../hooks/useIsMobile";
import { useListPanelCollapsed } from "../../hooks/useListPanelCollapsed";
import { useServerTimezone } from "../../hooks/useServerTimezone";
import PageShell from "../../layouts/PageShell";
import { apiErrorMessage, isNotFoundApiError } from "../../utils/apiError";
import { createDetailRequestGate } from "../../utils/detailRequestGate";
import { formatBytes, formatSizeGb } from "../../utils/embeddingDownload";
import { fileTreeIconSpec } from "../../utils/fileTreeIcon";
import { formatServerDateTime } from "../../utils/formatMessageTime";
import skillStyles from "../Agent/Skills/index.module.less";
import { KNOWLEDGE_ICON_NAMES, knowledgeIconForName } from "./knowledgeIcons";
import {
  isDirectKnowledgeChild,
  joinKnowledgePath,
  knowledgeBasename,
  knowledgeBreadcrumb,
  shouldOpenKnowledgeFolder,
} from "./knowledgeFolder";
import TextDocumentEditorModal, {
  isEditableKnowledgeDocument,
  type TextDocumentFormat,
} from "./TextDocumentEditorModal";
import styles from "./index.module.less";

type BaseFormValues = {
  name: string;
  description?: string;
  icon_name?: string;
  max_documents?: number;
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

const FOLDER_ICON_COLOR = "#d97706";

function DocumentFormatIcon({
  filename,
  size = 14,
  className,
  isDir = false,
}: {
  filename: string;
  size?: number;
  className?: string;
  isDir?: boolean;
}) {
  const { Icon, color } = isDir
    ? { Icon: Folder, color: FOLDER_ICON_COLOR }
    : fileTreeIconSpec(filename);
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

function ReadinessRow({
  label,
  ok,
  okText,
  failText,
}: {
  label: string;
  ok: boolean;
  okText: string;
  failText: string;
}) {
  return (
    <div className={styles.onnxReadinessRow}>
      <span className={styles.onnxReadinessLabel}>{label}</span>
      {ok ? (
        <Check size={13} color="var(--fn-color-success)" />
      ) : (
        <X size={13} color="var(--fn-color-warning)" />
      )}
      <Typography.Text type={ok ? "success" : "warning"}>
        {ok ? okText : failText}
      </Typography.Text>
    </div>
  );
}

export default function KnowledgeBasesPage() {
  const { t } = useTranslation();
  const { modal, message } = App.useApp();
  const navigate = useNavigate();
  const isMobile = useIsMobile();
  const timeZone = useServerTimezone();
  const user = useCurrentUser();
  const canConfigureKb = userCan(user, "knowledge_settings");
  const { viewMode, setViewMode, showCardView } = useCardTableView(
    loadDocsViewMode(),
  );
  const [bases, setBases] = useState<KnowledgeBase[]>([]);
  const [selected, setSelected] = useState<KnowledgeBase | null>(null);
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [currentFolder, setCurrentFolder] = useState("");
  const [folderModalOpen, setFolderModalOpen] = useState(false);
  const [folderName, setFolderName] = useState("");
  const [renameModalOpen, setRenameModalOpen] = useState(false);
  const [renameTarget, setRenameTarget] = useState<KnowledgeDocument | null>(
    null,
  );
  const [renameName, setRenameName] = useState("");
  const [capability, setCapability] = useState<KnowledgeCapability | null>(
    null,
  );
  const [catalog, setCatalog] = useState<KnowledgeOnnxModel[]>([]);
  const [onnxDownloading, setOnnxDownloading] = useState(false);
  const [downloadProgressOpen, setDownloadProgressOpen] = useState(false);
  const [downloadProgress, setDownloadProgress] = useState(0);
  const [downloadProgressLabel, setDownloadProgressLabel] = useState("");
  const [downloadProgressModel, setDownloadProgressModel] = useState("");
  const onnxDownloadTimer = useRef<ReturnType<typeof setInterval> | null>(null);
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
  const [onnxProbe, setOnnxProbe] = useState<{
    ok: boolean;
    latency_ms?: number | null;
    dim?: number | null;
    error?: string | null;
  } | null>(null);
  const [onnxProbing, setOnnxProbing] = useState(false);
  const [featureEnabledDraft, setFeatureEnabledDraft] = useState(false);
  const [featureModel, setFeatureModel] = useState<string>();
  const [featureBackend, setFeatureBackend] = useState<"onnx" | "remote">(
    "onnx",
  );
  const [featureProviderId, setFeatureProviderId] = useState<string>();
  const [featureOptionsLoading, setFeatureOptionsLoading] = useState(false);
  const [onnxExpanded, setOnnxExpanded] = useState(false);
  const [onnxExpanding, setOnnxExpanding] = useState(false);
  const onnxExpandedRef = useRef(false);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewFilename, setPreviewFilename] = useState("");
  const [previewText, setPreviewText] = useState("");
  const [textEditorOpen, setTextEditorOpen] = useState(false);
  const [textEditorMode, setTextEditorMode] = useState<"create" | "edit">(
    "create",
  );
  const [textEditorLoading, setTextEditorLoading] = useState(false);
  const [textEditorSaving, setTextEditorSaving] = useState(false);
  const [textEditorDocId, setTextEditorDocId] = useState<string | null>(null);
  const [textEditorName, setTextEditorName] = useState("");
  const [textEditorFormat, setTextEditorFormat] =
    useState<TextDocumentFormat>("md");
  const [textEditorContent, setTextEditorContent] = useState("");
  const [baseForm] = Form.useForm<BaseFormValues>();
  const [defaultOpenChecked, setDefaultOpenChecked] = useState(false);
  const [sharedChecked, setSharedChecked] = useState(false);
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
  const fileCount = documents.filter((document) => !document.is_dir).length;
  const isAtDocumentLimit =
    fileCount >= (selected?.max_documents ?? limits.max_docs_per_kb);
  const folderEntries = documents
    .filter((document) =>
      isDirectKnowledgeChild(document.path || document.filename, currentFolder),
    )
    .sort((a, b) => {
      const dirDelta = Number(Boolean(b.is_dir)) - Number(Boolean(a.is_dir));
      if (dirDelta !== 0) return dirDelta;
      return knowledgeBasename(a.path || a.filename).localeCompare(
        knowledgeBasename(b.path || b.filename),
      );
    });
  const folderCrumbs = knowledgeBreadcrumb(
    currentFolder,
    t("knowledgeBases.documents"),
  );

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

  const loadEmbeddingOptions = useCallback(
    async (allOnnx = false) => {
      if (allOnnx) {
        setOnnxExpanding(true);
      } else {
        setFeatureOptionsLoading(true);
      }
      try {
        const options = await knowledgeBasesApi.getEmbeddingOptions({
          allOnnx,
        });
        setCatalog(options.onnx);
        setRemoteProviders(options.remote);
        if (allOnnx) {
          onnxExpandedRef.current = true;
          setOnnxExpanded(true);
        }
        return options;
      } catch (error) {
        message.error(
          apiErrorMessage(error, t("knowledgeBases.loadFailed"), t),
        );
        return undefined;
      } finally {
        setFeatureOptionsLoading(false);
        setOnnxExpanding(false);
      }
    },
    [t],
  );

  const stopOnnxDownloadWatch = useCallback(() => {
    if (onnxDownloadTimer.current) {
      clearInterval(onnxDownloadTimer.current);
      onnxDownloadTimer.current = null;
    }
  }, []);

  const applyOnnxDownloadProgress = useCallback(
    (modelId: string, status: string, progress: number) => {
      const pct = Math.max(0, Math.min(100, Math.round((progress || 0) * 100)));
      setDownloadProgress(pct);
      if (status === "loading") {
        setDownloadProgressLabel(
          t("models.onnxDownloadLoading", { model: modelId }),
        );
      } else if (status === "downloading") {
        setDownloadProgressLabel(
          t("models.onnxDownloading", { model: modelId }),
        );
      } else {
        setDownloadProgressLabel(t("models.localDownloadPreparing"));
      }
    },
    [t],
  );

  const finishOnnxDownload = useCallback(
    async (modelId: string, status: string, error?: string | null) => {
      stopOnnxDownloadWatch();
      setOnnxDownloading(false);
      setDownloadProgressOpen(false);
      await loadEmbeddingOptions(onnxExpandedRef.current);
      if (status === "done") {
        try {
          await knowledgeBasesApi.activateOnnx(modelId);
          message.success(t("knowledgeBases.onnxServiceEnabled"));
        } catch (activateError) {
          message.success(t("models.onnxDownloadDone", { model: modelId }));
          message.warning(
            apiErrorMessage(
              activateError,
              t("knowledgeBases.featureSaveFailed"),
              t,
            ),
          );
        }
        return;
      }
      message.error(error || t("models.onnxDownloadFailed"));
    },
    [loadEmbeddingOptions, stopOnnxDownloadWatch, t],
  );

  const watchOnnxDownloadStatus = useCallback(
    (modelId: string) => {
      stopOnnxDownloadWatch();
      let inFlight = false;
      let stopped = false;
      const tick = async () => {
        if (inFlight || stopped) return;
        inFlight = true;
        try {
          const state = await knowledgeBasesApi.getOnnxDownloadStatus();
          applyOnnxDownloadProgress(
            state.model_name || modelId,
            state.status,
            state.progress,
          );
          if (state.status === "done" || state.status === "failed") {
            stopped = true;
            stopOnnxDownloadWatch();
            await finishOnnxDownload(
              state.model_name || modelId,
              state.status,
              state.error,
            );
          }
        } catch (error) {
          stopped = true;
          stopOnnxDownloadWatch();
          await finishOnnxDownload(
            modelId,
            "failed",
            error instanceof Error ? error.message : String(error),
          );
        } finally {
          inFlight = false;
        }
      };
      onnxDownloadTimer.current = setInterval(() => {
        void tick();
      }, 500);
      void tick();
    },
    [applyOnnxDownloadProgress, finishOnnxDownload, stopOnnxDownloadWatch],
  );

  useEffect(() => () => stopOnnxDownloadWatch(), [stopOnnxDownloadWatch]);

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
    setCurrentFolder("");
  }, [selected?.id]);

  useEffect(() => {
    void Promise.all([loadBases(), loadCapability()]).finally(() =>
      setLoading(false),
    );
  }, [loadBases, loadCapability]);

  useEffect(() => {
    const indexing = documents.some(
      (document) =>
        !document.is_dir &&
        (document.status === "pending" || document.status === "processing"),
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
      icon_name: "book-open",
      max_documents: 100,
    });
    setDefaultOpenChecked(false);
    setSharedChecked(false);
    setEditingBase(false);
    setBaseModalOpen(true);
  };

  const openEdit = () => {
    if (!selected) return;
    baseForm.setFieldsValue({
      name: selected.name,
      description: selected.description,
      icon_name: selected.icon_name || undefined,
      max_documents: selected.max_documents,
    });
    setDefaultOpenChecked(selected.default_open);
    setSharedChecked(selected.shared);
    setEditingBase(true);
    setBaseModalOpen(true);
  };

  const saveBase = async () => {
    const values = await baseForm.validateFields();
    const payload = {
      ...values,
      default_open: defaultOpenChecked,
      shared: sharedChecked,
    };
    try {
      const next =
        editingBase && selected
          ? await knowledgeBasesApi.update(selected.id, payload)
          : await knowledgeBasesApi.create(payload);
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

  // A probe describes one model; drop it as soon as the draft points elsewhere.
  useEffect(() => {
    setOnnxProbe(null);
  }, [featureModel, featureBackend]);

  const runOnnxProbe = async () => {
    if (!featureModel) return;
    setOnnxProbing(true);
    try {
      setOnnxProbe(await knowledgeBasesApi.testOnnx(featureModel));
    } catch (error) {
      setOnnxProbe({
        ok: false,
        error: error instanceof Error ? error.message : String(error),
      });
    } finally {
      setOnnxProbing(false);
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
      featureBackend === "onnx" &&
      !catalog.find((model) => model.id === featureModel)?.downloaded
    ) {
      message.warning(t("knowledgeBases.downloadNeedModel"));
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
      modal.confirm({
        title: t("knowledgeBases.rebuildConfirmTitle"),
        content: t("knowledgeBases.rebuildConfirmDescription"),
        okText: t("common.confirm"),
        cancelText: t("common.cancel"),
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
    const selectedModel = capability?.selected_model || undefined;
    const selectedBackend = capability?.backend ?? "onnx";
    onnxExpandedRef.current = false;
    setOnnxExpanded(false);
    setFeatureEnabledDraft(Boolean(capability?.feature_enabled));
    setFeatureBackend(selectedBackend);
    setFeatureModel(selectedModel);
    setFeatureProviderId(capability?.provider_id || undefined);
    setFeatureModalOpen(true);
    void (async () => {
      const options = await loadEmbeddingOptions(false);
      const selectedInCatalog = Boolean(
        selectedModel &&
          options?.onnx.some((model) => model.id === selectedModel),
      );
      if (selectedBackend === "onnx" && selectedModel && !selectedInCatalog) {
        await loadEmbeddingOptions(true);
      }
    })();
    void knowledgeBasesApi.getOnnxDownloadStatus().then((state) => {
      if (state.status === "downloading" || state.status === "loading") {
        const modelId = state.model_name;
        setOnnxDownloading(true);
        setDownloadProgressModel(modelId);
        setDownloadProgressOpen(true);
        applyOnnxDownloadProgress(modelId, state.status, state.progress);
        watchOnnxDownloadStatus(modelId);
      }
    });
  };

  const startOnnxDownload = async (modelId: string) => {
    const selected = catalog.find((model) => model.id === modelId);
    const size = formatSizeGb(selected?.size_gb);
    modal.confirm({
      title: t("models.localDownloadConfirmTitle"),
      content: t("models.localDownloadConfirmOnnx", {
        name: modelId,
        size: size || t("knowledgeBases.sizeUnknown"),
      }),
      okText: t("knowledgeBases.downloadModel"),
      cancelText: t("common.cancel"),
      onOk: async () => {
        setOnnxDownloading(true);
        setDownloadProgressModel(modelId);
        setDownloadProgress(0);
        setDownloadProgressLabel(t("models.localDownloadPreparing"));
        setDownloadProgressOpen(true);
        try {
          await knowledgeBasesApi.downloadOnnx(modelId);
          watchOnnxDownloadStatus(modelId);
        } catch (error) {
          setOnnxDownloading(false);
          setDownloadProgressOpen(false);
          message.error(
            apiErrorMessage(error, t("models.onnxDownloadFailed"), t),
          );
        }
      },
    });
  };

  const dismissDownloadProgressToBackground = () => {
    setDownloadProgressOpen(false);
    message.info(t("models.localDownloadBackground"));
  };

  const uploadDocuments = async (files: FileList | null) => {
    if (!selected || !files || !usable || isAtDocumentLimit) return;
    const remaining = Math.max(
      0,
      (selected?.max_documents ?? limits.max_docs_per_kb) - fileCount,
    );
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
        await knowledgeBasesApi.uploadDocument(
          selected.id,
          file,
          joinKnowledgePath(currentFolder, file.name),
        );
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

  const createFolder = async () => {
    if (!selected) return;
    const name = folderName.trim();
    if (!name) return;
    try {
      await knowledgeBasesApi.createFolder(
        selected.id,
        joinKnowledgePath(currentFolder, name),
      );
      setFolderModalOpen(false);
      setFolderName("");
      await loadDetail(selected.id, { silent: true });
    } catch (error) {
      message.error(
        apiErrorMessage(error, t("knowledgeBases.createFolderFailed"), t),
      );
    }
  };

  const openRenameFolder = (document: KnowledgeDocument) => {
    setRenameTarget(document);
    setRenameName(knowledgeBasename(document.path || document.filename));
    setRenameModalOpen(true);
  };

  const renameFolder = async () => {
    if (!selected || !renameTarget) return;
    const name = renameName.trim();
    if (!name) return;
    if (
      name === knowledgeBasename(renameTarget.path || renameTarget.filename)
    ) {
      setRenameModalOpen(false);
      return;
    }
    try {
      await knowledgeBasesApi.renameDocument(
        selected.id,
        renameTarget.id,
        name,
      );
      setRenameModalOpen(false);
      setRenameTarget(null);
      setRenameName("");
      await loadDetail(selected.id);
      message.success(t("knowledgeBases.renameFolderSuccess"));
    } catch (error) {
      message.error(
        apiErrorMessage(error, t("knowledgeBases.renameFolderFailed"), t),
      );
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

  const openCreateTextDocument = () => {
    setTextEditorMode("create");
    setTextEditorDocId(null);
    setTextEditorName("");
    setTextEditorFormat("md");
    setTextEditorContent("");
    setTextEditorLoading(false);
    setTextEditorOpen(true);
  };

  const openEditTextDocument = async (document: KnowledgeDocument) => {
    if (!selected) return;
    setTextEditorMode("edit");
    setTextEditorDocId(document.id);
    setTextEditorName(document.filename);
    setTextEditorFormat(
      document.filename.toLowerCase().endsWith(".txt") ||
        document.content_type === "text/plain"
        ? "txt"
        : "md",
    );
    setTextEditorContent("");
    setTextEditorOpen(true);
    setTextEditorLoading(true);
    try {
      const payload = await knowledgeBasesApi.getTextDocument(
        selected.id,
        document.id,
      );
      setTextEditorContent(payload.text);
      setTextEditorName(payload.filename);
      setTextEditorFormat(
        payload.content_type === "text/plain" ||
          payload.filename.toLowerCase().endsWith(".txt")
          ? "txt"
          : "md",
      );
    } catch (error) {
      setTextEditorOpen(false);
      message.error(
        apiErrorMessage(error, t("knowledgeBases.editDocumentFailed"), t),
      );
    } finally {
      setTextEditorLoading(false);
    }
  };

  const saveTextDocument = async (values: {
    name: string;
    format: TextDocumentFormat;
    content: string;
  }) => {
    if (!selected) return;
    setTextEditorSaving(true);
    try {
      if (textEditorMode === "create") {
        await knowledgeBasesApi.createTextDocument(selected.id, {
          name: values.name,
          format: values.format,
          content: values.content,
          path: currentFolder || undefined,
        });
        message.success(t("knowledgeBases.createFileSuccess"));
      } else if (textEditorDocId) {
        await knowledgeBasesApi.updateTextDocument(
          selected.id,
          textEditorDocId,
          values.content,
        );
        message.success(t("knowledgeBases.editDocumentSuccess"));
      }
      setTextEditorOpen(false);
      await loadDetail(selected.id);
    } catch (error) {
      message.error(
        apiErrorMessage(
          error,
          textEditorMode === "create"
            ? t("knowledgeBases.createFileFailed")
            : t("knowledgeBases.editDocumentFailed"),
          t,
        ),
      );
    } finally {
      setTextEditorSaving(false);
    }
  };

  const renderDocumentActions = (document: KnowledgeDocument) => (
    <div
      className={styles.docCardActions}
      data-kb-doc-actions=""
      onClick={(event) => event.stopPropagation()}
    >
      {document.is_dir ? null : (
        <Tooltip title={t("knowledgeBases.previewDocument")}>
          <Button
            type="text"
            size="small"
            icon={<Eye size={14} />}
            aria-label={t("knowledgeBases.previewDocument")}
            onClick={() => void openDocumentPreview(document.id)}
          />
        </Tooltip>
      )}
      {canWriteSelected ? (
        <>
          {!document.is_dir && isEditableKnowledgeDocument(document) ? (
            <Tooltip title={t("knowledgeBases.editDocument")}>
              <Button
                type="text"
                size="small"
                icon={<Pencil size={14} />}
                aria-label={t("knowledgeBases.editDocument")}
                onClick={() => void openEditTextDocument(document)}
              />
            </Tooltip>
          ) : null}
          {document.is_dir ? null : (
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
          )}
          {document.is_dir ? (
            <Tooltip title={t("knowledgeBases.renameFolder")}>
              <Button
                type="text"
                size="small"
                icon={<PencilLine size={14} />}
                aria-label={t("knowledgeBases.renameFolder")}
                onClick={(event) => {
                  event.stopPropagation();
                  openRenameFolder(document);
                }}
              />
            </Tooltip>
          ) : null}
          <Popconfirm
            title={
              document.is_dir
                ? t("knowledgeBases.deleteFolderConfirm")
                : t("knowledgeBases.deleteDocumentConfirm")
            }
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
  const showEnableGuide = !loading && !usable;
  const showEmptyGuide = !loading && usable && bases.length === 0;
  const emptyLayoutClassName = `${styles.emptyLayout}${
    isMobile ? ` ${styles.emptyLayoutMobile}` : ""
  }`;
  const setupMascot = (
    <OctopEmptyMascot size={120} className={styles.setupMascot} />
  );

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
      {loading ? (
        <div className={emptyLayoutClassName}>
          <div className={styles.centered}>
            <Spin />
          </div>
        </div>
      ) : showEnableGuide ? (
        <div className={emptyLayoutClassName}>
          <StreamSetupGuide
            className={styles.emptyGuide}
            wide
            icon={setupMascot}
            title={
              canConfigureKb
                ? t("knowledgeBases.enableGuideTitle")
                : t("knowledgeBases.unavailableTitle")
            }
            description={
              canConfigureKb
                ? t("knowledgeBases.enableGuideDesc")
                : t("knowledgeBases.unavailableDescriptionNonAdmin")
            }
            steps={
              canConfigureKb
                ? [
                    {
                      label: t("knowledgeBases.enableGuideStepOpen"),
                      detail: t("knowledgeBases.enableGuideStepOpenDetail"),
                    },
                    {
                      label: t("knowledgeBases.enableGuideStepToggle"),
                      detail: t("knowledgeBases.enableGuideStepToggleDetail"),
                    },
                    {
                      label: t("knowledgeBases.enableGuideStepModel"),
                      detail: t("knowledgeBases.enableGuideStepModelDetail"),
                    },
                  ]
                : []
            }
            primaryAction={
              canConfigureKb
                ? {
                    label: t("knowledgeBases.settingsTitle"),
                    onClick: openSettings,
                    icon: <Settings size={14} />,
                  }
                : undefined
            }
          />
        </div>
      ) : showEmptyGuide ? (
        <div className={emptyLayoutClassName}>
          <StreamSetupGuide
            className={styles.emptyGuide}
            wide
            icon={setupMascot}
            title={t("knowledgeBases.emptyGuideTitle")}
            description={t("knowledgeBases.emptyGuideDesc")}
            steps={[
              {
                label: t("knowledgeBases.emptyGuideStepWhat"),
                detail: t("knowledgeBases.emptyGuideStepWhatDetail"),
              },
              {
                label: t("knowledgeBases.emptyGuideStepHow"),
                detail: t("knowledgeBases.emptyGuideStepHowDetail"),
              },
              {
                label: t("knowledgeBases.emptyGuideStepShare"),
                detail: t("knowledgeBases.emptyGuideStepShareDetail"),
              },
            ]}
            primaryAction={{
              label: t("knowledgeBases.create"),
              onClick: openCreate,
              icon: <Plus size={14} />,
              disabled: atBaseLimit,
            }}
          />
        </div>
      ) : (
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
                          {base.description ||
                            t("knowledgeBases.noDescription")}
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
                      {selected.description ||
                        t("knowledgeBases.noDescription")}
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
                          count: fileCount,
                          max:
                            selected?.max_documents ?? limits.max_docs_per_kb,
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
                            icon={<FolderPlus size={14} />}
                            onClick={() => {
                              setFolderName("");
                              setFolderModalOpen(true);
                            }}
                          >
                            {t("knowledgeBases.createFolder")}
                          </Button>
                        ) : null}
                        {canWriteSelected ? (
                          <Button
                            icon={<FilePlus size={14} />}
                            disabled={isAtDocumentLimit}
                            onClick={openCreateTextDocument}
                          >
                            {t("knowledgeBases.createFile")}
                          </Button>
                        ) : null}
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
                    <div className={styles.docsPathRow}>
                      <nav
                        className={styles.pathBreadcrumb}
                        aria-label={t("knowledgeBases.pathBreadcrumb")}
                      >
                        {folderCrumbs.map((seg, index) => {
                          const isLast = index === folderCrumbs.length - 1;
                          return (
                            <span
                              key={`${seg.path}:${index}`}
                              className={styles.pathBreadcrumbSegment}
                            >
                              {index > 0 ? (
                                <span
                                  className={styles.pathBreadcrumbSep}
                                  aria-hidden
                                >
                                  /
                                </span>
                              ) : null}
                              {isLast ? (
                                <span
                                  className={styles.pathBreadcrumbCurrent}
                                  title={seg.label}
                                >
                                  {seg.label}
                                </span>
                              ) : (
                                <button
                                  type="button"
                                  className={styles.pathBreadcrumbLink}
                                  onClick={() => setCurrentFolder(seg.path)}
                                  title={seg.label}
                                >
                                  {seg.label}
                                </button>
                              )}
                            </span>
                          );
                        })}
                      </nav>
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
                    </div>
                    {isAtDocumentLimit ? (
                      <Alert
                        className={styles.limitAlert}
                        type="info"
                        showIcon
                        message={t("knowledgeBases.documentLimitReached", {
                          count:
                            selected?.max_documents ?? limits.max_docs_per_kb,
                        })}
                      />
                    ) : null}
                    {folderEntries.length === 0 ? (
                      <Empty
                        image={Empty.PRESENTED_IMAGE_SIMPLE}
                        description={t("knowledgeBases.emptyDocuments")}
                      />
                    ) : showCardView ? (
                      <div className={styles.docCardGrid}>
                        {folderEntries.map((document) => {
                          const name = knowledgeBasename(
                            document.path || document.filename,
                          );
                          return (
                            <div
                              key={document.id}
                              className={styles.docCard}
                              role={document.is_dir ? "button" : undefined}
                              onClick={(event) => {
                                if (
                                  !shouldOpenKnowledgeFolder(
                                    Boolean(document.is_dir),
                                    event,
                                  )
                                ) {
                                  return;
                                }
                                setCurrentFolder(
                                  document.path || document.filename,
                                );
                              }}
                            >
                              <div className={styles.docCardHeader}>
                                <DocumentFormatIcon
                                  filename={name}
                                  size={14}
                                  isDir={document.is_dir}
                                />
                                <div className={styles.docCardTitleBlock}>
                                  <div className={styles.docCardTitleRow}>
                                    <div
                                      className={styles.docCardName}
                                      title={document.path || name}
                                    >
                                      {name}
                                    </div>
                                    {!document.is_dir &&
                                    fileExtensionLabel(name) ? (
                                      <span className={styles.docExtBadge}>
                                        {fileExtensionLabel(name)}
                                      </span>
                                    ) : null}
                                  </div>
                                  <div className={styles.docCardMeta}>
                                    {document.is_dir
                                      ? t("knowledgeBases.folder")
                                      : `${formatBytes(
                                          document.byte_size,
                                        )} · ${t("knowledgeBases.chunkCount", {
                                          count: document.chunk_count,
                                        })}`}
                                  </div>
                                </div>
                                <span
                                  data-kb-doc-actions=""
                                  onClick={(event) => event.stopPropagation()}
                                >
                                  {renderDocumentActions(document)}
                                </span>
                              </div>
                              {document.is_dir ? null : (
                                <div className={styles.docCardFooter}>
                                  <Tooltip
                                    title={
                                      document.error_message ||
                                      t(
                                        `knowledgeBases.statuses.${document.status}`,
                                      )
                                    }
                                  >
                                    <Tag
                                      className={styles.docStatusTag}
                                      color={documentStatusColor(
                                        document.status,
                                      )}
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
                              )}
                            </div>
                          );
                        })}
                      </div>
                    ) : (
                      <ResizableTable
                        storageKey="kb-documents"
                        size="small"
                        rowKey="id"
                        pagination={false}
                        dataSource={folderEntries}
                        onRow={(document) => ({
                          onClick: document.is_dir
                            ? (event) => {
                                if (!shouldOpenKnowledgeFolder(true, event)) {
                                  return;
                                }
                                setCurrentFolder(
                                  document.path || document.filename,
                                );
                              }
                            : undefined,
                        })}
                        locale={{
                          emptyText: t("knowledgeBases.emptyDocuments"),
                        }}
                        columns={[
                          {
                            title: t("knowledgeBases.filename"),
                            key: "filename",
                            ellipsis: true,
                            render: (_, document) => {
                              const name = knowledgeBasename(
                                document.path || document.filename,
                              );
                              return (
                                <span className={styles.tableFilename}>
                                  <DocumentFormatIcon
                                    filename={name}
                                    size={13}
                                    className={styles.docTableIcon}
                                    isDir={document.is_dir}
                                  />
                                  <span title={document.path || name}>
                                    {name}
                                  </span>
                                  {!document.is_dir &&
                                  fileExtensionLabel(name) ? (
                                    <span className={styles.docExtBadge}>
                                      {fileExtensionLabel(name)}
                                    </span>
                                  ) : null}
                                </span>
                              );
                            },
                          },
                          {
                            title: t("knowledgeBases.entryType"),
                            key: "entry_type",
                            width: 88,
                            render: (_, document) =>
                              document.is_dir
                                ? t("knowledgeBases.folder")
                                : t("knowledgeBases.file"),
                          },
                          {
                            title: t("knowledgeBases.status"),
                            key: "status",
                            width: 100,
                            render: (_, document) =>
                              document.is_dir ? (
                                "—"
                              ) : (
                                <Tooltip
                                  title={document.error_message || undefined}
                                >
                                  <Tag
                                    color={documentStatusColor(document.status)}
                                  >
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
                            render: (chunkCount: number, document) =>
                              document.is_dir ? "—" : chunkCount,
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
                              <div
                                className={styles.tableActions}
                                data-kb-doc-actions=""
                                onClick={(event) => event.stopPropagation()}
                              >
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
      )}

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
        title={t("knowledgeBases.createFolder")}
        open={folderModalOpen}
        onCancel={() => setFolderModalOpen(false)}
        onOk={() => void createFolder()}
        okText={t("common.create")}
        cancelText={t("common.cancel")}
        destroyOnClose
      >
        <Input
          value={folderName}
          onChange={(event) => setFolderName(event.target.value)}
          placeholder={t("knowledgeBases.folderNamePlaceholder")}
          onPressEnter={() => void createFolder()}
        />
      </Modal>

      <Modal
        title={t("knowledgeBases.renameFolder")}
        open={renameModalOpen}
        onCancel={() => setRenameModalOpen(false)}
        onOk={() => void renameFolder()}
        okText={t("common.save")}
        cancelText={t("common.cancel")}
        destroyOnClose
      >
        <Input
          value={renameName}
          onChange={(event) => setRenameName(event.target.value)}
          placeholder={t("knowledgeBases.folderNamePlaceholder")}
          onPressEnter={() => void renameFolder()}
        />
      </Modal>

      <TextDocumentEditorModal
        open={textEditorOpen}
        mode={textEditorMode}
        loading={textEditorLoading}
        saving={textEditorSaving}
        initialName={textEditorName}
        initialFormat={textEditorFormat}
        initialContent={textEditorContent}
        onCancel={() => setTextEditorOpen(false)}
        onSubmit={saveTextDocument}
      />

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
          <Form.Item
            name="max_documents"
            label={t("knowledgeBases.maxDocuments")}
            extra={t("knowledgeBases.maxDocumentsHint")}
          >
            <InputNumber
              min={0}
              max={10000}
              step={1}
              precision={0}
              style={{ width: "100%" }}
            />
          </Form.Item>
          <Form.Item name="icon_name" label={t("knowledgeBases.icon")}>
            <KnowledgeIconPicker />
          </Form.Item>
          <div className={styles.formOptions}>
            <div className={styles.formOptionRow}>
              <div className={styles.formOptionCopy}>
                <span className={styles.switchLabel}>
                  {t("knowledgeBases.defaultOpen")}
                </span>
                <span className={styles.formOptionHint}>
                  {t("knowledgeBases.defaultOpenHint")}
                </span>
              </div>
              <Switch
                size="small"
                checked={defaultOpenChecked}
                onChange={setDefaultOpenChecked}
              />
            </div>
            <div className={styles.formOptionRow}>
              <div className={styles.formOptionCopy}>
                <span className={styles.switchLabel}>
                  {t("knowledgeBases.shared")}
                </span>
                <span className={styles.formOptionHint}>
                  {t("knowledgeBases.sharedHint")}
                </span>
              </div>
              <Switch
                size="small"
                checked={sharedChecked}
                onChange={setSharedChecked}
              />
            </div>
          </div>
        </Form>
      </Modal>

      <Drawer
        title={t("knowledgeBases.settingsTitle")}
        placement="right"
        width={isMobile ? "100%" : 520}
        open={featureModalOpen}
        onClose={() => setFeatureModalOpen(false)}
        destroyOnHidden
        footer={
          <div className={styles.drawerFooter}>
            <Button onClick={() => setFeatureModalOpen(false)}>
              {t("common.cancel")}
            </Button>
            <Button
              type="primary"
              disabled={
                featureEnabledDraft
                  ? !featureModel ||
                    (featureBackend === "remote" && !featureProviderId) ||
                    (featureBackend === "onnx" &&
                      !catalog.find((model) => model.id === featureModel)
                        ?.downloaded) ||
                    featureOptionsLoading ||
                    onnxDownloading
                  : false
              }
              onClick={() => void saveFeature()}
            >
              {t("common.save")}
            </Button>
          </div>
        }
      >
        <div className={styles.formOptions}>
          <div className={styles.formOptionRow}>
            <div className={styles.formOptionCopy}>
              <span className={styles.switchLabel}>
                {t("knowledgeBases.settingsOpen")}
              </span>
              <span className={styles.formOptionHint}>
                {t("knowledgeBases.settingsLead")}
              </span>
            </div>
            <Switch
              size="small"
              checked={featureEnabledDraft}
              onChange={setFeatureEnabledDraft}
            />
          </div>
        </div>

        {featureEnabledDraft ? (
          <Spin spinning={featureOptionsLoading}>
            <div className={styles.settingsBody}>
              <div className={styles.settingsFieldLabel}>
                {t("knowledgeBases.selectModel")}
              </div>
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
                  <div className={styles.onnxModelList}>
                    {(
                      remoteProviders.find(
                        (provider) =>
                          provider.provider_id === featureProviderId,
                      )?.models ?? []
                    ).map((model) => {
                      const selected = featureModel === model.id;
                      return (
                        <button
                          key={model.id}
                          type="button"
                          className={`${styles.onnxModelItem}${
                            selected ? ` ${styles.onnxModelItemActive}` : ""
                          }`}
                          onClick={() => setFeatureModel(model.id)}
                        >
                          <span className={styles.onnxModelName}>
                            {model.name}
                          </span>
                        </button>
                      );
                    })}
                    {featureProviderId &&
                    (remoteProviders.find(
                      (provider) => provider.provider_id === featureProviderId,
                    )?.models.length ?? 0) === 0 ? (
                      <Typography.Text
                        type="secondary"
                        className={styles.settingsHint}
                      >
                        {t("knowledgeBases.noModels")}
                      </Typography.Text>
                    ) : null}
                  </div>
                </div>
              ) : (
                <div className={styles.onnxModelList}>
                  {catalog.map((model) => {
                    const selected = featureModel === model.id;
                    const size = formatSizeGb(model.size_gb);
                    const downloading =
                      onnxDownloading && downloadProgressModel === model.id;
                    return (
                      <div
                        key={model.id}
                        className={`${styles.onnxModelItem}${
                          selected ? ` ${styles.onnxModelItemActive}` : ""
                        }`}
                        onClick={() => setFeatureModel(model.id)}
                        onKeyDown={(event) => {
                          if (event.key === "Enter" || event.key === " ") {
                            event.preventDefault();
                            setFeatureModel(model.id);
                          }
                        }}
                        role="button"
                        tabIndex={0}
                      >
                        <div className={styles.onnxModelInfo}>
                          <span className={styles.onnxModelName}>
                            {model.name}
                          </span>
                          <span className={styles.onnxModelMeta}>
                            {model.recommended
                              ? t("knowledgeBases.recommended")
                              : null}
                            {model.recommended ? " · " : null}
                            {size
                              ? t("knowledgeBases.approxSize", { size })
                              : t("knowledgeBases.sizeUnknown")}
                            {model.downloaded
                              ? null
                              : ` · ${t("knowledgeBases.notDownloaded")}`}
                          </span>
                        </div>
                        {model.downloaded ? null : (
                          <Button
                            size="small"
                            icon={<Download size={14} />}
                            loading={downloading}
                            disabled={onnxDownloading && !downloading}
                            onClick={(event) => {
                              event.stopPropagation();
                              setFeatureModel(model.id);
                              void startOnnxDownload(model.id);
                            }}
                          >
                            {t("knowledgeBases.downloadModel")}
                          </Button>
                        )}
                      </div>
                    );
                  })}
                  {catalog.length === 0 ? (
                    <Typography.Text
                      type="secondary"
                      className={styles.settingsHint}
                    >
                      {t("knowledgeBases.noModels")}
                    </Typography.Text>
                  ) : null}
                  {catalog.length > 0 && !onnxExpanded ? (
                    <Button
                      type="link"
                      loading={onnxExpanding}
                      className={styles.showMoreOnnx}
                      onClick={() => void loadEmbeddingOptions(true)}
                    >
                      {t("knowledgeBases.showMoreOnnx")}
                    </Button>
                  ) : null}
                </div>
              )}
              {featureBackend === "onnx" && featureModel ? (
                <div className={styles.onnxReadiness}>
                  <ReadinessRow
                    label={t("knowledgeBases.checkRuntime")}
                    ok={Boolean(capability?.checks.deps_available)}
                    okText={t("knowledgeBases.checkInstalled")}
                    failText={t("knowledgeBases.checkRuntimeMissing")}
                  />
                  <ReadinessRow
                    label={t("knowledgeBases.checkWeights")}
                    ok={Boolean(
                      catalog.find((model) => model.id === featureModel)
                        ?.downloaded,
                    )}
                    okText={t("knowledgeBases.checkDownloaded")}
                    failText={t("knowledgeBases.notDownloaded")}
                  />
                  <div className={styles.onnxReadinessRow}>
                    <span className={styles.onnxReadinessLabel}>
                      {t("knowledgeBases.checkEncode")}
                    </span>
                    {onnxProbe ? (
                      <Typography.Text
                        type={onnxProbe.ok ? "success" : "danger"}
                      >
                        {onnxProbe.ok
                          ? t("knowledgeBases.probeOk", {
                              dim: onnxProbe.dim ?? "?",
                              ms: Math.round(onnxProbe.latency_ms ?? 0),
                            })
                          : onnxProbe.error ?? t("knowledgeBases.probeFailed")}
                      </Typography.Text>
                    ) : (
                      <Typography.Text type="secondary">
                        {t("knowledgeBases.probeIdle")}
                      </Typography.Text>
                    )}
                    <Button
                      type="link"
                      size="small"
                      loading={onnxProbing}
                      onClick={() => void runOnnxProbe()}
                    >
                      {t("knowledgeBases.probeRun")}
                    </Button>
                  </div>
                </div>
              ) : null}
              <Typography.Text type="secondary" className={styles.settingsHint}>
                {t("knowledgeBases.enableDescription")}
              </Typography.Text>
              <Typography.Link onClick={() => navigate("/admin/models")}>
                {t("knowledgeBases.manageModels")}
              </Typography.Link>
            </div>
          </Spin>
        ) : null}
      </Drawer>
      <Modal
        open={downloadProgressOpen}
        title={t("models.localDownloadProgressTitle")}
        onCancel={dismissDownloadProgressToBackground}
        closable
        maskClosable
        destroyOnClose={false}
        footer={
          <Button onClick={dismissDownloadProgressToBackground}>
            {t("models.localDownloadContinueBackground")}
          </Button>
        }
      >
        <div className={styles.downloadProgressLabel}>
          {downloadProgressLabel || downloadProgressModel}
        </div>
        <Progress percent={downloadProgress} status="active" />
        <Typography.Text type="secondary" className={styles.settingsHint}>
          {t("models.localDownloadBackgroundHint")}
        </Typography.Text>
      </Modal>
    </PageShell>
  );
}
