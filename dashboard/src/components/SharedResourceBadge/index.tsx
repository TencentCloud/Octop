import type { ReactNode } from "react";
import { Share2 } from "lucide-react";
import { Tooltip } from "antd";
import { useTranslation } from "react-i18next";
import cx from "classnames";
import {
  isSharedExpertViewer,
  type SharedExpertAccess,
} from "../../utils/sharedExpert";
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

/** Compact share mark — same icon for “I shared this” and “shared with me”. */
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
      className={cx(
        styles.iconMark,
        incoming ? styles.incomingIcon : styles.outgoingIcon,
        className,
      )}
      title={label}
      aria-label={label}
    >
      <Share2 size={12} strokeWidth={2} aria-hidden />
    </span>
  );
}

/** Props for the incoming-share pip. Owners who shared outward get no avatar mark. */
export function incomingShareProps(
  agent?: (SharedExpertAccess & { owner_username?: string | null }) | null,
): { shared: boolean; owned: boolean; ownerName?: string | null } {
  const incoming = Boolean(agent && isSharedExpertViewer(agent));
  return {
    shared: incoming,
    owned: !incoming,
    ownerName: agent?.owner_username,
  };
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
    <span className={cx(styles.avatarHost, className)}>
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
