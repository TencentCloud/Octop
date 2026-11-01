import type { ReactNode } from "react";
import { Share2 } from "lucide-react";
import { Tooltip } from "antd";
import { useTranslation } from "react-i18next";
import styles from "./SharedResourceBadge.module.less";

type Props = {
  /** Resource is shared beyond its owner. */
  shared?: boolean;
  /** Current user owns the resource. */
  owned: boolean;
  /** Owner label for an incoming share. */
  ownerName?: string | null;
  className?: string;
};

/** One pill for “I shared this” and “someone shared this with me”. */
export function SharedResourceBadge({
  shared,
  owned,
  ownerName,
  className,
}: Props) {
  const { t } = useTranslation();
  if (!shared) return null;
  const incoming = !owned;
  const name =
    (ownerName || "").trim() || t("sharedResource.someone", "其他用户");
  const label = incoming
    ? t("sharedResource.from", { name, defaultValue: "来自 {{name}}" })
    : t("sharedResource.shared", "已共享");
  return (
    <span
      className={[
        styles.badge,
        incoming ? styles.incoming : styles.outgoing,
        className,
      ]
        .filter(Boolean)
        .join(" ")}
      title={label}
    >
      <Share2 size={11} aria-hidden />
      <span className={styles.label}>{label}</span>
    </span>
  );
}

/** Avatar with a pip when the resource was shared to the current user. */
export function SharedAvatarMark({
  shared,
  owned,
  ownerName,
  children,
  className,
  label,
}: Omit<Props, "className"> & {
  children: ReactNode;
  className?: string;
  /** Tooltip override. Defaults to “来自 {{name}}”. */
  label?: string;
}) {
  const { t } = useTranslation();
  const incoming = Boolean(shared) && !owned;
  const name =
    (ownerName || "").trim() || t("sharedResource.someone", "其他用户");
  const tip =
    label ||
    t("sharedResource.from", {
      name,
      defaultValue: "来自 {{name}}",
    });
  return (
    <span className={[styles.avatarHost, className].filter(Boolean).join(" ")}>
      {children}
      {incoming ? (
        <Tooltip title={tip} mouseEnterDelay={0.3}>
          <span
            className={styles.avatarMark}
            aria-label={tip}
            onClick={(event) => event.stopPropagation()}
          >
            <Share2 aria-hidden />
          </span>
        </Tooltip>
      ) : null}
    </span>
  );
}
