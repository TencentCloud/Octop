import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button, Empty, Spin, Tag, Tooltip, Typography } from "antd";
import { Plus, X } from "lucide-react";

import { connectorsApi } from "../../../../api/modules/connectors";
import {
  projectConfigApi,
  type ProjectConnectorResolution,
} from "../../../../api/modules/projectConfig";
import { apiErrorMessage } from "../../../../utils/apiError";
import { message } from "../../../../utils/antdMessage";
import SearchablePickerPanel from "../../../../components/ChatPicker/SearchablePickerPanel";
import styles from "./ConnectorsPanel.module.less";

const { Text } = Typography;

interface ConnectorsPanelProps {
  projectId: string;
  /** `PROJECT_MANAGE_CONFIG`（owner/admin）才可增删声明。 */
  canManage: boolean;
}

/**
 * 右栏「连接器」面板（PLAN §1.2/§1.4）。
 *
 * 项目**只存 kind**；`available=false` 是**非错误面**（S1：同 kind 实例都非
 * active / S2：只有 `shared` 实例）→ 灰态 + 「对你不可用」，**不得**用错误样式。
 * 解析结果按当前用户计算，所以这里显示「将使用你的 <name>」。
 */
export default function ConnectorsPanel({
  projectId,
  canManage,
}: ConnectorsPanelProps) {
  const { t } = useTranslation();
  const [items, setItems] = useState<ProjectConnectorResolution[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [adding, setAdding] = useState(false);
  const [catalog, setCatalog] = useState<{ kind: string; name: string }[]>([]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setItems(await projectConfigApi.getConnectors(projectId));
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    void load();
  }, [load]);

  // 声明用的 kind 来自既有连接器目录（只读，非项目数据源）。
  useEffect(() => {
    if (!adding) return;
    let cancelled = false;
    connectorsApi
      .catalog()
      .then((rows) => {
        if (!cancelled) {
          setCatalog(rows.map((row) => ({ kind: row.kind, name: row.name })));
        }
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [adding]);

  const declaredKinds = useMemo(() => items.map((item) => item.kind), [items]);
  const candidates = useMemo(
    () => catalog.filter((entry) => !declaredKinds.includes(entry.kind)),
    [catalog, declaredKinds],
  );

  const replaceKinds = useCallback(
    async (kinds: string[]) => {
      if (saving) return;
      setSaving(true);
      try {
        setItems(await projectConfigApi.putConnectors(projectId, kinds));
        setAdding(false);
      } catch (err) {
        message.error(apiErrorMessage(err, t("projects.connectorAdd"), t));
      } finally {
        setSaving(false);
      }
    },
    [projectId, saving, t],
  );

  return (
    <section className={styles.panel} data-testid="rail-connectors">
      <div className={styles.header}>
        <span className={styles.title}>{t("projects.connectorTitle")}</span>
        {canManage ? (
          <Button
            type="text"
            size="small"
            aria-label={t("projects.connectorAdd")}
            icon={<Plus size={14} />}
            onClick={() => setAdding((value) => !value)}
          />
        ) : null}
      </div>

      {loading ? (
        <div className={styles.centered}>
          <Spin size="small" />
        </div>
      ) : error ? (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={apiErrorMessage(error, t("projects.connectorTitle"), t)}
        />
      ) : items.length === 0 ? (
        <Text type="secondary" data-testid="connectors-empty">
          {t("projects.connectorNone")}
        </Text>
      ) : (
        <ul className={styles.list}>
          {items.map((item) => (
            <li
              key={item.kind}
              className={styles.row}
              data-testid={`connector-${item.kind}`}
            >
              <div className={styles.rowMain}>
                <span className={styles.rowName}>{item.kind}</span>
                {item.available ? (
                  <Text type="secondary" className={styles.rowMeta}>
                    {t("projects.connectorUsing", {
                      name: item.display_name ?? item.kind,
                    })}
                  </Text>
                ) : (
                  // S1/S2：非错误面 —— 灰态 + 「对你不可用」+ tooltip。
                  <Tooltip title={t("projects.connectorUnavailable")}>
                    <span
                      className={styles.unavailable}
                      data-testid={`connector-unavailable-${item.kind}`}
                    >
                      {t("projects.connectorUnavailable")}
                    </span>
                  </Tooltip>
                )}
              </div>
              {item.available ? (
                <Tag
                  className={styles.availableTag}
                  data-testid="connector-available"
                >
                  {t("projects.connectorAvailable")}
                </Tag>
              ) : null}
              {canManage ? (
                <Button
                  type="text"
                  size="small"
                  aria-label={t("common.delete")}
                  icon={<X size={14} />}
                  onClick={() =>
                    void replaceKinds(
                      declaredKinds.filter((kind) => kind !== item.kind),
                    )
                  }
                />
              ) : null}
            </li>
          ))}
        </ul>
      )}

      {canManage && adding ? (
        /* 形态统一到图 2（批次六 AC-C-1）：列表交给骨架 `SearchablePickerPanel`；
           ★ 功能不变 —— 提交仍走既有 `replaceKinds`（同签名）。 */
        <div className={styles.addBox} data-testid="picker-panel">
          <SearchablePickerPanel<{ kind: string; name: string }>
            items={candidates}
            filterFn={(entry, query) =>
              `${entry.name}\n${entry.kind}`.toLowerCase().includes(query)
            }
            searchPlaceholder={t("projects.quickInputRecipientFilter")}
            emptyMessage={t("projects.connectorNone")}
            renderItem={(entry) => (
              <Button
                key={entry.kind}
                type="text"
                size="small"
                block
                className={styles.addOption}
                data-testid={`picker-option-connector-${entry.kind}`}
                disabled={saving}
                onClick={() =>
                  void replaceKinds([...declaredKinds, entry.kind])
                }
              >
                {entry.name}
              </Button>
            )}
            footerIcon={<Plus size={15} aria-hidden />}
            footerLabel={t("projects.connectorAdd")}
            onFooterClick={() => undefined}
          />
        </div>
      ) : null}
    </section>
  );
}
