import { app, BrowserWindow, dialog, ipcMain, net, protocol, shell } from "electron";
import { spawn } from "node:child_process";
import { promises as fs } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

import {
  IPC_CHANNELS,
  type ClientSettings,
  type IssuedSession,
  type PlatformInfo,
  type UpdateCheckResult,
  type WindowControlAction,
} from "../shared/ipc-contract";
import { resolveAppVersion } from "./app-version";
import { DeviceCredentialStore } from "./session/device-credential";
import { DeviceSessionClient } from "./session/device-session";
import { safeStorageCipher, warnIfKeychainUnavailable } from "./session/safe-storage-cipher";
import { ClientSettingsStore, defaultClientSettingsPath } from "./storage/client-settings";
import { readLoginShellEnv, resolveOctopHome } from "./supervisor/shell-env";
import { reserveRandomPort } from "./supervisor/random-port";
import { classifyRuntime, extractPortableZip, type BundledPortable, type LocalRuntime } from "./supervisor/runtime-extractor";
import { compareVersions } from "./supervisor/version";
import { sha256File } from "./supervisor/sha256";
import { buildSidecarEnv } from "./supervisor/process-tree";
import { SidecarSupervisor } from "./supervisor/sidecar";
import { contentTypeFor, isExternalLink, resolveStaticPath } from "./protocol/static-handler";
import { isApiPath, sanitizeForwardHeaders, toBackendUrl } from "./protocol/stream-proxy";
import {
  platformAssetKey,
  selectRelease,
  type DownloadManifest,
  type SelectedRelease,
} from "./update/update-coordinator";
import { downloadToFile } from "./update/download";
import { installUpdate, type InstallOutcome, type InstallerKind } from "./update/installer";
import { createEarlyWindow, showEarlyWindowError } from "./windows/early-window";
import { createMainWindow } from "./windows/main-window";

const UPDATE_ENDPOINT = "https://octop.cloud/api/downloads";
const PRELOAD_PATH = join(__dirname, "../preload/index.js");
const SPLASH_PATH = join(__dirname, "../renderer/splash.html");

interface PortableManifestFile {
  version: string;
  sha256: string;
}

let supervisor: SidecarSupervisor | null = null;
let settingsStore: ClientSettingsStore;
// §7 accounts: renews the Dashboard session without a password. Registered by
// the renderer once it holds a JWT; used whenever that JWT has expired.
let deviceSession: DeviceSessionClient | null = null;
// Resolved after `whenReady` — `app.getVersion()` must not run at module load.
let appVersion = "";
// §6.3 step 1: once an install is under way the proxy answers 503 so no new API
// request is admitted while Python shuts down.
let apiAdmissionClosed = false;
let updateInFlight = false;
// Current loopback port of the sidecar. Read per request (not captured), so a
// restart after a failed install can hand the proxy a new port.
let backendPort = 0;
// Everything needed to (re)spawn the sidecar for this launch.
let backend: {
  interpreter: string;
  launchScript: string;
  cwd: string;
  octopHome: string;
  portableDir: string;
} | null = null;

// A custom scheme used as the renderer origin must be declared privileged
// BEFORE the app is ready, otherwise `octop://app/` is not treated as a
// standard/secure origin and fetch/XHR/CORS break.
protocol.registerSchemesAsPrivileged([
  {
    scheme: "octop",
    privileges: {
      standard: true,
      secure: true,
      supportFetchAPI: true,
      stream: true,
      corsEnabled: true,
    },
  },
]);

function resourcesRoot(): string {
  return app.isPackaged ? process.resourcesPath : join(__dirname, "../../resources");
}

function dashboardRoot(): string {
  return process.env.OCTOP_DASHBOARD_DIR ?? join(resourcesRoot(), "dashboard");
}

/** Map to the green-pack naming used by desktop/portable (`darwin-arm64`, …). */
function portablePlatformTag(): string {
  const arch = process.arch === "arm64" ? "arm64" : "amd64";
  if (process.platform === "darwin") return `darwin-${arch}`;
  if (process.platform === "win32") return `windows-${arch}`;
  return `linux-${arch}`;
}

function portableZipPath(): string {
  // The CI step places the exact platform/version zip at resources/portable.
  const dir = join(resourcesRoot(), "portable");
  return join(dir, `Octop-portable-${portablePlatformTag()}-${appVersion}.zip`);
}

