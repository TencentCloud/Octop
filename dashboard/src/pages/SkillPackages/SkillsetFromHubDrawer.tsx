import { useEffect, useRef, useState } from "react";
import { Button, Drawer, Empty, Spin, Typography } from "antd";
import { Download } from "lucide-react";
import { useTranslation } from "react-i18next";

import {
  expertMarketApi,
  type MarketExpert,
} from "../../api/modules/expertMarket";
import { skillPackagesApi } from "../../api/modules/skillPackages";
import type { SkillPackageDetail } from "../../api/types/skillPackage";
import { pickLocale } from "../../utils/localizedText";
import { showApiError } from "../../utils/showApiToast";
import { PackageIcon } from "./PackageIcon";
import styles from "./SkillsetFromHubDrawer.module.less";

interface SkillsetFromHubDrawerProps {
  open: boolean;
  onClose: () => void;
  onCreated: (pkg: SkillPackageDetail) => void;
}

export function SkillsetFromHubDrawer({
  open,
  onClose,
  onCreated,
}: SkillsetFromHubDrawerProps) {
  const { t, i18n } = useTranslation();
  const [items, setItems] = useState<MarketExpert[]>([]);
  const [loading, setLoading] = useState(false);
  const [importingSlug, setImportingSlug] = useState<string | null>(null);
  const tRef = useRef(t);
  tRef.current = t;
  const lang = i18n.language.startsWith("zh") ? "zh" : "en";

  useEffect(() => {
    if (!open) return;
    let active = true;

    const load = async () => {
      setLoading(true);
      try {
        const response = await expertMarketApi.list("");
        if (active) setItems(response.items);
      } catch (error) {
        if (active) {
          showApiError(
            error,
            tRef.current("skillPackages.loadFailed"),
            tRef.current,
          );
        }
      } finally {
        if (active) setLoading(false);
      }
    };

    void load();
    return () => {
      active = false;
    };
  }, [open]);

  const importSkillset = async (expert: MarketExpert) => {
    if (importingSlug) return;
    setImportingSlug(expert.slug);
    try {
      const pkg = await skillPackagesApi.fromSkillHub({ slug: expert.slug });
      await onCreated(pkg);
    } catch (error) {
      showApiError(error, t("skillPackages.importFailed"), t);
    } finally {
      setImportingSlug(null);
    }
  };

  return (
    <Drawer
      title={t("skillPackages.fromSkillHub")}
      open={open}
      onClose={onClose}
      width={720}
      destroyOnClose
    >
      <Typography.Paragraph type="secondary" className={styles.hint}>
        {t("skillPackages.fromSkillHubHint")}
      </Typography.Paragraph>
      {loading ? (
        <div className={styles.loading}>
          <Spin />
        </div>
      ) : items.length === 0 ? (
        <Empty description={t("skillPackages.empty")} />
      ) : (
        <div className={styles.grid}>
          {items.map((expert) => {
            const name = pickLocale(expert.label, lang) || expert.slug;
            const description = pickLocale(expert.description, lang);
            const skillCount =
              expert.skill_count ?? expert.skill_slugs?.length ?? 0;
            return (
              <div key={expert.slug} className={styles.card}>
                <div className={styles.header}>
                  <div className={styles.iconWrap}>
                    <PackageIcon
                      iconUrl={expert.icon_url ?? undefined}
                      iconName={expert.icon_name ?? undefined}
                      size={18}
                      className={styles.icon}
                      imageClassName={styles.iconImage}
                    />
                  </div>
                  <div className={styles.titleBlock}>
                    <div className={styles.name} title={name}>
                      {name}
                    </div>
                  </div>
                </div>
                <div
                  className={styles.description}
                  title={description || undefined}
                >
                  {description || t("skillPackages.noDescription")}
                </div>
                <div className={styles.footer}>
                  <span className={styles.count}>
                    {t("skillPackages.skillCount", { count: skillCount })}
                  </span>
                  <Button
                    type="primary"
                    size="small"
                    icon={<Download size={14} />}
                    loading={importingSlug === expert.slug}
                    disabled={Boolean(importingSlug)}
                    onClick={() => void importSkillset(expert)}
                  >
                    {t("skillPackages.addAsPackage")}
                  </Button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </Drawer>
  );
}
