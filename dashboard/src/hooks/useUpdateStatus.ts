import { useCallback, useEffect, useState } from "react";
import { updateApi, type UpdateStatus } from "../api/modules/update";
import {
  getDesktopBridge,
  isDesktopShell,
  type DesktopUpdateCheckResult,
} from "../utils/desktopBridge";
import {
  UPDATE_STATUS_CHANGED_EVENT,
  UPDATE_STATUS_POLL_MS,
  isUpdateStatusCacheExpired,
  readStoredUpdateStatus,
  storeUpdateStatus,
} from "../utils/updateStatusCache";

/** Shared in-flight probe so Header + Sidebar mounts don't stampede PyPI. */
let inFlight: Promise<UpdateStatus | null> | null = null;

/**
 * Shell check → the same status the header icon and update page already share.
 * ``latestVersion`` is the channel head, including when it is not an upgrade.
 */
function statusFromShell(res: DesktopUpdateCheckResult): UpdateStatus {
  const available =
    res.status === "update-available" && Boolean(res.latestVersion);
  return {
    current_version: res.currentVersion,
    latest_version: res.latestVersion,
    has_update: available,
    is_editable: false,
    service_mode: null,
    desktop: true,
    error: res.status === "error" ? res.error : null,
    error_code: null,
    source: null,
    last_check_time: new Date().toISOString(),
    release_notes: null,
  };
}

async function probeUpdateStatus(): Promise<UpdateStatus | null> {
  if (inFlight) return inFlight;
  inFlight = (async () => {
    try {
      // Desktop Python reports has_update: false on purpose. The shell probe
      // is what lights the update icon; the page reads the same stored status.
      if (isDesktopShell()) {
        const bridge = getDesktopBridge();
        if (!bridge) return null;
        const next = statusFromShell(await bridge.checkForUpdates());
        storeUpdateStatus(next);
        return next;
      }
      const next = await updateApi.getUpdateStatus();
      storeUpdateStatus(next);
      return next;
    } catch {
      return null;
    } finally {
      inFlight = null;
    }
  })();
  return inFlight;
}

export function useUpdateStatus() {
  const [status, setStatus] = useState<UpdateStatus | null>(() =>
    readStoredUpdateStatus(),
  );

  const refreshStatus = useCallback(async (force = false) => {
    if (!force && !isUpdateStatusCacheExpired()) {
      const cached = readStoredUpdateStatus();
      if (cached) {
        setStatus(cached);
        return;
      }
    }
    const next = await probeUpdateStatus();
    if (next) setStatus(next);
  }, []);

  useEffect(() => {
    // Dashboard boot: always re-fetch so a restarted server is not hidden
    // by a still-fresh localStorage entry. Focus / interval still honor TTL.
    void refreshStatus(true);
  }, [refreshStatus]);

  useEffect(() => {
    const onFocus = () => {
      void refreshStatus(false);
    };
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [refreshStatus]);

  // Keep checking while the dashboard stays open (cache TTL still gates PyPI).
  useEffect(() => {
    const id = window.setInterval(() => {
      void refreshStatus(false);
    }, UPDATE_STATUS_POLL_MS);
    return () => window.clearInterval(id);
  }, [refreshStatus]);

  // Sync Header / Sidebar / Update page when any writer stores a new status.
  useEffect(() => {
    const onChanged = (event: Event) => {
      const next = (event as CustomEvent<UpdateStatus>).detail;
      if (next) setStatus(next);
    };
    window.addEventListener(UPDATE_STATUS_CHANGED_EVENT, onChanged);
    return () =>
      window.removeEventListener(UPDATE_STATUS_CHANGED_EVENT, onChanged);
  }, []);

  const hasUpdate = Boolean(status?.has_update && status?.latest_version);

  return { status, hasUpdate, refreshStatus };
}
