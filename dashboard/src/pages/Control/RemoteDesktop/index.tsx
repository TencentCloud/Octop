import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Alert,
  Button,
  Drawer,
  Modal,
  Result,
  Select,
  Space,
  Tag,
  Tooltip,
  Typography,
  message,
} from "antd";
import {
  CheckCircle2,
  FolderOpen,
  LayoutGrid,
  Maximize2,
  Monitor,
  PlugZap,
  RefreshCw,
  Terminal,
  Trash2,
  Unplug,
  X,
} from "lucide-react";
import { useTranslation } from "react-i18next";

import StreamEdgeControls from "../../../components/StreamEdgeControls/StreamEdgeControls";
import StreamSetupGuide from "../../../components/StreamSetupGuide/StreamSetupGuide";
import PageShell from "../../../layouts/PageShell";
import {
  desktopApi,
  type DesktopStatusResponse,
} from "../../../api/modules/desktop";
import {
  paintBase64JpegToCanvas,
  clearCanvas,
} from "../../../utils/browserCanvas";
import {
  useDesktopStream,
  type DesktopStreamError,
} from "../../../hooks/useDesktopStream";
import { useDesktopCanvasInteraction } from "../../../hooks/useDesktopCanvasInteraction";
import { useIsMobile } from "../../../hooks/useIsMobile";
import { useLandscapeFullscreen } from "../../../hooks/useLandscapeFullscreen";
import { showApiError } from "../../../utils/showApiToast";
import { wsStreamErrorMessage } from "../../../utils/apiError";
import {
  DESKTOP_FPS_PRESETS,
  DESKTOP_RESOLUTION_OPTIONS,
  desktopFpsLabel,
  desktopResolutionLabel,
  isDesktopResolution,
  type DesktopResolution,
} from "../../../utils/desktopViewport";
import { sendDesktopAction } from "./desktopShortcuts";
import styles from "./index.module.less";

const { Text } = Typography;

const RESOLUTION_STORAGE_KEY = "octop:remote-desktop:resolution";
const FPS_STORAGE_KEY = "octop:remote-desktop:max-fps";
const DEFAULT_RESOLUTION: DesktopResolution = "1920x1080";
const DEFAULT_MAX_FPS = 10;

type InstallPhase =
  | "idle"
  | "installing"
  | "install_success"
  | "install_failed";

