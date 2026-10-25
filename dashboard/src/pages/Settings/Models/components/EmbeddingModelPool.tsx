/**
 * EmbeddingModelPool — list all enabled embedding models (no preferred/default).
 */
import { useMemo, useState } from "react";
import { Check, Info, X, Zap } from "lucide-react";
import { Button, Empty, Space, Tag, Tooltip } from "antd";
import { Link } from "react-router-dom";
import { message } from "@/utils/antdMessage";
import { useTranslation } from "react-i18next";
import { request } from "../../../../api/request";
import type { ProviderModel, ProviderRow } from "../useProviders";
import { isEmbeddingModel } from "../useProviders";
import { isOnnxProviderRow } from "../presetUtils";
import styles from "../index.module.less";

interface EmbeddingModelPoolProps {
  providers: ProviderRow[];
  /** Brief highlight after a provider/model save. */
  flash?: boolean;
  showServicesCta?: boolean;
  onScrollToServices?: () => void;
}

interface PoolEntry {
  providerId: number;
  providerName: string;
  providerKind: string;
  model: ProviderModel;
}

interface Grouped {
  providerId: number;
  providerName: string;
  providerKind: string;
  models: ProviderModel[];
}

export function EmbeddingModelPool({
  providers,
  flash = false,
  showServicesCta = false,
  onScrollToServices,
}: EmbeddingModelPoolProps) {
  const { t } = useTranslation();
  const [testingKey, setTestingKey] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<
    Map<string, "success" | "failure">
  >(new Map());

  const entries = useMemo(() => {
    const out: PoolEntry[] = [];
    for (const provider of providers) {
      if (!provider.enabled || !provider.api_key) continue;
      const onnx = isOnnxProviderRow(provider);
      const embeddingLane = onnx || provider.purpose === "embedding";
      for (const model of provider.models ?? []) {
        if (model.enabled === false) continue;
        if (!embeddingLane && !isEmbeddingModel(model)) continue;
        out.push({
          providerId: provider.id,
          providerName: provider.name,
          providerKind: provider.kind,
          model,
        });
      }
    }
    return out;
  }, [providers]);

  const grouped = useMemo(() => {
    const map = new Map<string, Grouped>();
    for (const entry of entries) {
      let group = map.get(entry.providerName);
      if (!group) {
        group = {
          providerId: entry.providerId,
          providerName: entry.providerName,
          providerKind: entry.providerKind,
          models: [],
        };
        map.set(entry.providerName, group);
      }
      group.models.push(entry.model);
    }
    return Array.from(map.values());
  }, [entries]);

  const handleTest = async (entry: PoolEntry) => {
    const key = `${entry.providerName}/${entry.model.id}`;
    setTestingKey(key);
    try {
      const result = await request<{
        ok: boolean;
        latency_ms?: number;
        error?: string;
      }>(`/admin/providers/${entry.providerId}/test`, {
        method: "POST",
        body: JSON.stringify({ model_id: entry.model.id, embedding: true }),
      });
      if (result.ok) {
        message.success(
          t("models.testSuccess", {
            name: entry.model.name || entry.model.id,
            time: result.latency_ms ?? 0,
          }),
        );
        setTestResults((prev) => new Map(prev).set(key, "success"));
        window.setTimeout(() => {
          setTestResults((prev) => {
            const next = new Map(prev);
            next.delete(key);
            return next;
          });
        }, 2500);
      } else {
        message.error(
          t("models.testFailed", { error: result.error ?? "unknown" }),
        );
        setTestResults((prev) => new Map(prev).set(key, "failure"));
        // Keep failure icon until the next test attempt.
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
    }
  };

  const sectionClass = flash
    ? `${styles.poolSection} ${styles.poolSectionFlash}`
    : styles.poolSection;

  if (entries.length === 0) {
    return (
      <div className={sectionClass}>
        <div className={styles.poolHeader}>
          <div className={styles.poolHeaderLeft}>
            <h3 className={styles.slotTitle}>
              {t("models.embeddingModelPool")}
            </h3>
            <Tooltip title={t("models.embeddingModelPoolTooltip")}>
              <Info size={14} className={styles.poolInfoIcon} />
            </Tooltip>
          </div>
        </div>
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={
            <div className={styles.poolEmptyBody}>
              <p className={styles.poolEmptyText}>
                {t("models.embeddingModelPoolEmpty")}
              </p>
              {showServicesCta ? (
                <Space wrap className={styles.poolEmptyActions}>
                  <Button type="primary" onClick={onScrollToServices}>
                    {t("models.embeddingPoolCtaServices")}
                  </Button>
                </Space>
              ) : null}
            </div>
          }
        />
      </div>
    );
  }

  return (
    <div className={sectionClass}>
      <div className={styles.poolHeader}>
        <div className={styles.poolHeaderLeft}>
          <h3 className={styles.slotTitle}>{t("models.embeddingModelPool")}</h3>
          <Tooltip title={t("models.embeddingModelPoolTooltip")}>
            <Info size={14} className={styles.poolInfoIcon} />
          </Tooltip>
        </div>
        <div className={styles.poolHeaderRight}>
          <Link to="/knowledge-bases" className={styles.poolHeaderLink}>
            {t("models.embeddingPoolKnowledgeLink")}
          </Link>
          <Tag color="green" className={styles.poolCountTag}>
            {t("models.modelCount", { count: entries.length })}
          </Tag>
        </div>
      </div>
      <p className={styles.poolDesc}>{t("models.embeddingModelPoolDesc")}</p>
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
              {group.models.map((model) => {
                const key = `${group.providerName}/${model.id}`;
                const isTesting = testingKey === key;
                const testState = testResults.get(key);
                return (
                  <div key={key} className={styles.poolModelRow}>
                    <div className={styles.poolModelInfo}>
                      <span
                        className={styles.poolModelName}
                        title={model.name || model.id}
                      >
                        {model.name || model.id}
                      </span>
                      {model.id !== model.name && model.name ? (
                        <span className={styles.poolModelId}>{model.id}</span>
                      ) : null}
                    </div>
                    <div className={styles.poolModelActions}>
                      {isTesting ? (
                        <Button type="text" size="small" loading />
                      ) : testState === "success" ? (
                        <Tooltip title={t("models.testConnection")}>
                          <Check size={14} style={{ color: "#52c41a" }} />
                        </Tooltip>
                      ) : testState === "failure" ? (
                        <Tooltip title={t("models.embeddingPoolRetest")}>
                          <Button
                            type="text"
                            size="small"
                            danger
                            icon={<X size={14} />}
                            onClick={() =>
                              void handleTest({
                                providerId: group.providerId,
                                providerName: group.providerName,
                                providerKind: group.providerKind,
                                model,
                              })
                            }
                          />
                        </Tooltip>
                      ) : (
                        <Tooltip title={t("models.testConnection")}>
                          <Button
                            type="text"
                            size="small"
                            icon={<Zap size={14} />}
                            onClick={() =>
                              void handleTest({
                                providerId: group.providerId,
                                providerName: group.providerName,
                                providerKind: group.providerKind,
                                model,
                              })
                            }
                          />
                        </Tooltip>
                      )}
                    </div>
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
