import {
  Fragment,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type {
  KeyboardEvent as ReactKeyboardEvent,
  MouseEvent as ReactMouseEvent,
  ReactNode,
} from "react";
import { Alert, Button, Select, Space, Spin, Tooltip } from "antd";
import { message } from "@/utils/antdMessage";
import {
  Bot,
  Camera,
  Circle,
  Cpu,
  Download,
  HardDrive,
  MonitorSmartphone,
  PlugZap,
  Power,
  RefreshCw,
  RotateCw,
  Smartphone,
  Square,
  TerminalSquare,
  Triangle,
  Unplug,
  Volume1,
  Volume2,
} from "lucide-react";
import { useTranslation } from "react-i18next";

import ForbiddenPage from "../../../components/ForbiddenPage";
import MobileAiPanel from "../../../components/MobileAiPanel";
import StreamConnectingIndicator from "../../../components/StreamConnectingIndicator";
import PageShell from "../../../layouts/PageShell";
import { usePathTabs } from "../../../hooks/usePathTabs";
import {
  mobileApi,
  type MobileDeviceInfo,
  type MobileStatusResponse,
} from "../../../api/modules/mobile";
import {
  paintBase64JpegToCanvas,
  clearCanvas,
} from "../../../utils/browserCanvas";
import { useMobileStream } from "../../../hooks/useMobileStream";
import { useCanvasRemotePointer } from "../../../hooks/useCanvasRemotePointer";
import { useCurrentUser } from "../../../hooks/useCurrentUser";
import { useIsMobile } from "../../../hooks/useIsMobile";
import { useAgent } from "../../../context/AgentContext";
import { userCan } from "../../../utils/permissions";
import { showApiError } from "../../../utils/showApiToast";
import AdbShellPanel from "./AdbShellPanel";
import RemotePhoneIdleGuide from "./RemotePhoneIdleGuide";
import styles from "./index.module.less";

export type RemotePhoneViewTab = "screen" | "shell";

const REMOTE_PHONE_VIEW_TABS = [
  "screen",
  "shell",
] as const satisfies readonly RemotePhoneViewTab[];

const PHONE_TAB_ICONS = {
  screen: Smartphone,
  shell: TerminalSquare,
} as const;

const MOBILE_AI_PANEL_KEY = "octop:remote-phone:ai-panel-open";
const MOBILE_AI_PANEL_WIDTH_KEY = "octop:remote-phone:ai-panel-width";
const MOBILE_AI_PANEL_HEIGHT_KEY = "octop:remote-phone:ai-panel-height";
const MOBILE_AI_PANEL_MIN_WIDTH = 260;
const MOBILE_AI_PANEL_MAX_WIDTH = 620;
const MOBILE_AI_PANEL_MIN_HEIGHT = 200;
const MOBILE_AI_PANEL_MAX_HEIGHT = 520;
const SHELL_SPLIT_WIDTH_KEY = "octop:remote-phone:shell-split-width";
const SHELL_SPLIT_MIN_WIDTH = 280;
const SHELL_SPLIT_MAX_WIDTH = 720;
const SHELL_SPLIT_DEFAULT_WIDTH = 420;
const SHELL_PANEL_OPEN_KEY = "octop:remote-phone:shell-panel-open";
const STREAM_QUALITY_KEY = "octop:remote-phone:stream-quality";

type StreamQualityPreset = "low" | "balanced" | "high" | "max";

const STREAM_QUALITY_PRESETS: Record<
  StreamQualityPreset,
  { quality: number; maxSide: number; maxFps: number }
> = {
  low: { quality: 55, maxSide: 720, maxFps: 8 },
  balanced: { quality: 75, maxSide: 1080, maxFps: 10 },
  high: { quality: 85, maxSide: 1440, maxFps: 12 },
  max: { quality: 90, maxSide: 0, maxFps: 10 },
};

function loadStreamQuality(): StreamQualityPreset {
  try {
    const saved = localStorage.getItem(STREAM_QUALITY_KEY);
    if (
      saved === "low" ||
      saved === "balanced" ||
      saved === "high" ||
      saved === "max"
    ) {
      return saved;
    }
  } catch {
    /* ignore */
  }
  return "balanced";
}

type RailKey =
  | "power"
  | "volume_up"
  | "volume_down"
  | "back"
  | "home"
  | "recents";

type RemoteAndroidPageProps = {
  /** Skip PageShell when mounted inside chat dock / remote-desktop hub. */
  embedded?: boolean;
  /** When false (hidden hub tab), pause the live stream. */
  isVisible?: boolean;
};

export default function RemoteAndroidPage({
  embedded = false,
  isVisible = true,
}: RemoteAndroidPageProps) {
  const { t } = useTranslation();
  const isMobile = useIsMobile();
  const {
    activeTab: activePhoneTab,
    handleTabChange: handlePhoneTabChange,
    isMounted: isPhoneTabMounted,
  } = usePathTabs({
    basePath: "/remote-desktop/phone",
    tabs: REMOTE_PHONE_VIEW_TABS,
    storageKey: "octop:remote-phone:view-tab",
    defaultTab: "screen",
  });
  const { activeAgent, activeAgentId, agents } = useAgent();
  const user = useCurrentUser();
  const canMobile = userCan(user, "mobile");
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const streamDesiredRef = useRef(false);
  const installAbortRef = useRef<AbortController | null>(null);
  const installLogRef = useRef<HTMLDivElement | null>(null);
  const [installPhase, setInstallPhase] = useState<
    "idle" | "installing" | "success" | "failed"
  >("idle");
  const [installLogs, setInstallLogs] = useState<string[]>([]);
  const [statusData, setStatusData] = useState<MobileStatusResponse | null>(
    null,
  );
  const [loading, setLoading] = useState(false);
  const [device, setDevice] = useState<string>("");
  const [frameReady, setFrameReady] = useState(false);
  const [streamSize, setStreamSize] = useState({ width: 0, height: 0 });
  const [deviceInfo, setDeviceInfo] = useState<MobileDeviceInfo | null>(null);
  const [deviceInfoLoading, setDeviceInfoLoading] = useState(false);
  const [streamQuality, setStreamQuality] =
    useState<StreamQualityPreset>(loadStreamQuality);
  const [isAiPanelOpen, setIsAiPanelOpen] = useState(() => {
    try {
      return localStorage.getItem(MOBILE_AI_PANEL_KEY) === "true";
    } catch {
      return false;
    }
  });
  const [aiPanelWidth, setAiPanelWidth] = useState(() => {
    try {
      const saved = localStorage.getItem(MOBILE_AI_PANEL_WIDTH_KEY);
      const n = saved ? Number(saved) : 340;
      if (Number.isFinite(n)) {
        return Math.min(
          Math.max(n, MOBILE_AI_PANEL_MIN_WIDTH),
          MOBILE_AI_PANEL_MAX_WIDTH,
        );
      }
    } catch {
      /* ignore */
    }
    return 340;
  });
  const [aiPanelHeight, setAiPanelHeight] = useState(() => {
    try {
      const saved = localStorage.getItem(MOBILE_AI_PANEL_HEIGHT_KEY);
      const n = saved ? Number(saved) : 320;
      if (Number.isFinite(n)) {
        return Math.min(
          Math.max(n, MOBILE_AI_PANEL_MIN_HEIGHT),
          MOBILE_AI_PANEL_MAX_HEIGHT,
        );
      }
    } catch {
      /* ignore */
    }
    return 320;
  });
  const [shellSplitWidth, setShellSplitWidth] = useState(() => {
    try {
      const saved = localStorage.getItem(SHELL_SPLIT_WIDTH_KEY);
      const n = saved ? Number(saved) : SHELL_SPLIT_DEFAULT_WIDTH;
      if (Number.isFinite(n)) {
        return Math.min(
          Math.max(n, SHELL_SPLIT_MIN_WIDTH),
          SHELL_SPLIT_MAX_WIDTH,
        );
      }
    } catch {
      /* ignore */
    }
    return SHELL_SPLIT_DEFAULT_WIDTH;
  });
  const [isShellPanelOpen, setIsShellPanelOpen] = useState(() => {
    try {
      return localStorage.getItem(SHELL_PANEL_OPEN_KEY) === "true";
    } catch {
      return false;
    }
  });
  const aiDragRef = useRef<{
    startX: number;
    startY: number;
    startSize: number;
  } | null>(null);
  const shellSplitDragRef = useRef<{
    startX: number;
    startSize: number;
  } | null>(null);
  const screenSizeRef = useRef({ width: 1080, height: 1920 });
  const handleStreamActionResultRef = useRef<
    (result: {
      action: string;
      ok: boolean;
      message?: string;
      rotation?: number;
    }) => void
  >(() => {});
  const {
    status: streamStatus,
    connect,
    disconnect,
    sendEvent,
  } = useMobileStream();

  const effectiveActiveAgent =
    activeAgent ??
    (activeAgentId
      ? agents.find((agent) => agent.agent_id === activeAgentId) ?? null
      : null);

  const handleAiPanelToggle = useCallback(() => {
    setIsAiPanelOpen((prev) => {
      const next = !prev;
      try {
        localStorage.setItem(MOBILE_AI_PANEL_KEY, String(next));
      } catch {
        /* ignore */
      }
      return next;
    });
  }, []);

  const handleAiPanelClose = useCallback(() => {
    setIsAiPanelOpen(false);
    try {
      localStorage.setItem(MOBILE_AI_PANEL_KEY, "false");
    } catch {
      /* ignore */
    }
  }, []);

  const handleAiResizeMouseDown = useCallback(
    (e: ReactMouseEvent<HTMLDivElement>) => {
      e.preventDefault();
      if (isMobile) {
        aiDragRef.current = {
          startX: e.clientX,
          startY: e.clientY,
          startSize: aiPanelHeight,
        };
        const onMove = (mv: MouseEvent) => {
          if (!aiDragRef.current) return;
          const delta = aiDragRef.current.startY - mv.clientY;
          const next = Math.min(
            Math.max(
              aiDragRef.current.startSize + delta,
              MOBILE_AI_PANEL_MIN_HEIGHT,
            ),
            MOBILE_AI_PANEL_MAX_HEIGHT,
          );
          setAiPanelHeight(next);
          try {
            localStorage.setItem(MOBILE_AI_PANEL_HEIGHT_KEY, String(next));
          } catch {
            /* ignore */
          }
        };
        const onUp = () => {
          aiDragRef.current = null;
          window.removeEventListener("mousemove", onMove);
          window.removeEventListener("mouseup", onUp);
        };
        window.addEventListener("mousemove", onMove);
        window.addEventListener("mouseup", onUp);
        return;
      }
      aiDragRef.current = {
        startX: e.clientX,
        startY: e.clientY,
        startSize: aiPanelWidth,
      };
      const onMove = (mv: MouseEvent) => {
        if (!aiDragRef.current) return;
        const delta = aiDragRef.current.startX - mv.clientX;
        const next = Math.min(
          Math.max(
            aiDragRef.current.startSize + delta,
            MOBILE_AI_PANEL_MIN_WIDTH,
          ),
          MOBILE_AI_PANEL_MAX_WIDTH,
        );
        setAiPanelWidth(next);
        try {
          localStorage.setItem(MOBILE_AI_PANEL_WIDTH_KEY, String(next));
        } catch {
          /* ignore */
        }
      };
      const onUp = () => {
        aiDragRef.current = null;
        window.removeEventListener("mousemove", onMove);
        window.removeEventListener("mouseup", onUp);
      };
      window.addEventListener("mousemove", onMove);
      window.addEventListener("mouseup", onUp);
    },
    [aiPanelHeight, aiPanelWidth, isMobile],
  );

  const handleShellPanelToggle = useCallback(() => {
    setIsShellPanelOpen((prev) => {
      const next = !prev;
      try {
        localStorage.setItem(SHELL_PANEL_OPEN_KEY, String(next));
      } catch {
        /* ignore */
      }
      return next;
    });
  }, []);

  const handleShellSplitResizeMouseDown = useCallback(
    (e: ReactMouseEvent<HTMLDivElement>) => {
      e.preventDefault();
      e.stopPropagation();
      const startX = e.clientX;
      const startSize = shellSplitWidth;
      let latest = startSize;
      shellSplitDragRef.current = { startX, startSize };
      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";

      const onMove = (mv: MouseEvent) => {
        if (!shellSplitDragRef.current) return;
        mv.preventDefault();
        const delta = shellSplitDragRef.current.startX - mv.clientX;
        latest = Math.min(
          Math.max(
            shellSplitDragRef.current.startSize + delta,
            SHELL_SPLIT_MIN_WIDTH,
          ),
          SHELL_SPLIT_MAX_WIDTH,
        );
        setShellSplitWidth(latest);
      };
      const onUp = () => {
        shellSplitDragRef.current = null;
        document.body.style.cursor = "";
        document.body.style.userSelect = "";
        window.removeEventListener("mousemove", onMove);
        window.removeEventListener("mouseup", onUp);
        try {
          localStorage.setItem(SHELL_SPLIT_WIDTH_KEY, String(latest));
        } catch {
          /* ignore */
        }
      };
      window.addEventListener("mousemove", onMove);
      window.addEventListener("mouseup", onUp);
    },
    [shellSplitWidth],
  );

  const refreshStatus = useCallback(async () => {
    setLoading(true);
    try {
      const data = await mobileApi.status();
      setStatusData(data);
      const pick = device || data.selected_device || data.devices[0] || "";
      if (pick) setDevice(pick);
    } catch (err) {
      showApiError(
        err,
        t("remoteAndroid.statusFailed", "Failed to load mobile status"),
        t,
      );
    } finally {
      setLoading(false);
    }
  }, [device, t]);

  const handleInstall = useCallback(() => {
    if (installPhase === "installing") return;
    setInstallPhase("installing");
    setInstallLogs([]);
    installAbortRef.current = mobileApi.install(
      (line) => setInstallLogs((prev) => [...prev, line]),
      (ok, error) => {
        installAbortRef.current = null;
        if (ok) {
          setInstallPhase("success");
          message.success(
            t("remoteAndroid.installSuccess", "Android 容器已就绪"),
          );
          void refreshStatus();
          return;
        }
        setInstallPhase("failed");
        if (error) {
          setInstallLogs((prev) => [...prev, error]);
        }
        message.error(
          t("remoteAndroid.installFailed", "容器安装失败，请查看日志后重试"),
        );
      },
    );
  }, [installPhase, refreshStatus, t]);

  const cancelInstall = useCallback(() => {
    installAbortRef.current?.abort();
    installAbortRef.current = null;
    setInstallPhase("idle");
    setInstallLogs([]);
    message.info(
      t(
        "remoteAndroid.installCancelHint",
        "已取消安装请求，服务端可能仍在继续安装，请稍后刷新状态。",
      ),
    );
  }, [t]);

  useEffect(() => {
    if (installLogRef.current) {
      installLogRef.current.scrollTop = installLogRef.current.scrollHeight;
    }
  }, [installLogs]);

  useEffect(() => {
    if (canMobile) void refreshStatus();
  }, [canMobile, refreshStatus]);

  const loadDeviceInfo = useCallback(
    async (serial: string) => {
      if (!serial) {
        setDeviceInfo(null);
        return;
      }
      setDeviceInfoLoading(true);
      try {
        const info = await mobileApi.deviceInfo(serial);
        setDeviceInfo(info);
      } catch (err) {
        setDeviceInfo(null);
        showApiError(
          err,
          t("remoteAndroid.deviceInfoFailed", "Failed to load device details"),
          t,
        );
      } finally {
        setDeviceInfoLoading(false);
      }
    },
    [t],
  );

  useEffect(() => {
    if (!canMobile || !device) {
      setDeviceInfo(null);
      return;
    }
    void loadDeviceInfo(device);
  }, [canMobile, device, loadDeviceInfo]);

  // Refresh adb specs again once streaming is up (first probe can race USB).
  useEffect(() => {
    if (!canMobile || !device) return;
    if (streamStatus !== "streaming") return;
    void loadDeviceInfo(device);
  }, [canMobile, device, loadDeviceInfo, streamStatus]);

  // Prefer physical screen size from adb for tap mapping when available.
  useEffect(() => {
    if (deviceInfo?.width && deviceInfo?.height) {
      screenSizeRef.current = {
        width: deviceInfo.width,
        height: deviceInfo.height,
      };
    }
  }, [deviceInfo]);

  const enrichPayload = useCallback(
    (coords: { x: number; y: number }) => ({
      ...coords,
      canvas_width: canvasRef.current?.width ?? 0,
      canvas_height: canvasRef.current?.height ?? 0,
      screen_width: screenSizeRef.current.width,
      screen_height: screenSizeRef.current.height,
    }),
    [],
  );

  const interaction = useCanvasRemotePointer({
    enabled: streamStatus === "streaming",
    canvasRef,
    onEvent: sendEvent,
    enrichPayload,
    sendHoverMoves: false,
  });

  const onKeyDown = useCallback(
    (e: ReactKeyboardEvent<HTMLCanvasElement>) => {
      if (streamStatus !== "streaming") return;
      e.preventDefault();
      if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
        sendEvent({ type: "type", text: e.key });
      } else {
        sendEvent({ type: "keydown", key: e.key });
      }
    },
    [sendEvent, streamStatus],
  );

  const handleConnect = useCallback(() => {
    if (!device) {
      message.warning(t("remoteAndroid.pickDevice", "Select a device first"));
      return;
    }
    const preset = STREAM_QUALITY_PRESETS[streamQuality];
    setFrameReady(false);
    streamDesiredRef.current = true;
    connect(
      {
        device,
        quality: preset.quality,
        maxFps: preset.maxFps,
        maxSide: preset.maxSide,
        codec: "jpeg",
      },
      {
        canvas: canvasRef.current,
        onFrame: (base64, width, height) => {
          if (width > 0 && height > 0) {
            screenSizeRef.current = { width, height };
            setStreamSize({ width, height });
          }
          paintBase64JpegToCanvas(canvasRef.current, base64);
          setFrameReady(true);
        },
        onVideoSize: (width, height) => {
          screenSizeRef.current = { width, height };
          setStreamSize({ width, height });
          setFrameReady(true);
        },
        onError: (msg) => message.error(msg),
        onActionResult: (result) => handleStreamActionResultRef.current(result),
      },
    );
  }, [connect, device, streamQuality, t]);

  const handleStreamQualityChange = useCallback(
    (next: StreamQualityPreset) => {
      setStreamQuality(next);
      try {
        localStorage.setItem(STREAM_QUALITY_KEY, next);
      } catch {
        /* ignore */
      }
      // Reconnect live stream so the new resolution/quality takes effect.
      if (streamStatus === "streaming" || streamStatus === "connecting") {
        const preset = STREAM_QUALITY_PRESETS[next];
        if (!device) return;
        setFrameReady(false);
        streamDesiredRef.current = true;
        connect(
          {
            device,
            quality: preset.quality,
            maxFps: preset.maxFps,
            maxSide: preset.maxSide,
            codec: "jpeg",
          },
          {
            canvas: canvasRef.current,
            onFrame: (base64, width, height) => {
              if (width > 0 && height > 0) {
                screenSizeRef.current = { width, height };
                setStreamSize({ width, height });
              }
              paintBase64JpegToCanvas(canvasRef.current, base64);
              setFrameReady(true);
            },
            onVideoSize: (width, height) => {
              screenSizeRef.current = { width, height };
              setStreamSize({ width, height });
              setFrameReady(true);
            },
            onError: (msg) => message.error(msg),
            onActionResult: (result) =>
              handleStreamActionResultRef.current(result),
          },
        );
      }
    },
    [connect, device, streamStatus],
  );

  const handleStreamActionResult = useCallback(
    (result: {
      action: string;
      ok: boolean;
      message?: string;
      rotation?: number;
    }) => {
      if (result.action !== "rotate") return;
      if (result.ok) {
        message.success(
          t("remoteAndroid.rotateOk", "Screen rotated on device"),
        );
        setStreamSize((prev) =>
          prev.width > 0 ? { width: prev.height, height: prev.width } : prev,
        );
        if (device) {
          void loadDeviceInfo(device);
          window.setTimeout(() => handleConnect(), 350);
        }
      } else {
        message.warning(
          result.message === "emulator_rotation_unsupported"
            ? t(
                "remoteAndroid.rotateFailedEmulator",
                "This emulator does not apply remote rotation. Use a physical device, or rotate from the emulator toolbar.",
              )
            : t(
                "remoteAndroid.rotateFailed",
                "Could not rotate this device remotely. Try rotating manually on the device.",
              ),
        );
      }
    },
    [device, handleConnect, loadDeviceInfo, t],
  );

  useEffect(() => {
    handleStreamActionResultRef.current = handleStreamActionResult;
  }, [handleStreamActionResult]);
  const handleDisconnect = useCallback(() => {
    streamDesiredRef.current = false;
    disconnect();
    clearCanvas(canvasRef.current);
    setFrameReady(false);
    setStreamSize({ width: 0, height: 0 });
  }, [disconnect]);

  // Pause/resume when the hub tab is hidden so phone/desktop don't stream at once.
  useEffect(() => {
    if (!isVisible) {
      disconnect();
      clearCanvas(canvasRef.current);
      setFrameReady(false);
      return;
    }
    if (streamDesiredRef.current && device) {
      handleConnect();
    }
    // handleConnect identity changes often; only react to visibility/device.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isVisible, device, disconnect]);

  const sendRailKey = useCallback(
    (key: RailKey) => {
      if (streamStatus !== "streaming") return;
      sendEvent({ type: "keyevent", key });
    },
    [sendEvent, streamStatus],
  );

  const handleRotate = useCallback(() => {
    if (streamStatus !== "streaming") return;
    sendEvent({ type: "rotate" });
  }, [sendEvent, streamStatus]);

  const handleScreenshot = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas || !frameReady) {
      message.warning(
        t(
          "remoteAndroid.screenshotNeedStream",
          "Connect and wait for a frame first",
        ),
      );
      return;
    }
    try {
      const url = canvas.toDataURL("image/png");
      const a = document.createElement("a");
      a.href = url;
      a.download = `octop-phone-${device || "screen"}-${Date.now()}.png`;
      a.click();
    } catch {
      message.error(t("remoteAndroid.screenshotFailed", "Screenshot failed"));
    }
  }, [device, frameReady, t]);

  const phoneTabOptions = useMemo(
    () =>
      REMOTE_PHONE_VIEW_TABS.map((value) => {
        const Icon = PHONE_TAB_ICONS[value];
        return {
          value,
          label: t(`remoteAndroid.tabs.${value}`),
          icon: Icon,
        };
      }),
    [t],
  );

  if (!canMobile) {
    return <ForbiddenPage />;
  }

  const ready = statusData?.setup_state === "ready" && statusData.ok;
  const needsDevice = statusData?.setup_state === "needs_device";
  const needsInstall = statusData?.setup_state === "needs_install";
  const showStream =
    streamStatus === "streaming" || streamStatus === "connecting";
  const hasDevice = Boolean(device);
  const railEnabled = streamStatus === "streaming";
  const isLandscape =
    streamSize.width > 0 && streamSize.width > streamSize.height;
  const statusClass =
    streamStatus === "streaming"
      ? `${styles.statusPill} ${styles.statusStreaming}`
      : streamStatus === "connecting"
      ? `${styles.statusPill} ${styles.statusConnecting}`
      : `${styles.statusPill} ${styles.statusIdle}`;

  const statusLabel =
    streamStatus === "streaming"
      ? t("remoteAndroid.statusStreaming", "Streaming")
      : streamStatus === "connecting"
      ? t("remoteAndroid.statusConnecting", "Connecting")
      : t("remoteAndroid.statusIdle", "Idle");

  const none = t("remoteAndroid.infoNone", "—");
  const displayName = deviceInfo?.model || device || none;
  const hardwareLabel =
    deviceInfo?.cpu_cores != null && deviceInfo?.mem_total_mb != null
      ? t("remoteAndroid.infoHardwareValue", {
          cores: deviceInfo.cpu_cores,
          memGb: (deviceInfo.mem_total_mb / 1024).toFixed(1),
          defaultValue: "{{cores}} cores · {{memGb}} GB RAM",
        })
      : deviceInfo?.cpu_cores != null
      ? t("remoteAndroid.infoCoresValue", {
          cores: deviceInfo.cpu_cores,
          defaultValue: "{{cores}} cores",
        })
      : deviceInfo?.mem_total_mb != null
      ? t("remoteAndroid.infoMemValue", {
          memGb: (deviceInfo.mem_total_mb / 1024).toFixed(1),
          defaultValue: "{{memGb}} GB RAM",
        })
      : none;
  const storagePrimary =
    deviceInfo?.storage_total_gb != null
      ? t("remoteAndroid.infoStorageTotal", {
          total: deviceInfo.storage_total_gb.toFixed(1),
          defaultValue: "{{total}} GB",
        })
      : none;
  const storageSecondary =
    deviceInfo?.storage_used_gb != null &&
    deviceInfo?.storage_total_gb != null &&
    deviceInfo?.storage_avail_gb != null
      ? t("remoteAndroid.infoStorageDetail", {
          used: deviceInfo.storage_used_gb.toFixed(1),
          total: deviceInfo.storage_total_gb.toFixed(1),
          avail: deviceInfo.storage_avail_gb.toFixed(1),
          defaultValue: "{{used}} / {{total}} GB ({{avail}} GB free)",
        })
      : null;
  const screenPrimary =
    deviceInfo?.width && deviceInfo?.height
      ? `${deviceInfo.width} × ${deviceInfo.height}`
      : streamSize.width > 0
      ? `${streamSize.width} × ${streamSize.height}`
      : none;
  const screenSecondary = [
    deviceInfo?.density_dpi != null
      ? t("remoteAndroid.infoDpiValue", {
          dpi: deviceInfo.density_dpi,
          defaultValue: "{{dpi}} dpi",
        })
      : null,
    deviceInfo?.refresh_hz != null
      ? t("remoteAndroid.infoFpsValue", {
          fps: deviceInfo.refresh_hz,
          defaultValue: "{{fps}} fps",
        })
      : null,
    deviceInfo?.android_version
      ? t("remoteAndroid.infoAndroidValue", {
          version: deviceInfo.android_version,
          defaultValue: "Android {{version}}",
        })
      : null,
  ]
    .filter(Boolean)
    .join(" · ");

  const railItems: {
    key: string;
    label: string;
    icon: ReactNode;
    onClick: () => void;
    dividerAfter?: boolean;
  }[] = [
    {
      key: "power",
      label: t("remoteAndroid.railPower", "Power"),
      icon: <Power size={15} />,
      onClick: () => sendRailKey("power"),
      dividerAfter: true,
    },
    {
      key: "volume_up",
      label: t("remoteAndroid.railVolumeUp", "Volume up"),
      icon: <Volume2 size={15} />,
      onClick: () => sendRailKey("volume_up"),
    },
    {
      key: "volume_down",
      label: t("remoteAndroid.railVolumeDown", "Volume down"),
      icon: <Volume1 size={15} />,
      onClick: () => sendRailKey("volume_down"),
      dividerAfter: true,
    },
    {
      key: "screenshot",
      label: t("remoteAndroid.railScreenshot", "Screenshot"),
      icon: <Camera size={15} />,
      onClick: handleScreenshot,
      dividerAfter: true,
    },
    {
      key: "rotate",
      label: t("remoteAndroid.railRotate", "Rotate screen"),
      icon: <RotateCw size={15} />,
      onClick: handleRotate,
      dividerAfter: true,
    },
    {
      key: "back",
      label: t("remoteAndroid.navBack", "Back"),
      icon: <Triangle size={13} style={{ transform: "rotate(-90deg)" }} />,
      onClick: () => sendRailKey("back"),
    },
    {
      key: "home",
      label: t("remoteAndroid.navHome", "Home"),
      icon: <Circle size={13} />,
      onClick: () => sendRailKey("home"),
    },
    {
      key: "recents",
      label: t("remoteAndroid.navRecents", "Recents"),
      icon: <Square size={12} />,
      onClick: () => sendRailKey("recents"),
    },
  ];

  const remotePhoneIdleGuide = (
    <>
      {loading && !statusData ? (
        <Spin size="large" />
      ) : (
        <RemotePhoneIdleGuide
          variant="screen"
          loading={loading}
          statusData={statusData}
          installPhase={installPhase}
          installLogs={installLogs}
          installLogRef={installLogRef}
          ready={ready}
          needsInstall={needsInstall}
          needsDevice={needsDevice}
          device={device}
          onConnect={handleConnect}
          onInstall={handleInstall}
          onRefresh={() => void refreshStatus()}
          onCancelInstall={cancelInstall}
        />
      )}
    </>
  );

  const remotePhoneShellIdleGuide = (
    <>
      {loading && !statusData ? (
        <Spin size="large" />
      ) : (
        <RemotePhoneIdleGuide
          variant="shell"
          loading={loading}
          statusData={statusData}
          installPhase={installPhase}
          installLogs={installLogs}
          installLogRef={installLogRef}
          ready={ready}
          needsInstall={needsInstall}
          needsDevice={needsDevice}
          device={device}
          onConnect={handleConnect}
          onInstall={handleInstall}
          onRefresh={() => void refreshStatus()}
          onCancelInstall={cancelInstall}
        />
      )}
    </>
  );

  const showTopBar = Boolean(ready || hasDevice || statusData);

  const aiToggleButton = (
    <Tooltip title={t("remoteAndroid.ai.title", "AI 助手")}>
      <Button
        size="small"
        type={isAiPanelOpen ? "primary" : "default"}
        icon={<Bot size={14} />}
        onClick={handleAiPanelToggle}
        aria-label={t("remoteAndroid.ai.title", "AI 助手")}
        className={styles.commandIconBtn}
      />
    </Tooltip>
  );

  const shellToggleButton = (
    <Button
      type={isShellPanelOpen ? "primary" : "default"}
      icon={<TerminalSquare size={14} />}
      onClick={handleShellPanelToggle}
      aria-pressed={isShellPanelOpen}
    >
      {t("remoteAndroid.toggleShell", "打开 ADB 调试")}
    </Button>
  );

  const viewSwitcher = (
    <nav
      className={styles.viewSwitcher}
      aria-label={t("remoteAndroid.tabsLabel", "Phone view")}
    >
      {phoneTabOptions.map((tab) => {
        const Icon = tab.icon;
        const active = activePhoneTab === tab.value;
        return (
          <button
            key={tab.value}
            type="button"
            role="tab"
            aria-selected={active}
            className={`${styles.viewSwitcherTab}${
              active ? ` ${styles.viewSwitcherTabActive}` : ""
            }`}
            onClick={() => handlePhoneTabChange(tab.value)}
          >
            <Icon size={14} strokeWidth={2} aria-hidden />
            <span>{tab.label}</span>
          </button>
        );
      })}
    </nav>
  );

  const qualityControl = (
    <div className={styles.qualityControl}>
      <Select
        size="small"
        style={{ minWidth: 88 }}
        value={streamQuality}
        onChange={(value) =>
          handleStreamQualityChange(value as StreamQualityPreset)
        }
        options={[
          {
            value: "low",
            label: t("remoteAndroid.streamQualityLow", "流畅"),
          },
          {
            value: "balanced",
            label: t("remoteAndroid.streamQualityBalanced", "均衡"),
          },
          {
            value: "high",
            label: t("remoteAndroid.streamQualityHigh", "高清"),
          },
          {
            value: "max",
            label: t("remoteAndroid.streamQualityMax", "原画"),
          },
        ]}
        popupMatchSelectWidth={false}
        aria-label={t("remoteAndroid.streamQuality", "画质")}
      />
    </div>
  );

  const actions = (
    <Space size={8} wrap>
      {!showTopBar && isMobile ? (
        <>
          {viewSwitcher}
          {aiToggleButton}
        </>
      ) : !showTopBar ? (
        aiToggleButton
      ) : null}
      {needsInstall ? (
        <Button
          type="primary"
          icon={<Download size={14} />}
          loading={installPhase === "installing"}
          onClick={handleInstall}
        >
          {t("remoteAndroid.install", "安装容器")}
        </Button>
      ) : null}
      {!isMobile ? shellToggleButton : null}
      <Button
        icon={<RefreshCw size={14} />}
        onClick={() => void refreshStatus()}
        loading={loading}
      >
        {t("remoteAndroid.refresh", "Refresh")}
      </Button>
      {showStream ? (
        <Button icon={<Unplug size={14} />} onClick={handleDisconnect} danger>
          {t("remoteAndroid.disconnect", "Disconnect")}
        </Button>
      ) : (
        <Button
          type={needsInstall ? "default" : "primary"}
          icon={<PlugZap size={14} />}
          disabled={!ready || !device}
          onClick={handleConnect}
        >
          {t("remoteAndroid.connect", "Connect")}
        </Button>
      )}
    </Space>
  );

  const useDesktopSplit = !isMobile;
  const desktopShellOpen = useDesktopSplit && isShellPanelOpen;
  const mountScreenPanel = useDesktopSplit || isPhoneTabMounted("screen");
  const mountShellPanel =
    desktopShellOpen || (!useDesktopSplit && isPhoneTabMounted("shell"));
  const showScreenPanel = useDesktopSplit || activePhoneTab === "screen";
  const showShellPanel =
    desktopShellOpen || (!useDesktopSplit && activePhoneTab === "shell");
  const shellPanelVisible = desktopShellOpen
    ? isVisible
    : !useDesktopSplit && activePhoneTab === "shell" && isVisible;
  const showSidePanel = !desktopShellOpen;

  const pageBody = (
    <div className={styles.remotePhonePage}>
      {embedded && <div className={styles.embeddedActions}>{actions}</div>}
      {needsInstall && installPhase !== "installing" && (
        <Alert
          type="info"
          showIcon
          message={t(
            "remoteAndroid.needsInstall",
            "Container install required",
          )}
          description={t(
            "remoteAndroid.needsInstallDesc",
            "此主机使用容器 Android 后端。可一键拉取并启动容器（需本机已安装 Docker）。",
          )}
          action={
            <Button
              size="small"
              type="primary"
              icon={<Download size={14} />}
              onClick={handleInstall}
            >
              {t("remoteAndroid.install", "安装容器")}
            </Button>
          }
        />
      )}
      {needsDevice && (
        <Alert
          type="warning"
          showIcon
          message={t("remoteAndroid.needsDevice", "No device connected")}
          description={
            statusData?.reason ||
            t(
              "remoteAndroid.needsDeviceDesc",
              "Start an Android emulator or connect a phone via USB, then refresh.",
            )
          }
        />
      )}
      {ready && !showStream && (
        <Alert
          type="success"
          showIcon
          message={t("remoteAndroid.readyTitle", "Phone ready")}
          description={t(
            "remoteAndroid.readyDesc",
            "A connected device was found. Click Connect to stream and control it.",
          )}
        />
      )}

      <div
        className={`${styles.workspaceRow}${
          isMobile && isAiPanelOpen ? ` ${styles.workspaceRowColumn}` : ""
        }`}
      >
        <div className={styles.mainColumn}>
          <div className={styles.phoneViewport}>
            <div className={styles.deviceBar}>
              <div className={styles.deviceMeta}>
                {isMobile ? viewSwitcher : null}
                {showTopBar ? (
                  <>
                    <Select
                      style={{ minWidth: 200 }}
                      placeholder={t(
                        "remoteAndroid.devicePlaceholder",
                        "Select device",
                      )}
                      value={device || undefined}
                      onChange={(value) => setDevice(value)}
                      options={(statusData?.devices ?? []).map((d) => ({
                        value: d,
                        label: d,
                      }))}
                      disabled={showStream}
                    />
                    {streamSize.width > 0 ? (
                      <span className={styles.streamSizePill}>
                        {streamSize.width}×{streamSize.height}
                      </span>
                    ) : null}
                    <span className={statusClass}>{statusLabel}</span>
                  </>
                ) : null}
              </div>
              <div className={styles.deviceBarSpacer} />
              <div className={styles.deviceBarActions}>
                {qualityControl}
                {aiToggleButton}
              </div>
            </div>
            <div
              className={
                desktopShellOpen ? styles.splitPanels : styles.phoneTabPanels
              }
            >
              {mountScreenPanel ? (
                <div
                  className={styles.phoneTabPanel}
                  style={{
                    display: showScreenPanel ? "flex" : "none",
                  }}
                  aria-hidden={!showScreenPanel}
                >
                  <div className={styles.viewport}>
                    {loading && !statusData ? (
                      <div className={styles.idleFill}>
                        <Spin size="large" />
                      </div>
                    ) : (
                      <>
                        {!showStream ? (
                          <div className={styles.idleFill}>
                            {remotePhoneIdleGuide}
                          </div>
                        ) : null}

                        <div
                          className={styles.streamWorkspace}
                          hidden={!showStream}
                          aria-hidden={!showStream}
                        >
                          <div className={styles.stage}>
                            {showStream && !frameReady ? (
                              <div className={styles.connectingStage}>
                                <StreamConnectingIndicator
                                  label={t(
                                    "remoteAndroid.connecting",
                                    "Connecting…",
                                  )}
                                  hint={t(
                                    "remoteAndroid.connectingHint",
                                    "Waiting for the first frame",
                                  )}
                                />
                              </div>
                            ) : null}
                            <div
                              className={`${styles.phoneCluster}${
                                !frameReady
                                  ? ` ${styles.phoneClusterOffstage}`
                                  : ""
                              }${
                                isLandscape
                                  ? ` ${styles.phoneClusterLandscape}`
                                  : ""
                              }`}
                              aria-hidden={!frameReady}
                            >
                              <div className={styles.phoneFrame}>
                                <canvas
                                  ref={canvasRef}
                                  className={styles.canvas}
                                  tabIndex={0}
                                  onPointerDown={(e) => {
                                    canvasRef.current?.focus();
                                    interaction.onPointerDown(e);
                                  }}
                                  onPointerMove={interaction.onPointerMove}
                                  onPointerLeave={interaction.onPointerLeave}
                                  onContextMenu={interaction.onContextMenu}
                                  onDoubleClick={interaction.onDoubleClick}
                                  onWheel={interaction.onWheel}
                                  onKeyDown={onKeyDown}
                                  style={{
                                    ...interaction.pointerStyle,
                                    cursor:
                                      streamStatus === "streaming"
                                        ? "crosshair"
                                        : undefined,
                                  }}
                                />
                              </div>
                              <aside
                                className={styles.deviceRail}
                                aria-label={t(
                                  "remoteAndroid.railLabel",
                                  "Device controls",
                                )}
                              >
                                {railItems.map((item) => (
                                  <Fragment key={item.key}>
                                    <Tooltip
                                      title={item.label}
                                      placement="right"
                                    >
                                      <button
                                        type="button"
                                        className={styles.railBtn}
                                        aria-label={item.label}
                                        disabled={
                                          item.key === "screenshot"
                                            ? !frameReady
                                            : !railEnabled
                                        }
                                        onClick={item.onClick}
                                      >
                                        {item.icon}
                                      </button>
                                    </Tooltip>
                                    {item.dividerAfter ? (
                                      <div
                                        className={styles.railDivider}
                                        aria-hidden
                                      />
                                    ) : null}
                                  </Fragment>
                                ))}
                              </aside>
                            </div>
                          </div>

                          {showSidePanel ? (
                            <aside className={styles.sidePanel}>
                              <section className={styles.infoSection}>
                                <header className={styles.infoSectionHead}>
                                  <Smartphone
                                    size={15}
                                    strokeWidth={2}
                                    aria-hidden
                                  />
                                  <h3 className={styles.sidePanelTitle}>
                                    {t(
                                      "remoteAndroid.infoTitle",
                                      "Device info",
                                    )}
                                  </h3>
                                  {deviceInfoLoading ? (
                                    <Spin size="small" />
                                  ) : null}
                                </header>
                                <dl className={styles.infoList}>
                                  <div className={styles.infoRow}>
                                    <dt className={styles.infoLabel}>
                                      {t(
                                        "remoteAndroid.infoName",
                                        "Device name",
                                      )}
                                    </dt>
                                    <dd className={styles.infoValue}>
                                      {displayName}
                                    </dd>
                                  </div>
                                  <div className={styles.infoRow}>
                                    <dt className={styles.infoLabel}>
                                      {t(
                                        "remoteAndroid.infoSerial",
                                        "Device ID",
                                      )}
                                    </dt>
                                    <dd className={styles.infoValue}>
                                      {device || none}
                                    </dd>
                                  </div>
                                </dl>
                              </section>

                              <section className={styles.infoSection}>
                                <header className={styles.infoSectionHead}>
                                  <Cpu size={15} strokeWidth={2} aria-hidden />
                                  <h3 className={styles.sidePanelTitle}>
                                    {t(
                                      "remoteAndroid.infoSpecsTitle",
                                      "Specifications",
                                    )}
                                  </h3>
                                </header>
                                <dl className={styles.infoList}>
                                  <div className={styles.infoRow}>
                                    <dt className={styles.infoLabel}>
                                      <span
                                        className={styles.infoLabelWithIcon}
                                      >
                                        <Cpu size={12} aria-hidden />
                                        {t(
                                          "remoteAndroid.infoHardware",
                                          "Hardware",
                                        )}
                                      </span>
                                    </dt>
                                    <dd className={styles.infoValue}>
                                      {hardwareLabel}
                                    </dd>
                                  </div>
                                  <div className={styles.infoRow}>
                                    <dt className={styles.infoLabel}>
                                      <span
                                        className={styles.infoLabelWithIcon}
                                      >
                                        <HardDrive size={12} aria-hidden />
                                        {t(
                                          "remoteAndroid.infoStorage",
                                          "Storage",
                                        )}
                                      </span>
                                    </dt>
                                    <dd className={styles.infoValue}>
                                      {storagePrimary}
                                      {storageSecondary ? (
                                        <span className={styles.infoSub}>
                                          {storageSecondary}
                                        </span>
                                      ) : null}
                                    </dd>
                                  </div>
                                  <div className={styles.infoRow}>
                                    <dt className={styles.infoLabel}>
                                      <span
                                        className={styles.infoLabelWithIcon}
                                      >
                                        <MonitorSmartphone
                                          size={12}
                                          aria-hidden
                                        />
                                        {t(
                                          "remoteAndroid.infoScreen",
                                          "Screen",
                                        )}
                                      </span>
                                    </dt>
                                    <dd className={styles.infoValue}>
                                      {screenPrimary}
                                      {screenSecondary ? (
                                        <span className={styles.infoSub}>
                                          {screenSecondary}
                                        </span>
                                      ) : null}
                                    </dd>
                                  </div>
                                </dl>
                              </section>

                              <section className={styles.infoSection}>
                                <header className={styles.infoSectionHead}>
                                  <h3 className={styles.sidePanelTitle}>
                                    {t(
                                      "remoteAndroid.infoStatusTitle",
                                      "Current status",
                                    )}
                                  </h3>
                                  <span className={statusClass}>
                                    {statusLabel}
                                  </span>
                                </header>
                                <dl className={styles.infoList}>
                                  <div className={styles.infoRow}>
                                    <dt className={styles.infoLabel}>
                                      {t(
                                        "remoteAndroid.infoBackend",
                                        "Backend",
                                      )}
                                    </dt>
                                    <dd className={styles.infoValue}>
                                      {statusData?.backend || none}
                                    </dd>
                                  </div>
                                  {streamSize.width > 0 ? (
                                    <div className={styles.infoRow}>
                                      <dt className={styles.infoLabel}>
                                        {t(
                                          "remoteAndroid.infoResolution",
                                          "Stream size",
                                        )}
                                      </dt>
                                      <dd className={styles.infoValue}>
                                        {`${streamSize.width} × ${streamSize.height}`}
                                      </dd>
                                    </div>
                                  ) : null}
                                </dl>
                              </section>
                            </aside>
                          ) : null}
                        </div>
                      </>
                    )}
                  </div>
                </div>
              ) : null}
              {desktopShellOpen ? (
                <div
                  className={styles.splitHandle}
                  onMouseDown={handleShellSplitResizeMouseDown}
                  role="separator"
                  aria-orientation="vertical"
                  aria-label={t(
                    "remoteAndroid.shellSplitHandle",
                    "Resize shell panel",
                  )}
                />
              ) : null}
              {mountShellPanel ? (
                <div
                  className={`${styles.phoneTabPanel}${
                    desktopShellOpen ? ` ${styles.splitShellPane}` : ""
                  }`}
                  style={{
                    display: showShellPanel ? "flex" : "none",
                    ...(desktopShellOpen
                      ? {
                          flex: `0 0 ${shellSplitWidth}px`,
                          width: shellSplitWidth,
                        }
                      : null),
                  }}
                  aria-hidden={!showShellPanel}
                >
                  <AdbShellPanel
                    device={device}
                    streamActive={showStream}
                    visible={shellPanelVisible}
                    idleGuide={remotePhoneShellIdleGuide}
                  />
                </div>
              ) : null}
            </div>
          </div>
        </div>

        {isAiPanelOpen ? (
          <div
            className={isMobile ? styles.aiPanelBottom : styles.aiPanelRight}
            style={
              isMobile ? { height: aiPanelHeight } : { width: aiPanelWidth }
            }
          >
            <div
              className={
                isMobile ? styles.resizeHandleTop : styles.resizeHandleLeft
              }
              onMouseDown={handleAiResizeMouseDown}
            />
            <MobileAiPanel
              activeAgent={effectiveActiveAgent}
              device={device || null}
              deviceName={deviceInfo?.model ?? null}
              streamActive={showStream}
              layout={isMobile ? "bottom" : "right"}
              onClose={handleAiPanelClose}
            />
          </div>
        ) : null}
      </div>
    </div>
  );

  if (embedded) {
    return <div className={styles.embeddedRoot}>{pageBody}</div>;
  }

  return (
    <PageShell
      title={t("pageShell.mobile.title", "Remote Phone")}
      subtitle={t(
        "pageShell.mobile.subtitle",
        "View and control a connected phone or emulator",
      )}
      fill
      actions={actions}
    >
      {pageBody}
    </PageShell>
  );
}
