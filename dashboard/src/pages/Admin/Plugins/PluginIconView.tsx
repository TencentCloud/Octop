import { Package, Wrench } from "lucide-react";
import type { CSSProperties } from "react";

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

/** Render plugin.yaml ``icon`` (emoji text or image URL). */
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
    ...style,
  };

  if (trimmed && isIconUrl(trimmed)) {
    return (
      <span className={className} style={shell}>
        <img
          src={trimmed}
          alt=""
          referrerPolicy="no-referrer"
          style={{ width: "100%", height: "100%", objectFit: "cover" }}
        />
      </span>
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
        }}
        aria-hidden
      >
        {trimmed}
      </span>
    );
  }

  const Icon = fallback === "wrench" ? Wrench : Package;
  return (
    <span className={className} style={shell}>
      <Icon size={Math.round(size * 0.42)} />
    </span>
  );
}
