/**
 * Shared helpers for rendering model capability metadata (modalities, token limits).
 */
import { Tag } from "antd";
import { useTranslation } from "react-i18next";
import styles from "./index.module.less";

export interface ModelMetaSource {
  input?: string[];
  context_window?: number | null;
  max_input_tokens?: number | null;
  max_tokens?: number | null;
  max_output_tokens?: number | null;
  reasoning?: boolean | null;
}

export function formatTokenCount(value?: number | null): string {
  if (!value) return "";
  if (value >= 1_000_000) {
    const n = value / 1_000_000;
    return `${n % 1 === 0 ? n.toFixed(0) : n.toFixed(1)}M`;
  }
  if (value >= 1_000) return `${Math.round(value / 1_000)}K`;
  return `${value}`;
}

export function ModelMetaTags({
  input,
  context_window,
  max_input_tokens,
  max_tokens,
  max_output_tokens,
  reasoning,
  className,
  includeText = false,
}: ModelMetaSource & { className?: string; includeText?: boolean }) {
  const { t } = useTranslation();
  const tags: React.ReactNode[] = [];

  if (reasoning) {
    tags.push(
      <Tag key="reasoning" color="purple" className={styles.capabilityTag}>
        {t("models.capReasoning")}
      </Tag>,
    );
  }

  const modalities = input ?? ["text"];
  for (const modality of modalities) {
    if (modality === "text" && !includeText) continue;
    const colorMap: Record<string, string> = {
      text: "green",
      image: "blue",
      audio: "cyan",
      video: "geekblue",
    };
    tags.push(
      <Tag
        key={`input-${modality}`}
        color={colorMap[modality] || "default"}
        className={styles.capabilityTag}
      >
        {modality === "text"
          ? t("models.cap_text")
          : t(`models.cap_${modality}`, modality)}
      </Tag>,
    );
  }

  const ctx = formatTokenCount(context_window ?? max_input_tokens);
  if (ctx) {
    tags.push(
      <Tag key="ctx" className={styles.capabilityTag}>
        {t("models.contextShort", { value: ctx })}
      </Tag>,
    );
  }

  const out = formatTokenCount(max_output_tokens ?? max_tokens);
  if (out) {
    tags.push(
      <Tag key="max-out" className={styles.capabilityTag}>
        {t("models.maxOutShort", { value: out })}
      </Tag>,
    );
  }

  if (tags.length === 0) return null;

  return <div className={className ?? styles.modelMetaTags}>{tags}</div>;
}
