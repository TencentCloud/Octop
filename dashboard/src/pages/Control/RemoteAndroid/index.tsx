import { useCallback, useEffect, useRef, useState } from "react";
import { Alert, Button, Result, Select, Space, Spin } from "antd";
import { message } from "@/utils/antdMessage";
import { PlugZap, RefreshCw, Smartphone, Unplug } from "lucide-react";
import { useTranslation } from "react-i18next";

import ForbiddenPage from "../../../components/ForbiddenPage";
import StreamConnectingIndicator from "../../../components/StreamConnectingIndicator";
import PageShell from "../../../layouts/PageShell";
import {
  mobileApi,
  type MobileStatusResponse,
} from "../../../api/modules/mobile";
import {
  paintBase64JpegToCanvas,
  clearCanvas,
} from "../../../utils/browserCanvas";
import { useMobileStream } from "../../../hooks/useMobileStream";
import { useCanvasRemotePointer } from "../../../hooks/useCanvasRemotePointer";
import { useCurrentUser } from "../../../hooks/useCurrentUser";
import { userCan } from "../../../utils/permissions";
import { showApiError } from "../../../utils/showApiToast";
import styles from "./index.module.less";

export default function RemoteAndroidPage() {
  const { t } = useTranslation();
  const user = useCurrentUser();
  const canMobile = userCan(user, "mobile");
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [statusData, setStatusData] = useState<MobileStatusResponse | null>(
    null,
  );
  const [loading, setLoading] = useState(false);
  const [device, setDevice] = useState<string>("");
  const [frameReady, setFrameReady] = useState(false);
  const screenSizeRef = useRef({ width: 1080, height: 1920 });
  const {
    status: streamStatus,
    connect,
    disconnect,
    sendEvent,
  } = useMobileStream();

  const refreshStatus = useCallback(async () => {
    setLoading(true);
    try {
      const data = await mobileApi.status();
      setStatusData(data);
      const pick = device || data.selected_device || data.devices[0] || "";
      if (pick) setDevice(pick);
    } catch (err) {
      showApiError(err);
    } finally {
      setLoading(false);
    }
  }, [device]);

  useEffect(() => {
    if (canMobile) void refreshStatus();
  }, [canMobile, refreshStatus]);

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

  const { onPointerDown, onPointerMove, onPointerUp, onWheel } =
    useCanvasRemotePointer({
      enabled: streamStatus === "streaming",
      canvasRef,
      onEvent: sendEvent,
      enrichPayload,
    });

  const handleConnect = useCallback(() => {
    if (!device) {
      message.warning(t("remoteAndroid.pickDevice", "Select a device first"));
      return;
    }
    setFrameReady(false);
    connect(
      { device, quality: 80, maxFps: 8 },
      {
        onFrame: (base64, width, height) => {
          screenSizeRef.current = { width, height };
          paintBase64JpegToCanvas(canvasRef.current, base64, width, height);
          setFrameReady(true);
        },
        onError: (msg) => message.error(msg),
      },
    );
  }, [connect, device, t]);

  const handleDisconnect = useCallback(() => {
    disconnect();
    clearCanvas(canvasRef.current);
    setFrameReady(false);
  }, [disconnect]);

  if (!canMobile) {
    return (
      <ForbiddenPage
        title={t("remoteAndroid.adminOnlyTitle", "Remote Android")}
        description={t(
          "remoteAndroid.adminOnlyDesc",
          "Remote Android requires the mobile permission.",
        )}
      />
    );
  }

  const ready = statusData?.setup_state === "ready" && statusData.ok;
  const needsDevice = statusData?.setup_state === "needs_device";
  const needsInstall = statusData?.setup_state === "needs_install";
  const streaming =
    streamStatus === "streaming" || streamStatus === "connecting";

  return (
    <PageShell
      title={t("pageShell.mobile.title", "Remote Android")}
      subtitle={t(
        "pageShell.mobile.subtitle",
        "View and control a connected Android device or emulator",
      )}
      actions={
        <Space>
          <Button
            icon={<RefreshCw size={16} />}
            onClick={() => void refreshStatus()}
            loading={loading}
          >
            {t("remoteAndroid.refresh", "Refresh")}
          </Button>
          {streaming ? (
            <Button
              icon={<Unplug size={16} />}
              onClick={handleDisconnect}
              danger
            >
              {t("remoteAndroid.disconnect", "Disconnect")}
            </Button>
          ) : (
            <Button
              type="primary"
              icon={<PlugZap size={16} />}
              disabled={!ready || !device}
              onClick={handleConnect}
            >
              {t("remoteAndroid.connect", "Connect")}
            </Button>
          )}
        </Space>
      }
    >
      {needsInstall && (
        <Alert
          type="info"
          showIcon
          message={t(
            "remoteAndroid.needsInstall",
            "Container install required",
          )}
          description={t(
            "remoteAndroid.needsInstallDesc",
            "This host uses a container Android backend. Install it from the server before connecting.",
          )}
          style={{ marginBottom: 16 }}
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
          style={{ marginBottom: 16 }}
        />
      )}
      <div className={styles.toolbar}>
        <Smartphone size={18} />
        <Select
          style={{ minWidth: 220 }}
          placeholder={t("remoteAndroid.devicePlaceholder", "Select device")}
          value={device || undefined}
          onChange={setDevice}
          options={(statusData?.devices ?? []).map((d) => ({
            value: d,
            label: d,
          }))}
          disabled={streaming}
        />
      </div>
      <div className={styles.viewport}>
        <canvas
          ref={canvasRef}
          className={styles.canvas}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onWheel={onWheel}
        />
        {!frameReady && streaming && (
          <StreamConnectingIndicator
            label={t("remoteAndroid.connecting", "Connecting…")}
          />
        )}
        {!streaming && !ready && !loading && (
          <Result
            icon={<Smartphone size={48} />}
            title={t("remoteAndroid.idleTitle", "Not connected")}
            subTitle={t(
              "remoteAndroid.idleDesc",
              "Connect to stream and control the Android screen.",
            )}
          />
        )}
        {loading && !statusData && <Spin />}
      </div>
    </PageShell>
  );
}
