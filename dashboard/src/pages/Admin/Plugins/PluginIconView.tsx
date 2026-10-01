import { Package, Wrench } from "lucide-react";
import type { CSSProperties } from "react";
import { useAuthImageSrc } from "../../../hooks/useAuthImageSrc";
import { needsAuthBlobFetch } from "../../../utils/toolMediaBlocks";

function isIconUrl(icon: string): boolean {
  const value = icon.trim();
  return (
    /^(https?:)?\/\//i.test(value) ||
    value.startsWith("/") ||
    value.startsWith("data:image/")
  );
}

export interface PluginIconViewProps {
  icon?: string | null;
  size?: number;
  className?: string;
  style?: CSSProperties;
  fallback?: "package" | "wrench";
}

function PluginIconImage({
  url,
  size,
  className,
  style,
  shell,
}: {
  url: string;
  size: number;
  className?: string;
  style?: CSSProperties;
  shell: CSSProperties;
}) {
  const authNeeded = needsAuthBlobFetch(url);
  const { src, loadState } = useAuthImageSrc(url);
  const displaySrc = authNeeded ? src : url;
  const ready = !authNeeded || (loadState === "ready" && !!displaySrc);

  return (
    <span
      className={className}
      style={{
        ...shell,
        ...(ready ? { background: "transparent" } : undefined),
        ...style,
      }}
    >
      {ready ? (
        <img
          src={displaySrc}
          alt=""
          referrerPolicy="no-referrer"
          style={{ width: "100%", height: "100%", objectFit: "cover" }}
        />
      ) : (
        <Package size={Math.round(size * 0.42)} />
      )}
    </span>
  );
}

/** Render plugin.yaml ``icon`` (emoji, image URL, or plugin-relative API path). */
export function PluginIconView({
  icon,
  size = 40,
  className,
  style,
  fallback = "package",
}: PluginIconViewProps) {
  const trimmed = (icon || "").trim();
  const radius = Math.max(10, Math.round(size * 0.28));
  const shell: CSSProperties = {
    width: size,
    height: size,
    borderRadius: radius,
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    flexShrink: 0,
    overflow: "hidden",
    background: "var(--fn-bg-secondary, #f2f4f7)",
    color: "var(--fn-text-secondary)",
  };

  if (trimmed && isIconUrl(trimmed)) {
    return (
      <PluginIconImage
        url={trimmed}
        size={size}
        className={className}
        style={style}
        shell={shell}
      />
    );
  }

  if (trimmed) {
    return (
      <span
        className={className}
        style={{
          ...shell,
          fontSize: Math.round(size * 0.52),
          lineHeight: 1,
          ...style,
        }}
        aria-hidden
      >
        {trimmed}
      </span>
    );
  }

  const Icon = fallback === "wrench" ? Wrench : Package;
  return (
    <span className={className} style={{ ...shell, ...style }}>
      <Icon size={Math.round(size * 0.42)} />
    </span>
  );
}
