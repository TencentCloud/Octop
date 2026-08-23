import type { CSSProperties } from "react";
import type { ToolRenderProps } from "../types";

/** Hard-coded colors so the card is visible even if theme CSS vars are missing. */
const cardStyle: CSSProperties = {
  marginTop: 0,
  padding: "12px 14px",
  borderRadius: 10,
  border: "1px solid #d0d5dd",
  background: "#ffffff",
  color: "#1f2937",
  maxWidth: 420,
  boxShadow: "0 1px 2px rgba(16, 24, 40, 0.06)",
};

/**
 * Fallback when tool output has ``octop_ui`` but the plugin ESM has not
 * registered (or failed to load). Still shows structured ``data`` visibly.
 */
export function BuiltinOctopUiFallback({
  toolName,
  displayName,
  data,
  textFallback,
  status,
  output,
}: ToolRenderProps) {
  const obj =
    data && typeof data === "object" && !Array.isArray(data)
      ? (data as Record<string, unknown>)
      : null;
  const title =
    (obj && typeof obj.title === "string" && obj.title) ||
    textFallback ||
    displayName ||
    toolName ||
    "Tool result";
  const entries = obj ? Object.entries(obj).filter(([k]) => k !== "title") : [];

  return (
    <div
      className="octop-builtin-ui-fallback"
      data-octop-plugin-ui="builtin-fallback"
      style={cardStyle}
    >
      <div style={{ fontWeight: 600, marginBottom: 4, fontSize: 15 }}>
        {title}
      </div>
      <div style={{ fontSize: 12, opacity: 0.7, marginBottom: 8 }}>
        {toolName || "tool"}
        {status === "running" ? " · running" : ""}
      </div>
      {entries.length > 0 ? (
        <dl style={{ margin: 0, fontSize: 13 }}>
          {entries.map(([k, v]) => (
            <div key={k} style={{ marginBottom: 4 }}>
              <dt style={{ display: "inline", opacity: 0.65 }}>{k}: </dt>
              <dd style={{ display: "inline", margin: 0 }}>
                {typeof v === "string" || typeof v === "number"
                  ? String(v)
                  : JSON.stringify(v)}
              </dd>
            </div>
          ))}
        </dl>
      ) : textFallback ? (
        <div style={{ fontSize: 13 }}>{textFallback}</div>
      ) : output ? (
        <pre
          style={{
            margin: 0,
            fontSize: 12,
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
          }}
        >
          {typeof output === "string"
            ? output
            : JSON.stringify(output, null, 2)}
        </pre>
      ) : (
        <div style={{ fontSize: 12, opacity: 0.6 }}>(no data)</div>
      )}
    </div>
  );
}
