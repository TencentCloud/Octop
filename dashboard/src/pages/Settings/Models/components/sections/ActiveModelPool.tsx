/**
 * ActiveModelPool — shows all resolved (enabled + authorized) models
 * grouped by provider, with a star button to set the global preferred model.
 *
 * Mirrors finnie's ActiveModelPool component.
 */
import { useMemo, useState } from "react";
import { Check, Info, Star, X, Zap } from "lucide-react";
import { Button, Empty, Tag, Tooltip } from "antd";
import { message } from "@/utils/antdMessage";

import { useTranslation } from "react-i18next";
import { request } from "../../../../../api/request";
import type { ProviderRow, ResolvedModel } from "../../useProviders";
import { ModelMetaTags } from "../../modelMeta";
import { modelOptionLabel } from "../../../../../utils/modelOptions";
import styles from "../../index.module.less";

interface ActiveModel {
  provider_name: string;
  model: string;
}

interface ActiveModelPoolProps {
  resolvedModels: ResolvedModel[];
  activeModel: ActiveModel;
  providers: ProviderRow[];
  onSaved: () => void | Promise<void>;
}

interface GroupedModels {
  providerId: number;
  providerName: string;
  providerKind: string;
  models: ResolvedModel[];
}

export function ActiveModelPool({
  resolvedModels,
  activeModel,
  providers,
  onSaved,
}: ActiveModelPoolProps) {
  const { t } = useTranslation();
  const [setting, setSetting] = useState<string | null>(null);
  const [testingKey, setTestingKey] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<
    Map<string, "success" | "failure">
  >(new Map());

  const providerHasKey = useMemo(() => {
    const map = new Map<number, boolean>();
    for (const p of providers) {
      map.set(p.id, !!p.api_key);
    }
    return map;
  }, [providers]);

  const grouped = useMemo<GroupedModels[]>(() => {
    const map = new Map<string, GroupedModels>();
    for (const m of resolvedModels) {
      let group = map.get(m.provider_name);
      if (!group) {
        group = {
          providerId: m.provider_id,
          providerName: m.provider_name,
          providerKind: m.provider_kind,
          models: [],
        };
        map.set(m.provider_name, group);
      }
      group.models.push(m);
    }
    return Array.from(map.values());
  }, [resolvedModels]);

  const handleSetPreferred = async (m: ResolvedModel) => {
    const isAlready =
      m.provider_name === activeModel.provider_name &&
      m.model === activeModel.model;
    if (isAlready) return;

    const key = `${m.provider_name}/${m.model}`;
    setSetting(key);
    try {
      await request("/providers/active-model", {
        method: "PUT",
        body: JSON.stringify({
          provider_name: m.provider_name,
          model: m.model,
        }),
      });
      message.success(
        t("models.preferredModelSet", {
          model: modelOptionLabel(m),
        }),
      );
      await onSaved();
    } catch (err) {
      message.error(
        err instanceof Error ? err.message : t("common.saveFailed"),
      );
    } finally {
      setSetting(null);
    }
  };

  const handleTestModel = async (m: ResolvedModel) => {
    const key = `${m.provider_name}/${m.model}`;
    setTestingKey(key);
    try {
      const result = await request<{
        ok: boolean;
        latency_ms?: number;
        error?: string;
      }>(`/admin/providers/${m.provider_id}/test`, {
        method: "POST",
        body: JSON.stringify({ model_id: m.model }),
      });
      if (result.ok) {
        message.success(
          t("models.testSuccess", {
            name: modelOptionLabel(m),
            time: result.latency_ms ?? 0,
          }),
        );
        setTestResults((prev) => new Map(prev).set(key, "success"));
      } else {
        message.error(
          t("models.testFailed", { error: result.error ?? "unknown" }),
        );
        setTestResults((prev) => new Map(prev).set(key, "failure"));
      }
    } catch (err) {
      message.error(
        t("models.testFailed", {
          error: err instanceof Error ? err.message : String(err),
        }),
      );
      setTestResults((prev) => new Map(prev).set(key, "failure"));
    } finally {
      setTestingKey(null);
      setTimeout(() => {
        setTestResults((prev) => {
          const next = new Map(prev);
          next.delete(key);
          return next;
        });
      }, 2000);
    }
  };

  const renderCapabilityTags = (m: ResolvedModel) => (
    <ModelMetaTags
      includeText
      input={m.input}
      context_window={m.context_window}
      max_tokens={m.max_tokens}
      reasoning={m.reasoning}
      className={styles.poolModelTags}
    />
  );

  if (resolvedModels.length === 0) {
    return (
      <div className={styles.poolSection}>
        <div className={styles.poolHeader}>
          <div className={styles.poolHeaderLeft}>
            <h3 className={styles.slotTitle}>{t("models.modelPool")}</h3>
            <Tooltip title={t("models.autoRouteTooltip")}>
              <Info size={14} className={styles.poolInfoIcon} />
            </Tooltip>
          </div>
        </div>
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={t("models.noModelsAvailable")}
        />
      </div>
    );
  }

  return (
    <div className={styles.poolSection}>
      <div className={styles.poolHeader}>
        <div className={styles.poolHeaderLeft}>
          <h3 className={styles.slotTitle}>{t("models.modelPool")}</h3>
          <Tooltip title={t("models.autoRouteTooltip")}>
            <Info size={14} className={styles.poolInfoIcon} />
          </Tooltip>
        </div>
        <Tag color="green" className={styles.poolCountTag}>
          {t("models.modelCount", { count: resolvedModels.length })}
        </Tag>
      </div>

      <p className={styles.poolDesc}>{t("models.autoRouteDesc")}</p>

      <div className={styles.poolList}>
        {grouped.map((group) => (
          <div key={group.providerName} className={styles.poolGroup}>
            <div className={styles.poolGroupHeader}>
              <div className={styles.poolGroupHeaderLeft}>
                <span className={styles.poolGroupName}>
                  {group.providerName}
                </span>
                <Tag className={styles.poolGroupKind}>{group.providerKind}</Tag>
              </div>
              <span className={styles.poolGroupCount}>
                {group.models.length} {t("models.modelUnit")}
              </span>
            </div>
            <div className={styles.poolGroupModels}>
              {group.models.map((m) => {
                const key = `${m.provider_name}/${m.model}`;
                const isPreferred =
                  m.provider_name === activeModel.provider_name &&
                  m.model === activeModel.model;
                const isLoading = setting === key;
                const isTesting = testingKey === key;
                const canTest = providerHasKey.get(m.provider_id) ?? false;
                const capTags = renderCapabilityTags(m);
                const testState = testResults.get(key);

                return (
                  <div
                    key={key}
                    className={`${styles.poolModelRow} ${
                      isPreferred ? styles.poolModelPreferred : ""
                    }`}
                  >
                    <Tooltip
                      title={
                        isPreferred
                          ? t("models.currentPreferred")
                          : t("models.setAsPreferred")
                      }
                    >
                      <Button
                        type="text"
                        size="small"
                        loading={isLoading}
                        className={`${styles.preferredBtn} ${
                          isPreferred ? styles.preferredActive : ""
                        }`}
                        onClick={() => void handleSetPreferred(m)}
                        icon={
                          <Star
                            size={14}
                            fill={isPreferred ? "currentColor" : "none"}
                          />
                        }
                      />
                    </Tooltip>

                    <div className={styles.poolModelInfo}>
                      <span
                        className={styles.poolModelName}
                        title={modelOptionLabel(m)}
                      >
                        {modelOptionLabel(m)}
                      </span>
                    </div>

                    {capTags}

                    {canTest && (
                      <div className={styles.poolModelActions}>
                        {isTesting ? (
                          <Button type="text" size="small" loading />
                        ) : testState === "success" ? (
                          <Check size={14} style={{ color: "#52c41a" }} />
                        ) : testState === "failure" ? (
                          <X size={14} style={{ color: "#ff4d4f" }} />
                        ) : (
                          <Tooltip title={t("models.testConnection")}>
                            <Button
                              type="text"
                              size="small"
                              icon={<Zap size={14} />}
                              onClick={() => void handleTestModel(m)}
                            />
                          </Tooltip>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
