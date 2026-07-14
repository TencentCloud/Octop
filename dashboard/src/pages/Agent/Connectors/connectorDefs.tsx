import { Cloud } from "lucide-react";

import { getConnectorLogo } from "../../../assets/connectors";
import type { ConnectorCatalogEntry } from "../../../api/modules/connectors";
import styles from "./index.module.less";

export const MAIL_PROVIDERS = [
  {
    id: "qq",
    label: "QQ 邮箱",
    guideUrl: "https://mail.qq.com/",
    emailPlaceholder: "you@qq.com",
  },
  {
    id: "netease",
    label: "网易邮箱",
    guideUrl: "https://mail.163.com/",
    emailPlaceholder: "you@163.com",
  },
  {
    id: "gmail",
    label: "Gmail",
    guideUrl: "https://mail.google.com/",
    emailPlaceholder: "you@gmail.com",
  },
  {
    id: "custom",
    label: "其他",
    guideUrl: null,
    emailPlaceholder: "you@example.com",
  },
] as const;

export type MailProviderId = (typeof MAIL_PROVIDERS)[number]["id"];

/** Connectors that use inline credential guide links instead of top auth buttons. */
export const INLINE_CREDENTIAL_GUIDE_KINDS = new Set(["qq-mail"]);

/** Connectors with a top auth button — hide redundant links under form fields. */
export const HIDE_INLINE_FIELD_GUIDE_KINDS = new Set([
  "tencent-ima",
  "tencent-lexiang",
  "tencent-meeting",
  "tencent-news",
  "wechat-reading",
  "youdao-note",
  "meituan-travel",
  "yuandian",
]);

export function mailProviderById(id: string | undefined) {
  return MAIL_PROVIDERS.find((item) => item.id === id) ?? MAIL_PROVIDERS[0];
}

export function connectorAccent(
  entry: Pick<ConnectorCatalogEntry, "kind" | "color">,
): string {
  return entry.color || "#1677ff";
}

export function ConnectorLogo({
  kind,
  size = 22,
}: {
  kind: string;
  size?: number;
}) {
  const src = getConnectorLogo(kind);
  if (!src) {
    return <Cloud size={size} />;
  }
  return (
    <img
      src={src}
      alt=""
      className={styles.connectorLogo}
      style={{ width: size, height: size }}
      draggable={false}
    />
  );
}
