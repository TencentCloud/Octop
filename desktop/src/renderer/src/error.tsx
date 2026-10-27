import { useEffect, useMemo, useState } from "react";
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
 */
function ResultGlyph() {
  return (
    <svg
      className="result__glyph"
      viewBox="0 0 76 76"
      width={76}
      height={76}
      fill="none"
      aria-hidden="true"
    >
      <circle
        cx="38"
        cy="38"
        r="36.5"
        fill="var(--brand-surface)"
        stroke="var(--brand-border)"
        strokeWidth={1.5}
      />
      <path
        d="M27 27 49 49M49 27 27 49"
        stroke="var(--brand)"
        strokeWidth={3.25}
        strokeLinecap="round"
      />
    </svg>
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

  useEffect(() => {
    if (copyState === "idle") return;
    const timer = window.setTimeout(() => setCopyState("idle"), COPY_FEEDBACK_MS);
    return () => window.clearTimeout(timer);
  }, [copyState]);

  // The window is frameless and has no controls of its own; Esc is the expected
  // way out of a page whose only content is a fatal error.
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

  return (
    <main className="result">
      <div className="result__body" role="alert">
        <ResultGlyph />
        <h1 className="result__title">{title}</h1>
        <p className="result__message">{message}</p>

        {detail ? (
          <details className="result__details">
            <summary className="result__summary">
              <svg viewBox="0 0 12 12" width={12} height={12} className="result__caret" aria-hidden="true">
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

        <div className="result__actions">
          <button
            type="button"
            className="result__button result__button--primary"
            onClick={() => window.close()}
            autoFocus
          >
            退出应用
          </button>
          <button
            type="button"
            className="result__button"
            onClick={handleCopy}
            aria-live="polite"
          >
            {copyLabel}
          </button>
        </div>

        {version ? <p className="result__meta">Octop 桌面端 v{version}</p> : null}
      </div>
    </main>
  );
}

mount(<ErrorPage />);