async function readBundledPortable(): Promise<BundledPortable> {
  const manifest = JSON.parse(
    await fs.readFile(join(resourcesRoot(), "portable", "portable-version.json"), "utf8"),
  ) as PortableManifestFile;
  return { version: manifest.version, sha256: manifest.sha256 };
}

async function readLocalRuntime(octopHome: string): Promise<LocalRuntime> {
  const versionPath = join(octopHome, "portable", "version.json");
  let version: string | null = null;
  try {
    const raw = JSON.parse(await fs.readFile(versionPath, "utf8")) as { version?: unknown };
    version = typeof raw.version === "string" ? raw.version : null;
  } catch {
    version = null;
  }
  const interpreterPath = join(octopHome, "portable", "runtime", process.platform === "win32" ? "python.exe" : "bin/python3");
  let interpreterExists = false;
  try {
    await fs.access(interpreterPath);
    interpreterExists = true;
  } catch {
    interpreterExists = false;
  }
  return { version, interpreterExists };
}

/**
 * The one product version (shell + Dashboard + runtime share a release). Read
 * the bundled portable manifest first, then the dev runtime, and only then fall
 * back to `package.json` — see `app-version.ts` for why the placeholder there
 * must not win.
 */
async function resolveProductVersion(): Promise<string> {
  return resolveAppVersion({
    readBundled: async () => (await readBundledPortable()).version,
    readDevRuntime: async () => {
      const dir = (process.env.OCTOP_PORTABLE_DIR ?? "").trim();
      if (!dir) return null;
      const raw = JSON.parse(await fs.readFile(join(dir, "version.json"), "utf8")) as {
        version?: unknown;
      };
      return typeof raw.version === "string" ? raw.version : null;
    },
    readPackage: () => app.getVersion(),
  });
}

async function writeLocalVersion(octopHome: string, version: string): Promise<void> {
  const dir = join(octopHome, "portable");
  await fs.mkdir(dir, { recursive: true });
  await fs.writeFile(join(dir, "version.json"), JSON.stringify({ version, sha256: "" }, null, 2), "utf8");
}

function registerProtocol(staticRootDir: string): void {
  protocol.handle("octop", async (request) => {
    const url = new URL(request.url);
    const pathname = url.pathname;

    if (isApiPath(pathname)) {
      if (apiAdmissionClosed) return new Response("update in progress", { status: 503 });
      const target = toBackendUrl(backendPort, pathname, url.search);
      const headers = sanitizeForwardHeaders(request.headers);
      headers["x-octop-proxy"] = "1";
      return net.fetch(target, {
        method: request.method,
        headers,
        body: ["GET", "HEAD"].includes(request.method) ? undefined : request.body,
        // @ts-expect-error duplex is required for streaming request bodies in undici
        duplex: "half",
      });
    }

    const filePath = resolveStaticPath(staticRootDir, pathname);
    if (!filePath) return new Response("forbidden", { status: 403 });
    // Serve via file URL so large assets stream instead of buffering in memory.
    return net.fetch(pathToFileURL(filePath).toString()).then((res) => {
      const out = new Response(res.body, { status: res.status, headers: res.headers });
      if (!out.headers.get("content-type")) out.headers.set("content-type", contentTypeFor(filePath));
      return out;
    });
  });
}

async function resolveSelectedRelease(): Promise<SelectedRelease | null> {
  const settings = settingsStore.load();
  const res = await net.fetch(UPDATE_ENDPOINT, { cache: "no-store" });
  if (!res.ok) throw new Error(`downloads endpoint returned ${res.status}`);
  const manifest = (await res.json()) as DownloadManifest;
  return selectRelease(
    manifest,
    appVersion,
    platformAssetKey(process.platform, process.arch),
    settings.stableOnly,
  );
}

