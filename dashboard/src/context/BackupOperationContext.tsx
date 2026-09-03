import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { App } from "antd";
import { useTranslation } from "react-i18next";

import {
  backupApi,
  type BackupOperationKind,
  type BackupStatusResponse,
  type CreateBackupOptions,
} from "../api/modules/backup";
import { apiErrorMessage } from "../utils/apiError";

export type BackupOpKind = BackupOperationKind | "upload" | null;

interface BackupOperationContextValue {
  kind: BackupOpKind;
  restoreTarget: string | null;
  uploadPercent: number | null;
  /** True while create / restore / auto / export / upload is in flight. */
  busy: boolean;
  creating: boolean;
  restoring: boolean;
  autoRunning: boolean;
  createBackup: (options: CreateBackupOptions) => Promise<boolean>;
  runAutoBackup: () => Promise<boolean>;
  restoreBackup: (name: string, restoreConfig: boolean) => Promise<boolean>;
  uploadBackup: (file: File) => Promise<boolean>;
  /** Align UI with server lock (call from backup panel while mounted). */
  syncFromServer: () => Promise<void>;
  /** Called by the backup panel so list refresh can run after remote ops finish. */
  setOnSettled: (fn: (() => void) | null) => void;
}

const BackupOperationContext =
  createContext<BackupOperationContextValue | null>(null);

function mapServerOperation(
  op: BackupStatusResponse["operation"],
): BackupOpKind {
  if (op === "create" || op === "auto" || op === "export") return op;
  if (op === "restore") return "restore";
  return "create";
}

export function BackupOperationProvider({ children }: { children: ReactNode }) {
  const { message } = App.useApp();
  const { t } = useTranslation();
  const [kind, setKind] = useState<BackupOpKind>(null);
  const [restoreTarget, setRestoreTarget] = useState<string | null>(null);
  const [uploadPercent, setUploadPercent] = useState<number | null>(null);
  /** Local request owns the kind; server poll must not clear it mid-flight. */
  const localOwnedRef = useRef(false);
  const kindRef = useRef<BackupOpKind>(null);
  const onSettledRef = useRef<(() => void) | null>(null);
  kindRef.current = kind;

  const setOnSettled = useCallback((fn: (() => void) | null) => {
    onSettledRef.current = fn;
  }, []);

  const notifySettled = useCallback(() => {
    onSettledRef.current?.();
  }, []);

  const syncFromServer = useCallback(async () => {
    try {
      const status = await backupApi.getStatus();
      if (localOwnedRef.current) {
        return;
      }
      if (status.busy) {
        setKind((prev) => prev ?? mapServerOperation(status.operation));
      } else {
        setKind((prev) => (prev === "upload" ? prev : null));
        setRestoreTarget(null);
      }
    } catch {
      // Status is best-effort; ignore transient / permission errors.
    }
  }, []);

  const beginLocal = useCallback((next: BackupOpKind) => {
    if (localOwnedRef.current || kindRef.current !== null) {
      return false;
    }
    localOwnedRef.current = true;
    setKind(next);
    return true;
  }, []);

  const createBackup = useCallback(
    async (options: CreateBackupOptions) => {
      if (!beginLocal("create")) return false;
      try {
        await backupApi.createBackup(options);
        message.success(t("backup.createSuccess"));
        notifySettled();
        return true;
      } catch (err: unknown) {
        message.error(apiErrorMessage(err, t("backup.createFailed"), t));
        return false;
      } finally {
        localOwnedRef.current = false;
        setKind(null);
        void syncFromServer();
      }
    },
    [beginLocal, message, notifySettled, syncFromServer, t],
  );

  const runAutoBackup = useCallback(async () => {
    if (!beginLocal("auto")) return false;
    try {
      await backupApi.runAutoBackup();
      message.success(t("backup.autoRunSuccess"));
      notifySettled();
      return true;
    } catch (err: unknown) {
      message.error(apiErrorMessage(err, t("backup.autoRunFailed"), t));
      return false;
    } finally {
      localOwnedRef.current = false;
      setKind(null);
      void syncFromServer();
    }
  }, [beginLocal, message, notifySettled, syncFromServer, t]);

  const restoreBackup = useCallback(
    async (name: string, restoreConfig: boolean) => {
      if (!beginLocal("restore")) return false;
      setRestoreTarget(name);
      try {
        const result = await backupApi.restoreBackup(name, restoreConfig);
        message.success(
          t("backup.importSuccess", {
            agents: result.agents,
            files: result.workspace_files,
          }),
        );
        notifySettled();
        return true;
      } catch (err: unknown) {
        message.error(apiErrorMessage(err, t("backup.importFailed"), t));
        return false;
      } finally {
        localOwnedRef.current = false;
        setKind(null);
        setRestoreTarget(null);
        void syncFromServer();
      }
    },
    [beginLocal, message, notifySettled, syncFromServer, t],
  );

  const uploadBackup = useCallback(
    async (file: File) => {
      if (!beginLocal("upload")) return false;
      setUploadPercent(0);
      try {
        await backupApi.uploadBackup(file, (p) => setUploadPercent(p));
        setUploadPercent(100);
        message.success(t("backup.uploadSuccess", { name: file.name }));
        notifySettled();
        return true;
      } catch (err: unknown) {
        const detail = err instanceof Error ? err.message : String(err);
        message.error(detail || t("backup.uploadFailed"));
        return false;
      } finally {
        localOwnedRef.current = false;
        setKind(null);
        setUploadPercent(null);
      }
    },
    [beginLocal, message, notifySettled, t],
  );

  const creating = kind === "create" || kind === "export";
  const restoring = kind === "restore";
  const autoRunning = kind === "auto";
  const busy = kind !== null;

  const value = useMemo<BackupOperationContextValue>(
    () => ({
      kind,
      restoreTarget,
      uploadPercent,
      busy,
      creating,
      restoring,
      autoRunning,
      createBackup,
      runAutoBackup,
      restoreBackup,
      uploadBackup,
      syncFromServer,
      setOnSettled,
    }),
    [
      kind,
      restoreTarget,
      uploadPercent,
      busy,
      creating,
      restoring,
      autoRunning,
      createBackup,
      runAutoBackup,
      restoreBackup,
      uploadBackup,
      syncFromServer,
      setOnSettled,
    ],
  );

  return (
    <BackupOperationContext.Provider value={value}>
      {children}
    </BackupOperationContext.Provider>
  );
}

export function useBackupOperation(): BackupOperationContextValue {
  const ctx = useContext(BackupOperationContext);
  if (!ctx) {
    throw new Error(
      "useBackupOperation must be used within BackupOperationProvider",
    );
  }
  return ctx;
}
