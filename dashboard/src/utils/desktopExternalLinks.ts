const INSTALL_FLAG = "__OCTOP_EXTERNAL_LINKS_INSTALLED__";
const OPEN_URL_EVENT_PREFIX = "desktop:open-url:";

type DesktopWindow = Window & {
  __OCTOP_EXTERNAL_LINKS_INSTALLED__?: boolean;
  _wails?: { invoke?: (message: string) => void };
};

export function isDesktopExternalURL(
  raw: string,
  base = window.location.href,
): boolean {
  try {
    const parsed = new URL(raw, base);
    const scheme = parsed.protocol.replace(":", "").toLowerCase();
    if (scheme === "mailto") {
      return Boolean(parsed.pathname || parsed.href.slice("mailto:".length));
    }
    return scheme === "http" || scheme === "https";
  } catch {
    return false;
  }
}

function wailsInvoke(): ((message: string) => void) | undefined {
  const invoke = (window as DesktopWindow)._wails?.invoke;
  return typeof invoke === "function" ? invoke : undefined;
}

let lastUrl = "";
let lastAt = 0;

function openExternal(url: string): boolean {
  const invoke = wailsInvoke();
  if (!invoke || !isDesktopExternalURL(url)) return false;
  const now = Date.now();
  if (url === lastUrl && now - lastAt < 800) return true;
  lastUrl = url;
  lastAt = now;
  invoke("wails:event:emit:" + OPEN_URL_EVENT_PREFIX + encodeURIComponent(url));
  return true;
}

function linkFromEvent(event: Event): HTMLAnchorElement | null {
  const raw = event.target;
  const node =
    raw instanceof Element
      ? raw
      : raw instanceof Node
      ? raw.parentElement
      : null;
  if (!node) return null;
  const link = node.closest("a[href][target]");
  if (!(link instanceof HTMLAnchorElement)) return null;
  if (link.target.toLowerCase() !== "_blank") return null;
  if (link.hasAttribute("download")) return null;
  return link;
}

function onActivate(event: Event): void {
  if (event instanceof MouseEvent && event.button !== 0) return;
  const link = linkFromEvent(event);
  if (!link) return;
  if (!openExternal(link.href)) return;
  event.preventDefault();
}

function patchWindowOpen(): () => void {
  const original = window.open.bind(window);
  window.open = ((url?: string | URL, target?: string, features?: string) => {
    const href = url == null ? "" : String(url);
    const name = target == null ? "_blank" : String(target);
    if (href && name.toLowerCase() === "_blank" && openExternal(href)) {
      return null;
    }
    return original(url, target, features);
  }) as typeof window.open;
  return () => {
    window.open = original;
  };
}

export function tryInstallDesktopExternalLinks(): (() => void) | undefined {
  const w = window as DesktopWindow;
  if (!wailsInvoke() || w[INSTALL_FLAG]) return undefined;
  w[INSTALL_FLAG] = true;
  document.addEventListener("click", onActivate, true);
  document.addEventListener("pointerdown", onActivate, true);
  const restoreOpen = patchWindowOpen();
  return () => {
    document.removeEventListener("click", onActivate, true);
    document.removeEventListener("pointerdown", onActivate, true);
    restoreOpen();
    w[INSTALL_FLAG] = false;
  };
}

export function installDesktopExternalLinks(): () => void {
  let cancelled = false;
  let uninstall: (() => void) | undefined;
  const tryInstall = () => {
    if (cancelled || uninstall) return;
    uninstall = tryInstallDesktopExternalLinks();
  };
  tryInstall();
  const timer = window.setInterval(tryInstall, 250);
  window.setTimeout(() => window.clearInterval(timer), 12_000);
  return () => {
    cancelled = true;
    window.clearInterval(timer);
    uninstall?.();
  };
}