function errorMessageOf(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

/** A JWT the shell will forward: non-empty, bounded, nothing else assumed. */
function isUsableAccessToken(value: unknown): value is string {
  return typeof value === "string" && value.length > 0 && value.length <= 4096;
}

async function showShellMessage(
  win: BrowserWindow | null,
  message: string,
  detail: string,
): Promise<void> {
  const options = { type: "info" as const, buttons: ["好"], message, detail, noLink: true };
  if (win) await dialog.showMessageBox(win, options);
  else await dialog.showMessageBox(options);
}

async function showShellError(
  win: BrowserWindow | null,
  message: string,
  detail: string,
): Promise<void> {
  const options = {
    type: "error" as const,
    buttons: ["好"],
    message,
    detail,
    noLink: true,
  };
  if (win) await dialog.showMessageBox(win, options);
  else await dialog.showMessageBox(options);
}

async function confirmInstall(win: BrowserWindow | null, selected: SelectedRelease): Promise<boolean> {
  const options = {
    type: "question" as const,
    buttons: ["立即升级", "稍后"],
    defaultId: 0,
    cancelId: 1,
    noLink: true,
    message: `发现新版本 ${selected.tag}`,
    detail:
      `当前版本 ${appVersion}。升级会下载安装包，然后退出并由安装程序替换客户端；` +
      `数据库、工作区和配置都会保留。`,
  };
  const { response } = win
    ? await dialog.showMessageBox(win, options)
    : await dialog.showMessageBox(options);
  return response === 0;
}

/** Temp staging area for installers — never inside OCTOP_HOME (user data). */
function updateDownloadDir(): string {
  return join(app.getPath("temp"), "octop-update");
}

async function handOffToInstaller(kind: InstallerKind, path: string): Promise<void> {
  if (kind === "appimage") await fs.chmod(path, 0o755);
  if (process.platform === "win32" && (kind === "exe" || kind === "msi")) {
    // NSIS/MSI must replace the running shell: start the installer detached and
    // let this process exit right after (§6.3 step 3).
    spawn(path, [], { detached: true, stdio: "ignore" }).unref();
    return;
  }
  const failure = await shell.openPath(path);
  if (failure) throw new Error(failure);
}

/** Stop Python cleanly and restart it when the installer never took over. */
async function restartBackend(win: BrowserWindow | null): Promise<void> {
  apiAdmissionClosed = false;
  const ready = await startBackend();
  if (ready) win?.webContents.reload();
}

async function runShellUpdate(
  win: BrowserWindow | null,
  selected: SelectedRelease,
): Promise<InstallOutcome> {
  updateInFlight = true;
  try {
    const dir = updateDownloadDir();
    // Start from an empty staging dir so an aborted earlier attempt cannot be
    // mistaken for (or re-used as) this download.
    await fs.rm(dir, { recursive: true, force: true });
    await fs.mkdir(dir, { recursive: true });
    return await installUpdate(selected, {
      download: async (plan) => {
        const dest = join(dir, plan.filename);
        await downloadToFile(plan.url, dest, net.fetch, {
          onProgress: (received, total) => {
            if (total > 0) win?.setProgressBar(received / total);
          },
        });
        return dest;
      },
      // §6.1 assets carry no digest; the URL is already pinned to https on
      // download.octop.cloud by isValidAssetUrl() before it reaches this point.
      verify: async () => true,
      stopSidecar: async () => {
        // §6.3 step 1 — refuse new API admissions, then ask Python to exit.
        apiAdmissionClosed = true;
        if (!supervisor) return { clean: true, exitCode: null };
        return supervisor.stop();
      },
      handOff: handOffToInstaller,
      onHandOffFailure: async () => {
        await restartBackend(win);
      },
    });
  } finally {
    win?.setProgressBar(-1);
    updateInFlight = false;
  }
}

function registerIpcHandlers(): void {
  ipcMain.handle(IPC_CHANNELS.getPlatformInfo, (): PlatformInfo => ({
    platform: process.platform as PlatformInfo["platform"],
    arch: process.arch,
    isDesktop: true,
  }));

  ipcMain.handle(IPC_CHANNELS.clientSettingsGet, (): ClientSettings => settingsStore.load());
  ipcMain.handle(IPC_CHANNELS.clientSettingsSet, (_e, patch: Partial<ClientSettings>) =>
    settingsStore.save(patch),
  );

  ipcMain.handle(IPC_CHANNELS.checkForUpdates, async (): Promise<UpdateCheckResult> => {
    try {
      const selected = await resolveSelectedRelease();
      if (!selected) return { status: "up-to-date", currentVersion: appVersion, latestVersion: null, error: null };
      return {
        status: "update-available",
        currentVersion: appVersion,
        latestVersion: selected.tag,
        error: null,
      };
    } catch (err) {
      return {
        status: "error",
        currentVersion: appVersion,
        latestVersion: null,
        error: errorMessageOf(err),
      };
    }
  });

  ipcMain.handle(IPC_CHANNELS.openUpdateConfirmation, async (event) => {
    // Deliberately ignores every argument: the renderer may only ASK for the
    // shell's confirmation dialog. It cannot pick the package URL, and it cannot
    // pre-authorize an install (§6.2).
    if (updateInFlight) return;
    const win = BrowserWindow.fromWebContents(event.sender) ?? BrowserWindow.getAllWindows()[0] ?? null;

    let selected: SelectedRelease | null;
    try {
      selected = await resolveSelectedRelease();
    } catch (err) {
      await showShellError(win, "检查更新失败", errorMessageOf(err));
      return;
    }
    if (!selected) {
      await showShellMessage(win, "已是最新版本", `当前版本 ${appVersion}。`);
      return;
    }
    if (!(await confirmInstall(win, selected))) return;

    const outcome = await runShellUpdate(win, selected);
    if (!outcome.ok) {
      await showShellError(win, "升级失败", outcome.message);
      return;
    }
    // §6.3 step 3: the installer owns the rest — hand it our exit.
    app.quit();
  });

  ipcMain.handle(IPC_CHANNELS.sessionRegister, (_event, accessToken: unknown): Promise<boolean> => {
    if (!isUsableAccessToken(accessToken)) return Promise.resolve(false);
    return deviceSession?.register(accessToken) ?? Promise.resolve(false);
  });

  ipcMain.handle(IPC_CHANNELS.sessionRenew, (): Promise<IssuedSession | null> => {
    return deviceSession?.renew() ?? Promise.resolve(null);
  });

  ipcMain.handle(IPC_CHANNELS.sessionRevoke, (_event, accessToken: unknown): Promise<boolean> => {
    if (!isUsableAccessToken(accessToken)) return Promise.resolve(false);
    return deviceSession?.revoke(accessToken) ?? Promise.resolve(false);
  });

  ipcMain.on(IPC_CHANNELS.windowControl, (event, action: WindowControlAction) => {
    const win = BrowserWindow.fromWebContents(event.sender);
    if (!win) return;
    if (action === "minimize") win.minimize();
    else if (action === "maximize") win.isMaximized() ? win.unmaximize() : win.maximize();
    else if (action === "close") win.close();
  });
}

/** Spawn the Python sidecar on a fresh loopback port and wait for health. */
async function startBackend(): Promise<boolean> {
  if (!backend) return false;
  const port = await reserveRandomPort();
  const env = buildSidecarEnv(process.env, {
    octopHome: backend.octopHome,
    portableDir: backend.portableDir,
    port,
    bindHost: "127.0.0.1",
  });
  backendPort = port;
  supervisor = new SidecarSupervisor({
    executable: backend.interpreter,
    args: [backend.launchScript, "run"],
    env,
    cwd: backend.cwd,
    port,
  });
  supervisor.start();
  return supervisor.waitUntilReady();
}

async function boot(): Promise<void> {
  const gotLock = app.requestSingleInstanceLock();
  if (!gotLock) {
    app.quit();
    return;
  }

  appVersion = await resolveProductVersion();

  settingsStore = new ClientSettingsStore(defaultClientSettingsPath(app.getPath("userData")));
  const settings = settingsStore.load();

  const early = createEarlyWindow({
    splashFile: SPLASH_PATH,
  });

  // Resolve OCTOP_HOME, reading the login shell on macOS/Linux (GUI apps don't
  // inherit it). The extraction dir and the child env must agree on one root.
  const loginShellEnv =
    process.platform === "win32" ? {} : await readLoginShellEnv(process.env.SHELL);
  const octopHome = resolveOctopHome(process.env, loginShellEnv);

  // Local dev escape hatch: point at an already-extracted runtime (e.g. the one
  // `pnpm dev:runtime` writes to .dev-runtime) and skip bundling/extraction.
  const devPortableDir = (process.env.OCTOP_PORTABLE_DIR ?? "").trim();
  const portableDir = devPortableDir || join(octopHome, "portable");

  // Runtime version guard (§2.3) — must run BEFORE spawning Python.
  if (!devPortableDir) {
    try {
      const bundled = await readBundledPortable();
      const local = await readLocalRuntime(octopHome);
      const decision = classifyRuntime(bundled, local, compareVersions);

      if (decision.action === "stop") {
        showEarlyWindowError(
          early,
          `检测到本机运行时版本为 ${decision.localVersion}，当前安装的是 ${bundled.version}。这是手动覆盖安装的旧版，已停止启动，并保留了现有运行时。`,
        );
        return;
      }

      if (decision.action === "extract" || decision.action === "replace") {
        const zip = portableZipPath();
        const digest = await sha256File(zip);
        if (digest !== bundled.sha256) {
          showEarlyWindowError(early, `便携运行时校验失败（SHA-256 不匹配），已停止启动。`);
          return;
        }
        extractPortableZip(zip, portableDir);
        await writeLocalVersion(octopHome, bundled.version);
      }
    } catch (err) {
      showEarlyWindowError(
        early,
        err instanceof Error ? err.message : String(err),
      );
      return;
    }
  }

  const interpreter = join(portableDir, "runtime", process.platform === "win32" ? "python.exe" : "bin/python3");
  backend = {
    interpreter,
    launchScript: join(portableDir, "launch.py"),
    cwd: portableDir,
    octopHome,
    portableDir,
  };

  // §7 accounts: the device credential lives in the data root, next to the
  // database it unlocks, and only the main process ever sees it.
  const cipher = safeStorageCipher();
  warnIfKeychainUnavailable(cipher);
  deviceSession = new DeviceSessionClient({
    store: new DeviceCredentialStore(octopHome, cipher),
    baseUrl: () => (apiAdmissionClosed || !backendPort ? null : `http://127.0.0.1:${backendPort}`),
    label: `${process.platform}-${process.arch}`,
  });

  registerProtocol(dashboardRoot());
  registerIpcHandlers();

  const ready = await startBackend();
  if (!ready) {
    showEarlyWindowError(
      early,
      "Python 后端未能就绪（健康检查超时或进程提前退出）。请查看日志后重试。",
    );
    return;
  }

  // Swap the Early Window for the real Dashboard (in-place mount, no white flash).
  const mainWindow = createMainWindow({
    preload: PRELOAD_PATH,
    backgroundColor: settings.themeBackground === "dark" ? "#111827" : "#ffffff",
    onNavigate: (url) => {
      if (isExternalLink(url)) void shell.openExternal(url);
    },
  });
  early.close();
  mainWindow.webContents.on("did-finish-load", () => {
    mainWindow.webContents.send(IPC_CHANNELS.onBackendReady, { ok: true });
  });
}

app.whenReady().then(boot).catch((err) => {
  console.error("octop-desktop boot failed", err);
  app.quit();
});

app.on("second-instance", () => {
  const [win] = BrowserWindow.getAllWindows();
  if (win) {
    if (win.isMinimized()) win.restore();
    win.focus();
  }
});

let quitting = false;

app.on("before-quit", (event) => {
  if (quitting || !supervisor) return;
  // §3.4: the sidecar runs in its own process group, so quitting without
  // waiting would orphan Python. Give it the grace window, then really quit.
  event.preventDefault();
  quitting = true;
  void supervisor.stop().finally(() => app.quit());
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

/**
 * Terminal Ctrl+C, `kill`, an IDE stop button and a service manager all send a
 * signal rather than a quit event, and the default action kills the shell
 * outright — `before-quit` never runs, so the sidecar survives as an orphan.
 * Python is spawned detached (§3.1) precisely so it is not in the terminal's
 * process group, which means the shell is the only one who can reap it.
 */
let signalReceived = 0;

async function shutdownFromSignal(signal: NodeJS.Signals): Promise<void> {
  signalReceived += 1;
  if (signalReceived > 1) {
    // Second Ctrl+C: the user wants out now, do not wait for the grace window.
    app.exit(0);
    return;
  }
  console.warn(`[desktop] ${signal} received — stopping the Python sidecar…`);
  // Keep `before-quit` from preventDefault-ing into a second stop attempt; the
  // exit below is deliberate and must not be deferred again.
  quitting = true;
  try {
    await supervisor?.stop();
  } catch (err) {
    console.error("octop-desktop shutdown failed", err);
  } finally {
    // `app.exit` skips `before-quit`/`will-quit`, so nothing can keep the
    // process alive after Python is gone.
    app.exit(0);
  }
}

for (const signal of ["SIGINT", "SIGTERM", "SIGHUP"] as const) {
  // Ctrl+C in a dev terminal is a normal way to stop the app, so exit 0 instead
  // of 130: pnpm prints "ELIFECYCLE Command failed" for non-zero exits.
  process.on(signal, () => void shutdownFromSignal(signal));
}
