import { useEffect, useState, useSyncExternalStore } from "react";
import {
  subscribePwaPrompt,
  getPwaInstallSnapshot,
  triggerInstall,
  waitForInstallPrompt,
} from "../../pwa-prompt";
import {
  DesktopInstallGuide,
  IosGuide,
} from "../../components/PwaInstallPrompt";
import { copyText } from "../../utils/copyText";

interface CheckItem {
  id: string;
  label: string;
  status: "pass" | "fail" | "warn" | "loading" | "info";
  detail: string;
}

function StatusDot({ status }: { status: CheckItem["status"] }) {
  const colors: Record<string, string> = {
    pass: "#22c55e",
    fail: "#ef4444",
    warn: "#f59e0b",
    loading: "#94a3b8",
    info: "#60a5fa",
  };
  const labels: Record<string, string> = {
    pass: "✓",
    fail: "✗",
    warn: "!",
    loading: "…",
    info: "i",
  };
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        width: 22,
        height: 22,
        borderRadius: "50%",
        background: colors[status],
        color: "#fff",
        fontSize: 12,
        fontWeight: 700,
        flexShrink: 0,
      }}
    >
      {labels[status]}
    </span>
  );
}

export default function PwaDebugPage() {
  const [checks, setChecks] = useState<CheckItem[]>([]);
  const [swLog, setSwLog] = useState<string[]>([]);
  const [copied, setCopied] = useState(false);
  const [forceInstalling, setForceInstalling] = useState(false);
  const [showManualGuide, setShowManualGuide] = useState(false);
  const [showIosGuide, setShowIosGuide] = useState(false);
  const [isIos] = useState(
    () =>
      /iphone|ipad|ipod/i.test(navigator.userAgent) ||
      (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1),
  );
  const installSnap = useSyncExternalStore(
    subscribePwaPrompt,
    getPwaInstallSnapshot,
  );

  useEffect(() => {
    const items: CheckItem[] = [];
    const log: string[] = [];

    // ── 1. Protocol ──────────────────────────────────────────────
    const isHttps =
      location.protocol === "https:" || location.hostname === "localhost";
    items.push({
      id: "https",
      label: "HTTPS / localhost",
      status: isHttps ? "pass" : "fail",
      detail: location.protocol + "//" + location.hostname,
    });
    log.push(`protocol: ${location.protocol}  host: ${location.hostname}`);

    // ── 2. Service Worker support ────────────────────────────────
    const swSupported = "serviceWorker" in navigator;
    items.push({
      id: "sw-support",
      label: "Service Worker 支持",
      status: swSupported ? "pass" : "fail",
      detail: swSupported ? "支持" : "浏览器不支持 SW",
    });
    log.push(`SW support: ${swSupported}`);

    // ── 3. SW registration state ─────────────────────────────────
    if (swSupported) {
      navigator.serviceWorker
        .getRegistration("/")
        .then((reg) => {
          if (!reg) {
            setChecks((prev) => [
              ...prev,
              {
                id: "sw-reg",
                label: "SW 注册状态",
                status: "fail",
                detail: "未找到任何 Service Worker 注册",
              },
            ]);
            log.push("SW registration: NONE");
          } else {
            const state = reg.active
              ? "active"
              : reg.installing
              ? "installing"
              : reg.waiting
              ? "waiting"
              : "unknown";
            const scope = reg.scope;
            setChecks((prev) => [
              ...prev,
              {
                id: "sw-reg",
                label: "SW 注册状态",
                status: state === "active" ? "pass" : "warn",
                detail: `scope: ${scope}  state: ${state}`,
              },
            ]);
            log.push(`SW reg scope: ${scope}  state: ${state}`);

            // ── 4. SW controlling ──────────────────────────────────
            const controlled = !!navigator.serviceWorker.controller;
            setChecks((prev) => [
              ...prev,
              {
                id: "sw-control",
                label: "SW 控制当前页面",
                status: controlled ? "pass" : "warn",
                detail: controlled
                  ? `controller: ${navigator.serviceWorker.controller?.scriptURL}`
                  : "SW 未控制当前页面（需刷新或 clientsClaim）",
              },
            ]);
            log.push(
              `SW controller: ${
                navigator.serviceWorker.controller?.scriptURL ?? "none"
              }`,
            );
          }
        })
        .catch((e) => {
          setChecks((prev) => [
            ...prev,
            {
              id: "sw-reg",
              label: "SW 注册状态",
              status: "fail",
              detail: `Error: ${e.message}`,
            },
          ]);
        });
    }

    // ── 5. Manifest fetch ────────────────────────────────────────
    fetch("/manifest.json")
      .then(async (res) => {
        const ct = res.headers.get("content-type") ?? "";
        let detail = `HTTP ${res.status}  Content-Type: ${ct}`;
        let status: CheckItem["status"] = "fail";
        if (res.ok) {
          try {
            const json = await res.json();
            const hasName = !!json.name;
            const hasIcons = Array.isArray(json.icons) && json.icons.length > 0;
            const hasStartUrl = !!json.start_url;
            const hasDisplay =
              json.display === "standalone" || json.display === "fullscreen";
            const allOk = hasName && hasIcons && hasStartUrl && hasDisplay;
            status = allOk ? "pass" : "warn";
            detail = `HTTP ${res.status} | name:${hasName} icons:${hasIcons} start_url:${hasStartUrl} display:${json.display} | CT:${ct}`;
            log.push(
              `manifest: ${JSON.stringify({
                name: json.name,
                display: json.display,
                icons: json.icons?.length,
                id: json.id,
              })}`,
            );

            // Chrome installability requires icon pixels to match manifest sizes.
            const icons = Array.isArray(json.icons) ? json.icons : [];
            void Promise.all(
              icons.map(async (icon: { src?: string; sizes?: string }) => {
                const src = icon.src;
                const sizes = icon.sizes ?? "";
                if (!src || !sizes || sizes === "any") return null;
                const [w, h] = sizes.split("x").map(Number);
                if (!w || !h) return null;
                try {
                  const img = new Image();
                  const loaded = await new Promise<boolean>((resolve) => {
                    img.onload = () => resolve(true);
                    img.onerror = () => resolve(false);
                    img.src = src.startsWith("/") ? src : `/${src}`;
                  });
                  if (!loaded) {
                    return `${src}: 加载失败`;
                  }
                  if (img.naturalWidth !== w || img.naturalHeight !== h) {
                    return `${src}: 声明 ${sizes}，实际 ${img.naturalWidth}x${img.naturalHeight}`;
                  }
                  return null;
                } catch {
                  return `${src}: 校验异常`;
                }
              }),
            ).then((mismatches) => {
              const bad = mismatches.filter(Boolean) as string[];
              if (bad.length === 0) {
                setChecks((prev) => [
                  ...prev,
                  {
                    id: "icon-sizes",
                    label: "图标尺寸与 manifest 一致",
                    status: "pass",
                    detail: `已校验 ${icons.length} 个图标`,
                  },
                ]);
                log.push("icon sizes: all match manifest");
              } else {
                setChecks((prev) => [
                  ...prev,
                  {
                    id: "icon-sizes",
                    label: "图标尺寸与 manifest 一致",
                    status: "fail",
                    detail: bad.join(" | "),
                  },
                ]);
                log.push(`icon size mismatch: ${bad.join("; ")}`);
              }
              setSwLog((prev) => [
                ...prev,
                bad.length === 0
                  ? "icon sizes: all match manifest"
                  : `icon size mismatch: ${bad.join("; ")}`,
              ]);
            });
          } catch {
            status = "fail";
            detail = `HTTP ${res.status} 但 JSON 解析失败`;
          }
        } else {
          detail = `HTTP ${res.status} — 被拦截或 404`;
          log.push(`manifest fetch failed: ${res.status} url=${res.url}`);
        }
        setChecks((prev) => [
          ...prev,
          { id: "manifest", label: "manifest.json 可访问", status, detail },
        ]);
      })
      .catch((e) => {
        const detail = `fetch 失败: ${e.message}（可能被认证代理拦截）`;
        log.push(`manifest fetch error: ${e.message}`);
        setChecks((prev) => [
          ...prev,
          {
            id: "manifest",
            label: "manifest.json 可访问",
            status: "fail",
            detail,
          },
        ]);
      });

    // ── 6. sw.js fetch ───────────────────────────────────────────
    // Use GET + abort so HEAD 405 (some servers block HEAD) doesn't cause false fail.
    const swAbort = new AbortController();
    fetch("/sw.js", { signal: swAbort.signal })
      .then((res) => {
        swAbort.abort();
        const cc = res.headers.get("cache-control") ?? "(none)";
        const ct = res.headers.get("content-type") ?? "(none)";
        const status: CheckItem["status"] = res.ok
          ? cc.includes("no-cache") || cc.includes("no-store")
            ? "pass"
            : "warn"
          : "fail";
        const detail = `HTTP ${res.status} | Cache-Control: ${cc} | Content-Type: ${ct}`;
        log.push(`sw.js: ${detail}`);
        setChecks((prev) => [
          ...prev,
          { id: "sw-fetch", label: "sw.js 可访问且无强缓存", status, detail },
        ]);
      })
      .catch((e) => {
        if (e.name === "AbortError") return;
        setChecks((prev) => [
          ...prev,
          {
            id: "sw-fetch",
            label: "sw.js 可访问且无强缓存",
            status: "fail",
            detail: `fetch 失败: ${e.message}`,
          },
        ]);
      });

    // ── 7. beforeinstallprompt ───────────────────────────────────
    // Checked via useSyncExternalStore below, but add as static check here
    items.push({
      id: "bip",
      label: "beforeinstallprompt 状态",
      status: "info",
      detail: "见下方实时状态",
    });

    // ── 8. Standalone mode ───────────────────────────────────────
    const standalone =
      window.matchMedia("(display-mode: standalone)").matches ||
      (navigator as { standalone?: boolean }).standalone === true;
    items.push({
      id: "standalone",
      label: "当前运行模式",
      status: standalone ? "info" : "info",
      detail: standalone
        ? "standalone（已安装模式）"
        : "browser tab（浏览器标签页）",
    });
    log.push(`standalone: ${standalone}`);

    // ── 9. User Agent ────────────────────────────────────────────
    items.push({
      id: "ua",
      label: "User Agent",
      status: "info",
      detail: navigator.userAgent,
    });
    log.push(`UA: ${navigator.userAgent}`);

    // ── 10. dismissed flag ───────────────────────────────────────
    const dismissed = localStorage.getItem("pwa:install-dismissed");
    items.push({
      id: "dismissed",
      label: "用户已点过「不安装」",
      status: dismissed ? "warn" : "pass",
      detail: dismissed ? `已设置（清除方法见下方）` : "未设置",
    });
    log.push(`dismissed flag: ${dismissed ?? "not set"}`);

    setSwLog((prev) => [...prev, ...log]);
    setChecks((prev) => {
      // merge static items first, then async items will append
      const ids = new Set(prev.map((c) => c.id));
      return [...prev, ...items.filter((i) => !ids.has(i.id))];
    });
  }, []);

  const allChecks: CheckItem[] = [
    ...checks,
    {
      id: "bip-live",
      label: "beforeinstallprompt 已捕获",
      status: installSnap.prompt ? "pass" : "warn",
      detail: installSnap.prompt
        ? "✓ 事件已捕获，可触发安装"
        : "未捕获（Chrome 内部评估后未发送事件，可能在沉默期）",
    },
    {
      id: "swready-live",
      label: "前端 swReady 状态",
      status: installSnap.swReady ? "pass" : "warn",
      detail: installSnap.swReady
        ? `swReady=true（按钮应已显示）`
        : `swReady=false（pwa-prompt.ts 检测 SW 失败，按钮隐藏）`,
    },
  ];

  const handleClearDismissed = () => {
    localStorage.removeItem("pwa:install-dismissed");
    localStorage.removeItem("pwa:ios-guide-shown");
    alert("已清除，请刷新页面");
  };

  const handleCopyLog = () => {
    const text =
      allChecks
        .map((c) => `[${c.status.toUpperCase()}] ${c.label}: ${c.detail}`)
        .join("\n") +
      "\n\n--- raw log ---\n" +
      swLog.join("\n");
    void copyText(text).then((ok) => {
      if (!ok) return;
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  const handleInstall = async () => {
    const result = await triggerInstall();
    alert(`安装结果: ${result}`);
  };

  /** Best-effort install: clear local dismiss, wait for prompt, call prompt(). */
  const handleForceInstall = async () => {
    if (forceInstalling) return;
    setForceInstalling(true);
    setSwLog((prev) => [
      ...prev,
      "[force] 清除本地拒绝标记，尝试触发安装对话框…",
    ]);
    localStorage.removeItem("pwa:install-dismissed");
    localStorage.removeItem("pwa:ios-guide-shown");

    try {
      if (isIos) {
        setShowIosGuide(true);
        setSwLog((prev) => [
          ...prev,
          "[force] iOS 需手动「添加到主屏幕」，已打开引导",
        ]);
        return;
      }

      if (!getPwaInstallSnapshot().prompt) {
        setSwLog((prev) => [
          ...prev,
          "[force] 尚未捕获 beforeinstallprompt，等待 3 秒…",
        ]);
        await waitForInstallPrompt(3000);
      }

      const result = await triggerInstall();
      setSwLog((prev) => [...prev, `[force] triggerInstall → ${result}`]);

      if (result === "accepted") {
        alert("安装已接受，应用应出现在程序坞/启动台");
        return;
      }
      if (result === "dismissed") {
        alert("安装对话框已弹出，你选择了取消");
        return;
      }

      setSwLog((prev) => [
        ...prev,
        "[force] 浏览器未提供 programmatic install，打开手动安装引导",
      ]);
      setShowManualGuide(true);
    } finally {
      setForceInstalling(false);
    }
  };

  const handleWaitPrompt = async () => {
    setSwLog((prev) => [...prev, "[wait] 等待 beforeinstallprompt 8 秒..."]);
    const prompt = await waitForInstallPrompt(8000);
    setSwLog((prev) => [
      ...prev,
      prompt
        ? "[wait] ✓ 事件已捕获"
        : "[wait] ✗ 8 秒内未触发，Chrome 处于静默期或评估未通过",
    ]);
  };

  const handleResetPwa = async () => {
    if (
      !confirm(
        "将注销当前 Service Worker 并清空所有 PWA 状态。确定要重置吗？\n操作完成后会自动刷新页面。",
      )
    ) {
      return;
    }
    const regs = await navigator.serviceWorker.getRegistrations();
    for (const reg of regs) {
      await reg.unregister();
    }
    localStorage.removeItem("pwa:install-dismissed");
    localStorage.removeItem("pwa:ios-guide-shown");
    // Clear any cached PWA install decision so Chrome re-evaluates on next visit.
    if ("caches" in window) {
      const names = await caches.keys();
      for (const n of names) {
        if (n.toLowerCase().includes("workbox")) await caches.delete(n);
      }
    }
    setSwLog((prev) => [...prev, "[reset] SW 注销 + 缓存清理完成，即将刷新"]);
    setTimeout(() => location.reload(), 800);
  };

  return (
    <div
      style={{
        padding: "20px 16px 40px",
        maxWidth: 640,
        margin: "0 auto",
        fontFamily: "system-ui, sans-serif",
      }}
    >
      <h2
        style={{
          margin: "0 0 4px",
          fontSize: 20,
          fontWeight: 700,
          color: "var(--fn-text-primary)",
        }}
      >
        PWA 诊断
      </h2>
      <p
        style={{
          margin: "0 0 20px",
          fontSize: 13,
          color: "var(--fn-text-tertiary)",
        }}
      >
        在手机上访问此页面，查看 PWA 安装条件是否满足
      </p>

      {/* Check list */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: 10,
          marginBottom: 24,
        }}
      >
        {allChecks.map((c) => (
          <div
            key={c.id}
            style={{
              display: "flex",
              gap: 12,
              alignItems: "flex-start",
              padding: "10px 12px",
              borderRadius: 10,
              background: "var(--fn-bg-secondary, rgba(255,255,255,0.04))",
              border:
                "1px solid var(--fn-border-primary, rgba(255,255,255,0.07))",
            }}
          >
            <StatusDot status={c.status} />
            <div style={{ minWidth: 0 }}>
              <div
                style={{
                  fontSize: 13,
                  fontWeight: 600,
                  color: "var(--fn-text-primary)",
                  marginBottom: 2,
                }}
              >
                {c.label}
              </div>
              <div
                style={{
                  fontSize: 12,
                  color: "var(--fn-text-tertiary)",
                  wordBreak: "break-all",
                  lineHeight: 1.5,
                }}
              >
                {c.detail}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Actions */}
      <div
        style={{ display: "flex", flexWrap: "wrap", gap: 10, marginBottom: 24 }}
      >
        <button
          type="button"
          onClick={() => void handleForceInstall()}
          disabled={forceInstalling}
          style={{
            padding: "8px 16px",
            borderRadius: 999,
            border: "none",
            background: forceInstalling ? "#94a3b8" : "var(--fn-color-brand)",
            color: "#fff",
            fontSize: 13,
            fontWeight: 600,
            cursor: forceInstalling ? "not-allowed" : "pointer",
          }}
        >
          {forceInstalling ? "安装尝试中…" : "强制尝试安装"}
        </button>
        <button
          onClick={handleCopyLog}
          style={{
            padding: "8px 16px",
            borderRadius: 999,
            border: "1px solid var(--fn-border-primary)",
            background: "var(--fn-bg-tertiary)",
            color: "var(--fn-text-primary)",
            fontSize: 13,
            cursor: "pointer",
          }}
        >
          {copied ? "已复制 ✓" : "复制诊断报告"}
        </button>
        <button
          onClick={handleClearDismissed}
          style={{
            padding: "8px 16px",
            borderRadius: 999,
            border: "1px solid #f59e0b",
            background: "transparent",
            color: "#f59e0b",
            fontSize: 13,
            cursor: "pointer",
          }}
        >
          清除「不安装」标记
        </button>
        <button
          onClick={() => void handleWaitPrompt()}
          style={{
            padding: "8px 16px",
            borderRadius: 999,
            border: "1px solid var(--fn-border-primary)",
            background: "var(--fn-bg-tertiary)",
            color: "var(--fn-text-primary)",
            fontSize: 13,
            cursor: "pointer",
          }}
        >
          等待安装事件（8s）
        </button>
        <button
          onClick={() => void handleResetPwa()}
          style={{
            padding: "8px 16px",
            borderRadius: 999,
            border: "1px solid #ef4444",
            background: "transparent",
            color: "#ef4444",
            fontSize: 13,
            cursor: "pointer",
          }}
        >
          重置 PWA 状态（注销 SW）
        </button>
        {installSnap.prompt && (
          <button
            type="button"
            onClick={() => void handleInstall()}
            style={{
              padding: "8px 16px",
              borderRadius: 999,
              border: "1px solid var(--fn-color-brand)",
              background: "transparent",
              color: "var(--fn-color-brand)",
              fontSize: 13,
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            直接 prompt（已捕获）
          </button>
        )}
      </div>

      {showManualGuide && (
        <DesktopInstallGuide onClose={() => setShowManualGuide(false)} />
      )}
      {showIosGuide && <IosGuide onClose={() => setShowIosGuide(false)} />}

      {/* Instructions */}
      <div
        style={{
          padding: "14px 14px",
          borderRadius: 10,
          fontSize: 12,
          background: "rgba(96,165,250,0.08)",
          border: "1px solid rgba(96,165,250,0.2)",
          color: "var(--fn-text-secondary)",
          lineHeight: 1.7,
        }}
      >
        <strong>说明：</strong>
        <br />• <strong>SW 未控制当前页面</strong>：正常，首次访问后刷新即可
        <br />• <strong>beforeinstallprompt 未捕获</strong>：Chrome
        需要"参与度"才触发——在站点上正常使用几分钟后关闭，第二天或几小时后重新打开，Chrome
        会自动弹出安装横条
        <br />• <strong>manifest 被拦截</strong>
        ：需要在反向代理/网关白名单中放行 /manifest.json
        <br />• <strong>已设置「不安装」标记</strong>：点击「清除」按钮后刷新
        <br />• <strong>强制尝试安装</strong>：清除本地拒绝标记后调用
        beforeinstallprompt；若浏览器未发送该事件，会打开手动安装引导（网页无法绕过
        Chrome 强制弹窗）
        <br />• 点击「复制诊断报告」把结果发给开发者
      </div>
    </div>
  );
}
