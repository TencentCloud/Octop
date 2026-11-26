import { useCallback, useEffect, useState } from "react";
import { Alert, Button, Card, Input, Select, Skeleton } from "antd";
import { Cpu, ScrollText } from "lucide-react";
import { useTranslation } from "react-i18next";
import PageShell from "../../../layouts/PageShell";
import { message } from "@/utils/antdMessage";
import {
  memoryDashboardApi,
  type GlobalMemoryDefaults,
} from "../../../api/modules/memoryDashboard";
import { providerApi } from "../../../api/modules/provider";
import {
  MODEL_AUTO_VALUE,
  buildModelSelectOptions,
  defaultModelFromForm,
  defaultModelToForm,
  type ModelPickerOption,
} from "../../../utils/modelOptions";
import styles from "./index.module.less";

const MAX_RULE_CHARS = 2000;

export default function AdminMemoryPage() {
  const { t } = useTranslation();
  const loadFailedMessage = t(
    "adminMemory.loadFailed",
    "全局记忆默认设置加载失败",
  );
  const [loading, setLoading] = useState(true);
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [defaults, setDefaults] = useState<GlobalMemoryDefaults | null>(null);
  const [saving, setSaving] = useState(false);
  const [auxModel, setAuxModel] = useState<string>(MODEL_AUTO_VALUE);
  const [keepRules, setKeepRules] = useState("");
  const [skipRules, setSkipRules] = useState("");
  const [models, setModels] = useState<ModelPickerOption[]>([]);
  const [modelsLoading, setModelsLoading] = useState(false);

  const applyDefaults = useCallback((data: GlobalMemoryDefaults) => {
    setAuxModel(defaultModelToForm(data.aux_model));
    setDefaults(data);
    setKeepRules(data.extract_keep_rules ?? "");
    setSkipRules(data.extract_skip_rules ?? "");
  }, []);

  useEffect(() => {
    let cancelled = false;
    setModelsLoading(true);
    providerApi
      .listResolvedModels()
      .then((data) => {
        if (!cancelled) setModels(data as ModelPickerOption[]);
      })
      .catch(() => {
        if (!cancelled) setModels([]);
      })
      .finally(() => {
        if (!cancelled) setModelsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    memoryDashboardApi
      .getGlobalMemoryDefaults()
      .then((data) => {
        if (!cancelled) applyDefaults(data);
      })
      .catch(() => {
        if (!cancelled) setDefaults(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [applyDefaults, loadAttempt]);

  const handleSave = async () => {
    if (!defaults) return;
    const patch: Parameters<
      typeof memoryDashboardApi.putGlobalMemoryDefaults
    >[0] = {};
    const model = defaultModelFromForm(auxModel);
    if (model !== defaults.aux_model) patch.aux_model = model;
    if (keepRules.trim() !== defaults.extract_keep_rules)
      patch.extract_keep_rules = keepRules.trim();
    if (skipRules.trim() !== defaults.extract_skip_rules)
      patch.extract_skip_rules = skipRules.trim();
    setSaving(true);
    try {
      const saved = await memoryDashboardApi.putGlobalMemoryDefaults(patch);
      applyDefaults(saved);
      const affected = saved.affected_agent_count ?? 0;
      message.success(
        affected > 0
          ? t(
              "adminMemory.savedWithAffected",
              "已保存全局记忆设置，此次变更影响 {{count}} 个继承设置的专家",
              { count: affected },
            )
          : t("adminMemory.saved", "已保存全局记忆设置"),
      );
    } catch {
      message.error(t("adminMemory.saveFailed", "保存全局记忆设置失败"));
    } finally {
      setSaving(false);
    }
  };

  const rulesUnsupported =
    Array.isArray(defaults?.supported_call_options) &&
    !defaults.supported_call_options.includes("extract_rules");

  return (
    <PageShell
      title={t("adminMemory.title", "全局记忆设置")}
      subtitle={t(
        "adminMemory.subtitle",
        "统一配置新建专家与未单独设置专家的默认记忆提取模型和记忆规则；专家可在各自记忆设置中单独覆盖。记忆内容仍按专家隔离。",
      )}
    >
      {loading ? (
        <div className={styles.page}>
          <Skeleton active paragraph={{ rows: 8 }} />
        </div>
      ) : !defaults ? (
        <Alert
          type="error"
          showIcon
          message={loadFailedMessage}
          action={
            <Button onClick={() => setLoadAttempt((attempt) => attempt + 1)}>
              {t("common.retry", "重试")}
            </Button>
          }
        />
      ) : (
        <div className={styles.page}>
          <Card className={styles.settingCard}>
            <div className={styles.sectionHeading}>
              <span className={styles.settingIcon}>
                <Cpu size={18} />
              </span>
              <div>
                <div className={styles.settingTitle}>
                  {t("adminMemory.extractModelTitle", "默认记忆提取模型")}
                </div>
                <div className={styles.settingDescription}>
                  {t(
                    "adminMemory.extractModelDescription",
                    "所有选择「继承全局」的专家将统一使用该模型在后台提取记忆；未设置时沿用各专家自己的对话模型。",
                  )}
                </div>
              </div>
            </div>

            <div className={styles.fields}>
              {auxModel === defaults.aux_model &&
              defaults.aux_model_usable === false ? (
                <Alert
                  type="warning"
                  showIcon
                  message={t(
                    "adminMemory.extractModelUnavailable",
                    "当前配置的全局提取模型不可用（对应服务商可能已禁用或删除），继承该配置的专家已自动回退到各自对话模型。请重新选择可用模型或恢复未设置。",
                  )}
                />
              ) : null}

              <Select
                aria-label={t(
                  "adminMemory.extractModelTitle",
                  "默认记忆提取模型",
                )}
                style={{ minWidth: 280, maxWidth: 440 }}
                value={auxModel}
                loading={modelsLoading}
                disabled={saving}
                onChange={setAuxModel}
                options={buildModelSelectOptions(
                  models,
                  t(
                    "adminMemory.extractModelUnset",
                    "未设置（沿用各专家对话模型）",
                  ),
                )}
                showSearch
                optionFilterProp="label"
              />
            </div>
          </Card>

          <Card className={styles.settingCard}>
            <div className={styles.sectionHeading}>
              <span className={styles.settingIcon}>
                <ScrollText size={18} />
              </span>
              <div>
                <div className={styles.settingTitle}>
                  {t("adminMemory.rulesTitle", "默认记忆规则")}
                </div>
                <div className={styles.settingDescription}>
                  {t(
                    "adminMemory.rulesDescription",
                    "定义哪些信息值得保留为长期记忆、哪些信息应跳过。留空时沿用内置默认规则。",
                  )}
                </div>
              </div>
            </div>

            <div className={styles.fields}>
              {rulesUnsupported ? (
                <Alert
                  type="info"
                  showIcon
                  message={t(
                    "adminMemory.rulesUnsupported",
                    "当前运行环境尚不支持自定义记忆规则。规则会保存，升级 octop-harness 和 octop-memory 后生效。",
                  )}
                />
              ) : null}

              <div className={styles.fieldBlock}>
                <label
                  htmlFor="admin-memory-keep-rules"
                  className={styles.fieldLabel}
                >
                  {t("adminMemory.keepRulesLabel", "值得保留为长期记忆的信息")}
                </label>
                <div className={styles.fieldHint}>
                  {t(
                    "adminMemory.keepRulesHint",
                    "例如：稳定的个人偏好、长期项目架构决策、后续协作会反复用到的约定与背景。",
                  )}
                </div>
                <Input.TextArea
                  id="admin-memory-keep-rules"
                  disabled={saving}
                  rows={4}
                  maxLength={MAX_RULE_CHARS}
                  showCount
                  value={keepRules}
                  onChange={(e) => setKeepRules(e.target.value)}
                  placeholder={t(
                    "adminMemory.keepRulesPlaceholder",
                    "描述需要优先记住的信息类型，留空表示仅使用内置默认规则",
                  )}
                />
              </div>

              <div className={styles.fieldBlock}>
                <label
                  htmlFor="admin-memory-skip-rules"
                  className={styles.fieldLabel}
                >
                  {t("adminMemory.skipRulesLabel", "应当跳过的信息")}
                </label>
                <div className={styles.fieldHint}>
                  {t(
                    "adminMemory.skipRulesHint",
                    "例如：一次性查询问答、寒暄闲聊、临时草稿或不需要沉淀的中间调试内容。",
                  )}
                </div>
                <Input.TextArea
                  id="admin-memory-skip-rules"
                  disabled={saving}
                  rows={4}
                  maxLength={MAX_RULE_CHARS}
                  showCount
                  value={skipRules}
                  onChange={(e) => setSkipRules(e.target.value)}
                  placeholder={t(
                    "adminMemory.skipRulesPlaceholder",
                    "描述不需要沉淀为长期记忆的信息类型，留空表示仅使用内置默认规则",
                  )}
                />
              </div>
            </div>
          </Card>

          <div className={styles.saveBar}>
            <span>
              {t(
                "adminMemory.saveHint",
                "修改后，采用「继承全局」的专家会自动采用新配置；已显式自定义相应项目的专家不受影响。",
              )}
            </span>
            <Button
              type="primary"
              loading={saving}
              onClick={() => void handleSave()}
            >
              {t("memory.settings.save", "保存设置")}
            </Button>
          </div>
        </div>
      )}
    </PageShell>
  );
}
