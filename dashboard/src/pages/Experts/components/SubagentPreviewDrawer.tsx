import { useEffect, useState } from "react";
import { Drawer, Spin } from "antd";
import { message } from "@/utils/antdMessage";

import { useTranslation } from "react-i18next";
import { getSubagentCatalogItem } from "../../../api/modules/subagents";
import { useIsMobile } from "../../../hooks/useIsMobile";
import { apiErrorMessage } from "../../../utils/apiError";
import { normalizeUiLocale } from "../../../utils/locale";
import { pickLocale } from "../../../utils/localizedText";
import styles from "../index.module.less";

interface SubagentPreviewDrawerProps {
  slug: string | null;
  title: string;
  open: boolean;
  onClose: () => void;
}

export default function SubagentPreviewDrawer({
  slug,
  title,
  open,
  onClose,
}: SubagentPreviewDrawerProps) {
  const { t, i18n } = useTranslation();
  const isMobile = useIsMobile();
  const lang = normalizeUiLocale(i18n.language);
  const [loading, setLoading] = useState(false);
  const [content, setContent] = useState("");

  useEffect(() => {
    if (!open || !slug) {
      setContent("");
      return;
    }
    let cancelled = false;
    setLoading(true);
    void getSubagentCatalogItem(slug)
      .then((detail) => {
        if (!cancelled) setContent(pickLocale(detail.content, lang));
      })
      .catch((err) => {
        if (!cancelled) {
          setContent("");
          message.error(apiErrorMessage(err, t("subagents.previewFailed")));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, slug, lang, t]);

  return (
    <Drawer
      open={open}
      title={title}
      width={isMobile ? "100%" : 480}
      onClose={onClose}
      destroyOnHidden
      styles={{
        body: isMobile
          ? {
              padding: "12px",
              overflow: "auto",
              WebkitOverflowScrolling: "touch",
            }
          : { padding: "12px 16px 20px" },
      }}
    >
      {loading ? (
        <div className={styles.catalogPreviewLoading}>
          <Spin />
        </div>
      ) : (
        <pre className={styles.catalogPreviewContent}>
          {content || t("workspace.emptyFile")}
        </pre>
      )}
    </Drawer>
  );
}
