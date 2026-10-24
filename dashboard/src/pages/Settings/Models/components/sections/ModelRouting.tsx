/**
 * ModelRouting — 模型路由（有序 failover 链）。
 *
 * 按用户手动设置的顺序依次调用模型：第 1 个失败（限流/故障/不可用）时
 * 自动切换下一个，全部失败才报错。链为空时不启用路由，按偏好模型（星星）走。
 * 保存走 PATCH /api/preferences { model_routing: string[] }。
 */
import { useMemo, useState } from "react";
import { ArrowDown, ArrowUp, Info, Plus, Trash2 } from "lucide-react";
import { Button, Empty, Select, Tag, Tooltip } from "antd";
import { message } from "@/utils/antdMessage";

import { useTranslation } from "react-i18next";
import { preferencesApi } from "../../../../../api/modules/preferences";
import type { ResolvedModel } from "../../useProviders";
import { modelOptionLabel } from "../../../../../utils/modelOptions";
import styles from "../../index.module.less";

const MAX_ROUTING = 8;

interface ModelRoutingProps {
  resolvedModels: ResolvedModel[];
  routing: string[];
  onSaved: () => void | Promise<void>;
}

export function ModelRouting({
  resolvedModels,
  routing,
  onSaved,
}: ModelRoutingProps) {
  const { t } = useTranslation();
  const [saving, setSaving] = useState(false);
  const [adding, setAdding] = useState(false);

  // ref -> 展示名（找不到就显示原始 ref，容忍 provider 被删后链里残留的项）
  const labelOf = useMemo(() => {
    const map = new Map<string, string>();
    for (const m of resolvedModels) {
      map.set(`${m.provider_name}/${m.model}`, modelOptionLabel(m));
    }
    return (ref: string) => map.get(ref) ?? ref;
  }, [resolvedModels]);

  const candidates = useMemo(
    () =>
      resolvedModels
        .map((m) => ({
          value: `${m.provider_name}/${m.model}`,
          label: modelOptionLabel(m),
        }))
        .filter((o) => !routing.includes(o.value)),
    [resolvedModels, routing],
  );

  const save = async (next: string[]) => {
    setSaving(true);
    try {
      await preferencesApi.patch({ model_routing: next });
      message.success(t("models.routingSaved"));
      await onSaved();
    } catch (err) {
      message.error(
        err instanceof Error ? err.message : t("common.saveFailed"),
      );
    } finally {
      setSaving(false);
    }
  };

  const move = (index: number, delta: number) => {
    const next = [...routing];
    const target = index + delta;
    if (target < 0 || target >= next.length) return;
    [next[index], next[target]] = [next[target], next[index]];
    void save(next);
  };

  const remove = (index: number) => {
    void save(routing.filter((_, i) => i !== index));
  };

  const append = (ref: string) => {
    if (!ref || routing.length >= MAX_ROUTING) return;
    void save([...routing, ref]);
    setAdding(false);
  };

  return (
    <div className={styles.poolSection}>
      <div className={styles.poolHeader}>
        <div className={styles.poolHeaderLeft}>
          <h3 className={styles.slotTitle}>{t("models.routingTitle")}</h3>
          <Tooltip title={t("models.routingTooltip")}>
            <Info size={14} className={styles.poolInfoIcon} />
          </Tooltip>
        </div>
        {routing.length > 0 && (
          <Tag color="blue" className={styles.poolCountTag}>
            {t("models.routingCount", { count: routing.length })}
          </Tag>
        )}
      </div>

      <p className={styles.poolDesc}>{t("models.routingDesc")}</p>

      {routing.length === 0 ? (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={t("models.routingEmpty")}
        />
      ) : (
        <div className={styles.routingList}>
          {routing.map((ref, i) => (
            <div key={ref} className={styles.routingRow}>
              <span className={styles.routingIndex}>{i + 1}</span>
              <span className={styles.routingName} title={ref}>
                {labelOf(ref)}
              </span>
              <div className={styles.routingActions}>
                <Tooltip title={t("models.routingMoveUp")}>
                  <Button
                    type="text"
                    size="small"
                    disabled={i === 0 || saving}
                    icon={<ArrowUp size={14} />}
                    onClick={() => move(i, -1)}
                  />
                </Tooltip>
                <Tooltip title={t("models.routingMoveDown")}>
                  <Button
                    type="text"
                    size="small"
                    disabled={i === routing.length - 1 || saving}
                    icon={<ArrowDown size={14} />}
                    onClick={() => move(i, 1)}
                  />
                </Tooltip>
                <Tooltip title={t("models.routingRemove")}>
                  <Button
                    type="text"
                    size="small"
                    danger
                    disabled={saving}
                    icon={<Trash2 size={14} />}
                    onClick={() => remove(i)}
                  />
                </Tooltip>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className={styles.routingAddRow}>
        {adding ? (
          <Select
            autoFocus
            showSearch
            placeholder={t("models.routingAddPlaceholder")}
            style={{ minWidth: 280 }}
            options={candidates}
            onSelect={(value) => append(value as string)}
            onBlur={() => setAdding(false)}
            notFoundContent={t("models.noModelsAvailable")}
          />
        ) : (
          <Button
            size="small"
            icon={<Plus size={14} />}
            disabled={routing.length >= MAX_ROUTING || saving}
            onClick={() => setAdding(true)}
          >
            {t("models.routingAdd")}
          </Button>
        )}
      </div>
    </div>
  );
}
