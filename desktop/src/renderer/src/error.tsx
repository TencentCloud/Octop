import { useEffect, useMemo, useState } from "react";
import markUrl from "./assets/octop-mark.svg";
import { decodeShellError } from "../../shared/shell-error";
import { mount } from "./mount";
import "./base.css";
import "./error.css";

const PAYLOAD_PARAM = "payload";
const COPY_FEEDBACK_MS = 2200;

type CopyState = "idle" | "copied" | "failed";

/**
 * The failure Result shown inside the Early Window when boot cannot continue
 * (runtime version guard, checksum mismatch, sidecar never becoming healthy).
 * It never renders a stack trace as the headline: `message` is the sentence the
 * user gets, `detail` is the technical tail, hidden behind a disclosure.
 *
 * The page leads with the product mark rather than a generic ✕: the user did not
 * hit a website error, the app they just launched could not come up, and the
 * first thing worth offering is another attempt.
 */
function FailureMark() {
  return (
    <div className="result__mark" aria-hidden="true">
      <img className="result__mark-img" src={markUrl} alt="" width={352} height={255} />
      <span className="result__badge">
        <svg viewBox="0 0 12 12" width="11" height="11" aria-hidden="true">
          <rect x="5.15" y="1" width="1.7" height="6.2" rx="0.85" fill="currentColor" />
          <circle cx="6" cy="9.95" r="1.05" fill="currentColor" />
        </svg>
      </span>
    </div>
  );
}

/** Clipboard writes can be refused (no user gesture yet, sandboxed page). */
async function writeClipboard(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    // Fall through to the legacy path below.
  }
  try {
    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.top = "-1000px";
    area.style.opacity = "0";
    document.body.append(area);
    area.select();
    const copied = document.execCommand("copy");
    area.remove();
    return copied;
  } catch {
    return false;
  }
}

function ErrorPage() {
  const payload = useMemo(
    () => decodeShellError(new URLSearchParams(window.location.search).get(PAYLOAD_PARAM)),
    [],
  );
  const [copyState, setCopyState] = useState<CopyState>("idle");
  /** Absent when the page is opened outside the shell (no preload bridge). */
  const canRetry = typeof window.octopShell?.restart === "function";

  useEffect(() => {
    if (copyState === "idle") return;
    const timer = window.setTimeout(() => setCopyState("idle"), COPY_FEEDBACK_MS);
    return () => window.clearTimeout(timer);
  }, [copyState]);

  // Native caption buttons are on the window. Esc still closes a page whose
  // only content is a fatal error.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") window.close();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const title = payload.title ?? "Octop 无法启动";
  const { message, detail, version } = payload;

  const copyLabel =
    copyState === "copied" ? "已复制" : copyState === "failed" ? "复制失败" : "复制错误信息";

  const handleCopy = () => {
    const text = [title, message, detail, version ? `Octop Desktop v${version}` : ""]
      .filter(Boolean)
      .join("\n\n");
    void writeClipboard(text).then((ok) => setCopyState(ok ? "copied" : "failed"));
  };

  const handleRetry = () => window.octopShell?.restart();

  return (
    <main className="result">
      <div className="result__body" role="alert">
        <FailureMark />
        <h1 className="result__title">{title}</h1>
        <p className="result__message">{message}</p>

        <div className="result__actions">
          {canRetry ? (
            <button
              type="button"
              className="result__button result__button--primary"
              onClick={handleRetry}
              autoFocus
            >
              重试启动
            </button>
          ) : null}
          <button
            type="button"
            className="result__button"
            onClick={() => window.close()}
            autoFocus={!canRetry}
          >
            退出应用
          </button>
        </div>

        <div className="result__aside">
          {detail ? (
            <details className="result__details">
              <summary className="result__summary">
                <svg
                  viewBox="0 0 12 12"
                  width={12}
                  height={12}
                  className="result__caret"
                  aria-hidden="true"
                >
                  <path
                    d="M4.5 2.5 8 6l-3.5 3.5"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth={1.6}
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
                技术详情
              </summary>
              <pre className="result__detail">{detail}</pre>
            </details>
          ) : null}
          <button
            type="button"
            className="result__link"
            onClick={handleCopy}
            aria-live="polite"
          >
            {copyLabel}
          </button>
        </div>
      </div>

      {version ? <p className="result__meta">Octop 桌面端 v{version}</p> : null}
    </main>
  );
}

mount(<ErrorPage />);