export default function RemoteDesktopPage() {
  const { t } = useTranslation();
  const isMobile = useIsMobile();
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const installAbortRef = useRef<AbortController | null>(null);
  const uninstallAbortRef = useRef<AbortController | null>(null);
  const installLogRef = useRef<HTMLDivElement | null>(null);

  const [envStatus, setEnvStatus] = useState<DesktopStatusResponse | null>(
    null,
  );
  const [envLoading, setEnvLoading] = useState(false);
  const [envModalOpen, setEnvModalOpen] = useState(false);
  const [controlsOpen, setControlsOpen] = useState(false);
  const openControlsDrawer = useCallback(() => setControlsOpen(true), []);
  const closeControlsDrawer = useCallback(() => setControlsOpen(false), []);
  const [installPhase, setInstallPhase] = useState<InstallPhase>("idle");
  const [installLogs, setInstallLogs] = useState<string[]>([]);
  const [uninstalling, setUninstalling] = useState(false);
  const [uninstallLogs, setUninstallLogs] = useState<string[]>([]);
  const [screenSize, setScreenSize] = useState({ width: 1920, height: 1080 });
  const screenSizeRef = useRef({ width: 1920, height: 1080 });
  const [resolution, setResolution] = useState<DesktopResolution>(() => {
    try {
      const saved = localStorage.getItem(RESOLUTION_STORAGE_KEY);
      if (saved && isDesktopResolution(saved)) return saved;
    } catch {
      // ignore
    }
    return DEFAULT_RESOLUTION;
  });
  const [maxFps, setMaxFps] = useState<number>(() => {
    try {
      const saved = localStorage.getItem(FPS_STORAGE_KEY);
      if (saved) {
        const n = Number(saved);
        if (DESKTOP_FPS_PRESETS.some((v) => v === n)) return n;
      }
    } catch {
      // ignore
    }
    return DEFAULT_MAX_FPS;
  });
  const [geometryBusy, setGeometryBusy] = useState(false);
  const [frameReady, setFrameReady] = useState(false);
  const { status, connect, sendEvent, disconnect } = useDesktopStream();

  const envReady = envStatus?.setup_state === "ready" && envStatus.ok;
  const canUninstall =
    Boolean(envStatus) &&
    envStatus?.setup_state !== "deps_missing" &&
    envStatus?.setup_state !== "unsupported";
  const isStreaming =
    status === "streaming" ||
    status === "connecting" ||
    status === "reconnecting";
  const showStream = isStreaming;
  const showEdgeControls = status === "streaming" && frameReady;

  useEffect(() => {
    if (status === "connecting" || status === "reconnecting") {
      setFrameReady(false);
      clearCanvas(canvasRef.current);
    } else if (
      status === "idle" ||
      status === "stopped" ||
      status === "error"
    ) {
      setFrameReady(false);
      clearCanvas(canvasRef.current);
    }
  }, [status]);

  const requireStream = useCallback(() => {
    if (status === "streaming") return true;
    message.info(t("remoteDesktop.shortcutsNeedConnect", "请先连接远程桌面"));
    return false;
  }, [status, t]);

  const refreshEnv = useCallback(async () => {
    setEnvLoading(true);
    try {
      const data = await desktopApi.status();
      setEnvStatus(data);
      return data;
    } catch (err) {
      showApiError(
        err,
        t("remoteDesktop.statusFailed", "获取远程桌面状态失败"),
        t,
      );
      return null;
    } finally {
      setEnvLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void refreshEnv();
  }, [refreshEnv]);

  useEffect(() => {
    if (installLogRef.current) {
      installLogRef.current.scrollTop = installLogRef.current.scrollHeight;
    }
  }, [installLogs]);

  useEffect(
    () => () => {
      installAbortRef.current?.abort();
      uninstallAbortRef.current?.abort();
    },
    [],
  );

  const startInstall = useCallback(() => {
    setInstallPhase("installing");
    setInstallLogs([]);
    setEnvModalOpen(false);
    installAbortRef.current = desktopApi.installDesktop(
      (line) => setInstallLogs((prev) => [...prev, line]),
      (success) => {
        installAbortRef.current = null;
        if (!success) {
          setInstallPhase("install_failed");
          setEnvModalOpen(true);
          return;
        }
        setInstallPhase("idle");
        setEnvModalOpen(false);
        void refreshEnv();
        message.success(t("remoteDesktop.installSuccess", "桌面环境已就绪"));
      },
    );
  }, [refreshEnv, t]);

  const handleUninstall = useCallback(() => {
    if (!canUninstall || uninstalling) return;
    const confirmText = envStatus?.native_capture
      ? t(
          "remoteDesktop.uninstallConfirmNative",
          "将移除远程桌面所需的 Python 组件，是否继续？",
        )
      : t(
          "remoteDesktop.uninstallConfirmLinux",
          "将停止虚拟桌面服务并移除已安装组件，是否继续？",
        );
    Modal.confirm({
      title: t("remoteDesktop.uninstallTitle", "卸载远程桌面"),
      content: confirmText,
      okText: t("remoteDesktop.uninstall", "卸载"),
      okButtonProps: { danger: true },
      cancelText: t("common.cancel"),
      onOk: () =>
        new Promise<void>((resolve, reject) => {
          if (isStreaming) {
            disconnect();
          }
          setUninstalling(true);
          setUninstallLogs([]);
          const hide = message.loading(
            t("remoteDesktop.uninstalling", "正在卸载…"),
            0,
          );
          uninstallAbortRef.current = desktopApi.uninstallDesktop(
            (line) => setUninstallLogs((prev) => [...prev, line]),
            (success) => {
              uninstallAbortRef.current = null;
              setUninstalling(false);
              hide();
              void refreshEnv().then((data) => {
                const removed =
                  success ||
                  data?.setup_state === "deps_missing" ||
                  data?.setup_state === "needs_install";
                if (removed) {
                  setUninstallLogs([]);
                  message.success(
                    t("remoteDesktop.uninstallSuccess", "远程桌面已卸载"),
                  );
                  resolve();
                  return;
                }
                message.error(t("remoteDesktop.uninstallFailed", "卸载失败"));
                reject(new Error("uninstall failed"));
              });
            },
          );
        }),
    });
  }, [
    canUninstall,
    disconnect,
    envStatus?.native_capture,
    isStreaming,
    refreshEnv,
    t,
    uninstalling,
  ]);

  const openEnvModal = useCallback(() => {
    setEnvModalOpen(true);
    if (installPhase !== "installing") {
      setInstallPhase("idle");
      setInstallLogs([]);
    }
    void refreshEnv();
  }, [installPhase, refreshEnv]);

  const closeEnvModal = useCallback(() => {
    if (installPhase === "installing") {
      installAbortRef.current?.abort();
      installAbortRef.current = null;
      setInstallPhase("idle");
    }
    setEnvModalOpen(false);
    if (
      installPhase === "install_success" ||
      installPhase === "install_failed"
    ) {
      void refreshEnv();
    }
  }, [installPhase, refreshEnv]);

  useEffect(() => {
    if (envStatus?.geometry && isDesktopResolution(envStatus.geometry)) {
      setResolution(envStatus.geometry);
    }
  }, [envStatus?.geometry]);

  const streamCallbacks = useCallback(
    () => ({
      onFrame: (data: string, width: number, height: number) => {
        setFrameReady(true);
        if (width > 0 && height > 0) {
          const prev = screenSizeRef.current;
          if (prev.width !== width || prev.height !== height) {
            screenSizeRef.current = { width, height };
            setScreenSize({ width, height });
          }
        }
        paintBase64JpegToCanvas(canvasRef.current, data);
      },
      onError: (err: DesktopStreamError) =>
        message.error(
          wsStreamErrorMessage(
            err,
            t("remoteDesktop.streamError", "远程桌面连接失败"),
            t,
          ),
        ),
      onActionResult: ({ ok }: { ok: boolean }) => {
        if (!ok) {
          message.error(t("remoteDesktop.shortcutFailed", "快捷操作发送失败"));
        }
      },
    }),
    [t],
  );

  const startStream = useCallback(() => {
    connect(streamCallbacks(), { quality: 80, maxFps });
  }, [connect, maxFps, streamCallbacks]);

  const applyResolution = useCallback(
    async (value: DesktopResolution) => {
      setResolution(value);
      try {
        localStorage.setItem(RESOLUTION_STORAGE_KEY, value);
      } catch {
        // ignore
      }
      if (envStatus?.platform !== "linux") return;
      setGeometryBusy(true);
      try {
        await desktopApi.setGeometry(value);
        await refreshEnv();
        if (isStreaming) startStream();
      } catch (err) {
        showApiError(
          err,
          t("remoteDesktop.geometryFailed", "切换分辨率失败"),
          t,
        );
      } finally {
        setGeometryBusy(false);
      }
    },
    [envStatus?.platform, isStreaming, refreshEnv, startStream, t],
  );

  const handleResolutionChange = useCallback(
    (value: DesktopResolution) => {
      if (envStatus?.platform === "linux" && isStreaming) {
        Modal.confirm({
          title: t("remoteDesktop.geometryRestartTitle", "切换分辨率"),
          content: t(
            "remoteDesktop.geometryRestartWarning",
            "将重启虚拟桌面，当前连接会短暂中断。",
          ),
          okText: t("common.confirm", "确定"),
          cancelText: t("common.cancel", "取消"),
          onOk: () => applyResolution(value),
        });
        return;
      }
      void applyResolution(value);
    },
    [applyResolution, envStatus?.platform, isStreaming, t],
  );

  const handleFpsChange = useCallback(
    (fps: number) => {
      setMaxFps(fps);
      try {
        localStorage.setItem(FPS_STORAGE_KEY, String(fps));
      } catch {
        // ignore
      }
      if (isStreaming) {
        connect(streamCallbacks(), { quality: 80, maxFps: fps });
      }
    },
    [connect, isStreaming, streamCallbacks],
  );

  const handleEvent = useCallback(
    (event: Record<string, unknown>) => {
      sendEvent(event);
    },
    [sendEvent],
  );

  const interaction = useDesktopCanvasInteraction({
    enabled: status === "streaming" && frameReady,
    canvasRef,
    screenWidth: screenSize.width,
    screenHeight: screenSize.height,
    onEvent: handleEvent,
  });

  const handleConnect = useCallback(() => {
    if (!envReady) {
      openEnvModal();
      return;
    }
    startStream();
  }, [envReady, openEnvModal, startStream]);

  const handleDisconnect = useCallback(() => {
    disconnect();
    clearCanvas(canvasRef.current);
  }, [disconnect]);

  const handleRefreshStream = useCallback(() => {
    if (!requireStream()) return;
    startStream();
    message.success(t("remoteDesktop.refreshStreamDone", "画面已刷新"));
  }, [requireStream, startStream, t]);

  const handleFullscreen = useLandscapeFullscreen(viewportRef, {
    isMobile,
    onError: () =>
      message.error(t("remoteDesktop.fullscreenFailed", "无法进入全屏")),
  });

  const runShortcut = useCallback(
    (action: Parameters<typeof sendDesktopAction>[1]) => {
      if (!requireStream()) return;
      if (!sendDesktopAction(sendEvent, action)) {
        message.error(t("remoteDesktop.shortcutFailed", "快捷操作发送失败"));
      }
    },
    [requireStream, sendEvent, t],
  );

  const handleShowDesktop = useCallback(() => {
    runShortcut("show_desktop");
  }, [runShortcut]);

  const handleOpenMenu = useCallback(() => {
    runShortcut("open_menu");
  }, [runShortcut]);

  const handleOpenTerminal = useCallback(() => {
    runShortcut("open_terminal");
  }, [runShortcut]);

  const handleOpenFiles = useCallback(() => {
    runShortcut("open_files");
  }, [runShortcut]);

  const handleCloseWindow = useCallback(() => {
    runShortcut("close_window");
  }, [runShortcut]);

  type ShortcutTone =
    | "blue"
    | "emerald"
    | "violet"
    | "amber"
    | "rose"
    | "orange";

  const shortcutIconToneClass: Record<ShortcutTone, string> = {
    blue: styles.shortcutIconBlue,
    emerald: styles.shortcutIconEmerald,
    violet: styles.shortcutIconViolet,
    amber: styles.shortcutIconAmber,
    rose: styles.shortcutIconRose,
    orange: styles.shortcutIconOrange,
  };

  const shortcutItems = useMemo(
    () => [
      {
        id: "showDesktop",
        label: t("remoteDesktop.showDesktop", "进入桌面"),
        icon: LayoutGrid,
        tone: "blue" as const,
        onClick: handleShowDesktop,
      },
      {
        id: "openTerminal",
        label: t("remoteDesktop.openTerminal", "终端"),
        icon: Terminal,
        tone: "emerald" as const,
        onClick: handleOpenTerminal,
      },
      {
        id: "openMenu",
        label: t("remoteDesktop.openMenu", "开始菜单"),
        icon: Monitor,
        tone: "violet" as const,
        onClick: handleOpenMenu,
      },
      {
        id: "openFiles",
        label: t("remoteDesktop.openFiles", "文件管理"),
        icon: FolderOpen,
        tone: "amber" as const,
        onClick: handleOpenFiles,
      },
      {
        id: "closeWindow",
        label: t("remoteDesktop.closeWindow", "关闭窗口"),
        icon: X,
        tone: "rose" as const,
        onClick: handleCloseWindow,
      },
      {
        id: "refreshStream",
        label: t("remoteDesktop.refreshStream", "刷新画面"),
        icon: RefreshCw,
        tone: "orange" as const,
        onClick: handleRefreshStream,
        disabled: !isStreaming,
      },
    ],
    [
      t,
      handleShowDesktop,
      handleOpenTerminal,
      handleOpenMenu,
      handleOpenFiles,
      handleCloseWindow,
      handleRefreshStream,
      isStreaming,
    ],
  );

  const renderControlsContent = () => (
    <div className={styles.drawerContent}>
      <div className={styles.settingsCard}>
        <div className={styles.settingsCardHeader}>
          <span className={styles.settingsCardTitle}>
            {t("remoteDesktop.streamSettings", "推流设置")}
          </span>
          {isStreaming ? (
            <Tag color="success" style={{ margin: 0 }}>
              {status === "streaming"
                ? t("remoteDesktop.streaming", "推流中")
                : status === "reconnecting"
                ? t("remoteDesktop.reconnecting", "重连中")
                : t("remoteDesktop.connecting", "连接中")}
            </Tag>
          ) : (
            <Tag style={{ margin: 0 }}>{t("remoteDesktop.idle", "未连接")}</Tag>
          )}
        </div>
        <div className={styles.settingsGrid}>
          {envStatus?.platform === "linux" ? (
            <div className={styles.settingItem}>
              <span className={styles.settingLabel}>
                {t("remoteDesktop.resolution", "分辨率")}
              </span>
              <Select
                size="middle"
                className={styles.settingSelectFull}
                value={resolution}
                disabled={geometryBusy}
                onChange={(v) => handleResolutionChange(v)}
                options={DESKTOP_RESOLUTION_OPTIONS.map((o) => ({
                  value: o.value,
                  label: desktopResolutionLabel(o.value),
                }))}
              />
            </div>
          ) : null}
          <div className={styles.settingItem}>
            <span className={styles.settingLabel}>
              {t("remoteDesktop.streamFps", "帧率")}
            </span>
            <Select
              size="middle"
              className={styles.settingSelectFull}
              value={maxFps}
              onChange={handleFpsChange}
              options={DESKTOP_FPS_PRESETS.map((fps) => ({
                value: fps,
                label: desktopFpsLabel(fps),
              }))}
            />
          </div>
        </div>
      </div>

      {isMobile && (
        <Button
          block
          icon={<Maximize2 size={14} />}
          onClick={() => {
            closeControlsDrawer();
            void handleFullscreen();
          }}
        >
          {t("remoteDesktop.fullscreen", "全屏")}
        </Button>
      )}

      <div className={styles.shortcutsCard}>
        <div className={styles.shortcutsCardHeader}>
          <span className={styles.shortcutsTitle}>
            {t("remoteDesktop.shortcuts", "快捷操作")}
          </span>
        </div>
        <div className={styles.shortcutsList}>
          {shortcutItems.map((item) => {
            const Icon = item.icon;
            return (
              <button
                key={item.id}
                type="button"
                className={styles.shortcutRow}
                onClick={item.onClick}
                disabled={item.disabled}
              >
                <span
                  className={`${styles.shortcutIcon} ${
                    shortcutIconToneClass[item.tone]
                  }`}
                >
                  <Icon size={16} strokeWidth={2} />
                </span>
                <span className={styles.shortcutLabel}>{item.label}</span>
              </button>
            );
          })}
        </div>
        <p className={styles.hintText}>
          {t(
            "remoteDesktop.mobileHint",
            "点击画面可操控远程桌面；快捷按钮会发送常用快捷键。",
          )}
        </p>
      </div>
    </div>
  );

  const cancelInstall = useCallback(() => {
    installAbortRef.current?.abort();
    installAbortRef.current = null;
    setInstallPhase("idle");
    setInstallLogs([]);
    message.info(
      t(
        "remoteDesktop.installCancelHint",
        "已取消安装请求，服务端可能仍在继续安装，请稍后刷新状态。",
      ),
    );
  }, [t]);

  const renderInstallLog = (maxHeight?: number, extraClass?: string) => (
    <div
      ref={installLogRef}
      className={`${styles.installLog} ${extraClass ?? ""}`}
      style={maxHeight !== undefined ? { maxHeight } : undefined}
    >
      {installLogs.length === 0 ? (
        <div>{t("remoteDesktop.installing", "正在启动安装...")}</div>
      ) : (
        installLogs.map((line, i) => <div key={i}>{line}</div>)
      )}
    </div>
  );

  const renderViewportUninstallProgress = () => (
    <div className={styles.installProgress}>
      <RefreshCw size={32} className={styles.streamLoadingIcon} />
      <div className={styles.installProgressTitle}>
        {t("remoteDesktop.uninstalling", "正在卸载…")}
      </div>
      <div className={styles.installLog}>
        {uninstallLogs.length === 0 ? (
          <div>{t("remoteDesktop.uninstalling", "正在卸载…")}</div>
        ) : (
          uninstallLogs.map((line, i) => <div key={i}>{line}</div>)
        )}
      </div>
    </div>
  );

  const renderViewportInstallProgress = () => (
    <div className={styles.installProgress}>
      <RefreshCw size={32} className={styles.streamLoadingIcon} />
      <div className={styles.installProgressTitle}>
        {t("remoteDesktop.installProgress", "正在安装中…")}
      </div>
      {renderInstallLog()}
      <div className={styles.installProgressActions}>
        <Button onClick={cancelInstall}>{t("common.cancel")}</Button>
      </div>
    </div>
  );

  const renderEnvModalContent = () => {
    if (envLoading && installPhase === "idle") {
      return (
        <div style={{ textAlign: "center", padding: 24 }}>
          {t("remoteDesktop.checking", "正在检测桌面环境...")}
        </div>
      );
    }

    if (installPhase === "installing") {
      return (
        <Space direction="vertical" size="middle" style={{ width: "100%" }}>
          <Alert
            type="warning"
            showIcon
            message={t("remoteDesktop.resourceWarningTitle", "资源占用提示")}
            description={t("remoteDesktop.resourceWarningDesc")}
          />
          {renderInstallLog()}
        </Space>
      );
    }

    if (installPhase === "install_success") {
      return (
        <Result
          icon={
            <CheckCircle2 size={40} color="var(--fn-color-success,#52c41a)" />
          }
          title={t("remoteDesktop.installSuccess", "桌面环境已就绪")}
          subTitle={t("remoteDesktop.installSuccessHint")}
          style={{ padding: "8px 0" }}
        />
      );
    }

    if (installPhase === "install_failed") {
      return (
        <Space direction="vertical" size="middle" style={{ width: "100%" }}>
          <Result
            icon={<Terminal size={40} color="var(--fn-color-error,#ff4d4f)" />}
            title={t("remoteDesktop.installFailed", "安装失败")}
            subTitle={t("remoteDesktop.installFailedHint")}
            style={{ padding: "8px 0" }}
          />
          {installLogs.length > 0 && (
            <details open>
              <summary
                style={{
                  cursor: "pointer",
                  fontSize: 12,
                  color: "var(--fn-text-tertiary)",
                }}
              >
                {t("remoteDesktop.installLog", "安装日志")}
              </summary>
              {renderInstallLog(160, styles.installLogCompact)}
            </details>
          )}
        </Space>
      );
    }

    if (envReady) {
      return (
        <Space direction="vertical" size="middle" style={{ width: "100%" }}>
          <Result
            icon={
              <CheckCircle2 size={40} color="var(--fn-color-success,#52c41a)" />
            }
            title={t("remoteDesktop.envReady", "桌面环境已就绪")}
            subTitle={
              envStatus?.display
                ? t("remoteDesktop.displayReady", {
                    display: envStatus.display,
                  })
                : undefined
            }
            style={{ padding: "8px 0" }}
          />
          <Alert
            type="info"
            showIcon
            message={t("remoteDesktop.resourceInfoTitle", "关于资源占用")}
            description={t("remoteDesktop.resourceInfoDesc")}
          />
        </Space>
      );
    }

    return (
      <Space direction="vertical" size="middle" style={{ width: "100%" }}>
        <Alert
          type="warning"
          showIcon
          message={t("remoteDesktop.resourceWarningTitle", "资源占用提示")}
          description={t("remoteDesktop.resourceWarningDesc")}
        />
      </Space>
    );
  };

  const envModalFooter = () => {
    if (installPhase === "installing") {
      return <Button onClick={closeEnvModal}>{t("common.cancel")}</Button>;
    }
    if (installPhase === "install_failed") {
      return (
        <Space>
          <Button onClick={closeEnvModal}>{t("common.close")}</Button>
          <Button type="primary" onClick={startInstall}>
            {t("remoteDesktop.installRetry", "重新安装")}
          </Button>
        </Space>
      );
    }
    if (installPhase === "install_success") {
      return (
        <Button type="primary" onClick={closeEnvModal}>
          {t("common.close")}
        </Button>
      );
    }
    if (!envReady) {
      return (
        <Space>
          <Button onClick={closeEnvModal}>{t("common.close")}</Button>
          <Button type="primary" onClick={startInstall}>
            {t("remoteDesktop.install", "安装桌面环境")}
          </Button>
        </Space>
      );
    }
    return (
      <Button type="primary" onClick={closeEnvModal}>
        {t("common.close")}
      </Button>
    );
  };

  const headerActions = (
    <Space size={8} wrap>
      <Tooltip title={t("remoteDesktop.checkInstallTip")}>
        <Button
          size={isMobile ? "small" : "middle"}
          icon={<Monitor size={14} />}
          onClick={openEnvModal}
          type={envReady ? "default" : "primary"}
        >
          {t("remoteDesktop.checkInstallShort", "检查")}
          {envReady && !envLoading && (
            <CheckCircle2
              size={14}
              style={{
                marginLeft: 4,
                color: "var(--fn-color-success,#52c41a)",
              }}
            />
          )}
        </Button>
      </Tooltip>
      {!isStreaming ? (
        <Tooltip
          title={envReady ? undefined : t("remoteDesktop.connectDisabled")}
        >
          <Button
            size={isMobile ? "small" : "middle"}
            type="primary"
            icon={<PlugZap size={14} />}
            onClick={handleConnect}
            disabled={!envReady}
            aria-label={t("remoteDesktop.connect", "连接")}
          >
            {!isMobile && t("remoteDesktop.connect", "连接")}
          </Button>
        </Tooltip>
      ) : (
        <Tooltip title={t("remoteDesktop.disconnect", "断开")}>
          <Button
            size={isMobile ? "small" : "middle"}
            danger
            icon={<Unplug size={14} />}
            onClick={handleDisconnect}
            aria-label={t("remoteDesktop.disconnect", "断开")}
          >
            {!isMobile && t("remoteDesktop.disconnect", "断开")}
          </Button>
        </Tooltip>
      )}
    </Space>
  );

  return (
    <PageShell
      title={t("nav.remoteDesktop", "远程桌面")}
      subtitle={t(
        "pageShell.desktop.subtitle",
        "查看并操控 Octop 主机操作系统桌面",
      )}
      fill
      actions={headerActions}
    >
      <Modal
        title={t("remoteDesktop.checkInstall", "检测桌面")}
        open={envModalOpen}
        onCancel={closeEnvModal}
        footer={envModalFooter()}
        width={isMobile ? "100%" : 560}
        style={isMobile ? { top: 20, maxWidth: "100vw" } : undefined}
        destroyOnClose
        maskClosable={installPhase !== "installing"}
      >
        {renderEnvModalContent()}
      </Modal>

      <div className={styles.remoteDesktopPage}>
        {envReady &&
          !showStream &&
          envStatus?.platform === "darwin" &&
          envStatus.permissions_needed.length > 0 && (
            <Alert
              type="info"
              showIcon
              message={t(
                "remoteDesktop.macPermissionsTitle",
                "需要 macOS 系统权限",
              )}
              description={t("remoteDesktop.macPermissionsDesc", {
                permissions: envStatus.permissions_needed
                  .map((p) =>
                    p === "screen_recording"
                      ? t("remoteDesktop.permScreenRecording", "屏幕录制")
                      : p === "accessibility"
                      ? t("remoteDesktop.permAccessibility", "辅助功能")
                      : p,
                  )
                  .join(t("remoteDesktop.permJoin", "、")),
              })}
            />
          )}
        {envReady && !showStream && envStatus?.native_capture && (
          <Alert
            type="success"
            showIcon
            message={t("remoteDesktop.nativeReadyTitle", "本机桌面已就绪")}
            description={t(
              "remoteDesktop.nativeReadyDesc",
              "将直接捕获本机屏幕并注入键鼠，无需安装虚拟桌面。",
            )}
          />
        )}
        <div
          ref={viewportRef}
          className={`${styles.viewport} ${
            isMobile ? styles.viewportMobile : ""
          }`}
        >
          {!showStream ? (
            installPhase === "installing" ? (
              renderViewportInstallProgress()
            ) : uninstalling ? (
              renderViewportUninstallProgress()
            ) : (
              <StreamSetupGuide
                icon={<Monitor size={48} strokeWidth={1.5} />}
                title={
                  envReady
                    ? t("remoteDesktop.connectTitle", "连接远程桌面")
                    : t("remoteDesktop.subtitle", "控制 Octop 主机操作系统桌面")
                }
                description={
                  envReady
                    ? t(
                        "remoteDesktop.connectIdleDesc",
                        "点击下方「连接」开始实时操控主机桌面",
                      )
                    : t(
                        "remoteDesktop.setupDesc",
                        "按以下步骤完成环境配置，即可在浏览器中远程操控主机桌面",
                      )
                }
                steps={
                  envReady
                    ? [
                        {
                          label: t(
                            "remoteDesktop.idleStep1",
                            "点击「连接」建立远程桌面会话",
                          ),
                        },
                        {
                          label: t(
                            "remoteDesktop.idleStep2",
                            "在画面中点击、拖动与输入，即可操控远程桌面",
                          ),
                        },
                      ]
                    : [
                        {
                          label: t(
                            "remoteDesktop.setupStep1",
                            "点击「检查」，检测 Python 依赖与桌面环境状态",
                          ),
                        },
                        {
                          label: t(
                            "remoteDesktop.setupStep2",
                            "若未安装，在弹窗中按引导完成安装（Linux 无图形服务器可一键搭建虚拟桌面）",
                          ),
                        },
                        {
                          label: t(
                            "remoteDesktop.setupStep3",
                            "环境就绪后，点击「连接」开始实时看屏与键鼠操控",
                          ),
                        },
                      ]
                }
                primaryAction={
                  envReady
                    ? {
                        label: t("remoteDesktop.connect", "连接"),
                        onClick: handleConnect,
                        icon: <PlugZap size={14} />,
                      }
                    : {
                        label: t("remoteDesktop.checkInstallShort", "检查"),
                        onClick: openEnvModal,
                        icon: <Monitor size={14} />,
                      }
                }
                secondaryAction={
                  envReady && canUninstall
                    ? {
                        label: t("remoteDesktop.uninstall", "卸载"),
                        onClick: handleUninstall,
                        icon: <Trash2 size={14} />,
                        loading: uninstalling,
                        disabled: uninstalling || envLoading,
                        danger: true,
                      }
                    : undefined
                }
              />
            )
          ) : (
            <div className={styles.streamSurface}>
              {isStreaming && !frameReady && (
                <div className={styles.streamLoading}>
                  <RefreshCw size={28} className={styles.streamLoadingIcon} />
                  <Text type="secondary">
                    {status === "connecting"
                      ? t("remoteDesktop.connecting", "连接中")
                      : status === "reconnecting"
                      ? t("remoteDesktop.reconnecting", "重连中")
                      : t("remoteDesktop.waitingFrame", "等待画面…")}
                  </Text>
                </div>
              )}
              {isStreaming && frameReady && (
                <div className={styles.viewportOverlay}>
                  <Tag color="green" style={{ margin: 0, fontSize: 11 }}>
                    {status === "streaming"
                      ? t("remoteDesktop.streaming", "推流中")
                      : t("remoteDesktop.connecting", "连接中")}
                  </Tag>
                </div>
              )}
              <StreamEdgeControls
                visible={showEdgeControls}
                isMobile={isMobile}
                fullscreenLabel={t("remoteDesktop.fullscreen", "全屏")}
                controlsLabel={t(
                  "remoteDesktop.openControls",
                  "控制与快捷操作",
                )}
                onFullscreen={() => void handleFullscreen()}
                onOpenControls={openControlsDrawer}
              />
              <canvas
                ref={canvasRef}
                className={`${styles.canvas} ${
                  isMobile ? styles.canvasMobile : ""
                } ${!frameReady ? styles.canvasHidden : ""}`}
                onPointerDown={interaction.onPointerDown}
                onDoubleClick={interaction.onDoubleClick}
                onContextMenu={interaction.onContextMenu}
                onWheel={interaction.onWheel}
                onKeyDown={interaction.onKeyDown}
                onKeyUp={interaction.onKeyUp}
                {...interaction.canvasProps}
              />
            </div>
          )}
        </div>
      </div>

      <Drawer
        title={t("remoteDesktop.controlsTitle", "控制面板")}
        placement={isMobile ? "bottom" : "right"}
        open={controlsOpen}
        onClose={closeControlsDrawer}
        width={isMobile ? "100%" : 360}
        height={isMobile ? "min(75vh, 560px)" : undefined}
        destroyOnClose={false}
        styles={{ body: { padding: "12px 16px 16px" } }}
      >
        {renderControlsContent()}
      </Drawer>
    </PageShell>
  );
}
