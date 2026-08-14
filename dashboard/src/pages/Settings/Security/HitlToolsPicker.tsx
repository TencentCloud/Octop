import { useMemo } from "react";
import { Button, Checkbox, Space, Typography } from "antd";
import { useTranslation } from "react-i18next";
import type { HitlToolCatalogItem } from "../../../api/modules/security";
import styles from "./index.module.less";

const { Text } = Typography;

function localizedLabel(item: HitlToolCatalogItem, locale: string): string {
  return locale.startsWith("zh") ? item.label_zh : item.label_en;
}

interface HitlToolsPickerProps {
  catalog: HitlToolCatalogItem[];
  defaultTools?: string[];
  value?: string[];
  onChange?: (tools: string[]) => void;
  disabled?: boolean;
}

export default function HitlToolsPicker({
  catalog,
  defaultTools = [],
  value = [],
  onChange,
  disabled,
}: HitlToolsPickerProps) {
  const { t, i18n } = useTranslation();

  const options = useMemo(() => {
    const known = new Set(catalog.map((item) => item.name));
    const extras = value.filter((name) => !known.has(name));
    return [
      ...catalog,
      ...extras.map((name) => ({
        name,
        label_zh: name,
        label_en: name,
      })),
    ];
  }, [catalog, value]);

  const handleSelectAll = () => {
    onChange?.(options.map((item) => item.name));
  };

  const handleDeselectAll = () => {
    onChange?.([]);
  };

  const handleSelectDefaults = () => {
    const known = new Set(options.map((item) => item.name));
    onChange?.(defaultTools.filter((name) => known.has(name)));
  };

  if (options.length === 0) {
    return <Text type="secondary">{t("security.hitlToolsEmpty")}</Text>;
  }

  return (
    <div className={styles.hitlToolsPicker}>
      <div className={styles.hitlToolsPickerHeader}>
        <Text type="secondary" className={styles.hitlToolsPickerHint}>
          {t("security.hitlToolsPickerHint")}
        </Text>
        <Space size={4} wrap>
          <Button
            type="link"
            size="small"
            disabled={disabled}
            onClick={handleSelectDefaults}
          >
            {t("security.hitlToolsSelectDefaults")}
          </Button>
          <Button
            type="link"
            size="small"
            disabled={disabled}
            onClick={handleSelectAll}
          >
            {t("security.hitlToolsSelectAll")}
          </Button>
          <Button
            type="link"
            size="small"
            disabled={disabled}
            onClick={handleDeselectAll}
          >
            {t("security.hitlToolsDeselectAll")}
          </Button>
        </Space>
      </div>
      <Checkbox.Group
        className={styles.hitlToolsGrid}
        value={value}
        disabled={disabled}
        onChange={(names) => onChange?.(names as string[])}
      >
        {options.map((item) => (
          <Checkbox
            key={item.name}
            value={item.name}
            className={styles.hitlToolTile}
          >
            <span className={styles.hitlToolLabel}>
              {localizedLabel(item, i18n.language)}
            </span>
            <span className={styles.hitlToolName}>{item.name}</span>
          </Checkbox>
        ))}
      </Checkbox.Group>
    </div>
  );
}
