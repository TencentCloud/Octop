import { Link } from "react-router-dom";
import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Collapse,
  Input,
  InputNumber,
  Radio,
  Select,
  Skeleton,
  Space,
  Switch,
  Typography,
} from "antd";
import { message } from "@/utils/antdMessage";

import {
  Brain,
  Cpu,
  Database,
  ScrollText,
  SlidersHorizontal,
  Sparkles,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import cx from "classnames";

import {
  memoryDashboardApi,
  type ExtractConfig,
  type ExtractTriggerMode,
  type GlobalMemoryDefaults,
  type MemoryOverrideMode,
} from "../../../api/modules/memoryDashboard";
import { providerApi } from "../../../api/modules/provider";
import { useCurrentUser } from "../../../hooks/useCurrentUser";
import { userCan } from "../../../utils/permissions";
import {
  MODEL_AUTO_VALUE,
  buildModelSelectOptions,
  defaultModelFromForm,
  defaultModelToForm,
  type ModelPickerOption,
} from "../../../utils/modelOptions";
import styles from "./MemorySettings.module.less";
import MemoryStorage from "./MemoryStorage";

interface Props {
  agentId: string;
}

const MIN_IDLE_MINUTES = 1;
const MIN_INTERVAL_HOURS = 0.1;
/** 0 means "automatic" on the wire: the backend normalizes it back to null. */
const AUTO_SENTINEL = 0;
const MAX_AUX_TIMEOUT_S = 3600;
const MAX_AUX_TOKENS = 65536;
const MAX_RULE_CHARS = 2000;

export default function MemorySettings({ agentId }: Props) {
  const { t } = useTranslation();
  const currentUser = useCurrentUser();
  const canEditGlobalMemory = userCan(currentUser, "memory_defaults");
  const loadFailedMessage = t("memory.settings.loadFailed", "记忆设置加载失败");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [memoryEnabled, setMemoryEnabled] = useState(true);
  const [mode, setMode] = useState<ExtractTriggerMode>("idle");
  const [idleMinutes, setIdleMinutes] = useState(5);
  const [intervalHours, setIntervalHours] = useState(6);
  const [auxModelMode, setAuxModelMode] =
    useState<MemoryOverrideMode>("inherit");
  const [auxModel, setAuxModel] = useState<string>(MODEL_AUTO_VALUE);
  const [rulesMode, setRulesMode] = useState<MemoryOverrideMode>("inherit");
  const [keepRules, setKeepRules] = useState("");
  const [skipRules, setSkipRules] = useState("");
  const [globalDefaults, setGlobalDefaults] = useState<GlobalMemoryDefaults>({
    aux_model: null,
    aux_model_usable: true,
    extract_keep_rules: "",
    extract_skip_rules: "",
  });
  const [models, setModels] = useState<ModelPickerOption[]>([]);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [extractMaxTokens, setExtractMaxTokens] =
    useState<number>(AUTO_SENTINEL);
  const [lightTimeoutS, setLightTimeoutS] = useState<number>(AUTO_SENTINEL);
  const [heavyTimeoutS, setHeavyTimeoutS] = useState<number>(AUTO_SENTINEL);
  const [thinking, setThinking] = useState<"auto" | "off" | "on">("auto");
  const [maxRetries, setMaxRetries] = useState(2);
  const [retryBackoffS, setRetryBackoffS] = useState(1);
  const [extraBody, setExtraBody] = useState("");
  const [extraBodyError, setExtraBodyError] = useState(false);
  const [supportedCallOptions, setSupportedCallOptions] = useState<
    string[] | undefined
  >();

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

  const applyConfig = useCallback((cfg: ExtractConfig) => {
    setMemoryEnabled(cfg.memory_enabled ?? true);
    setMode(cfg.extract_trigger_mode);
    const inferredAuxMode: MemoryOverrideMode =
      cfg.aux_model_mode ?? (cfg.aux_model ? "custom" : "inherit");
    setAuxModelMode(inferredAuxMode);
    setAuxModel(defaultModelToForm(cfg.aux_model));
    const inferredRulesMode: MemoryOverrideMode =
      cfg.extract_rules_mode ??
      (cfg.extract_keep_rules || cfg.extract_skip_rules ? "custom" : "inherit");
    setRulesMode(inferredRulesMode);
    setKeepRules(cfg.extract_keep_rules ?? "");
    setSkipRules(cfg.extract_skip_rules ?? "");
    setGlobalDefaults({
      aux_model: cfg.global_defaults?.aux_model ?? null,
      aux_model_usable: cfg.global_defaults?.aux_model_usable ?? true,
      extract_keep_rules: cfg.global_defaults?.extract_keep_rules ?? "",
      extract_skip_rules: cfg.global_defaults?.extract_skip_rules ?? "",
    });
    setSupportedCallOptions(cfg.supported_call_options);
    setThinking(cfg.extract_thinking ?? "auto");
    setMaxRetries(cfg.extract_max_retries ?? 2);
    setRetryBackoffS(cfg.extract_retry_backoff_s ?? 1);
    setExtraBody(
      cfg.extract_extra_body
        ? JSON.stringify(cfg.extract_extra_body, null, 2)
        : "",
    );
    setExtraBodyError(false);
    setIdleMinutes(
      Math.max(
        MIN_IDLE_MINUTES,
        Math.round((cfg.extract_idle_seconds / 60) * 10) / 10,
      ),
    );
    setIntervalHours(
      Math.round((cfg.extract_interval_seconds / 3600) * 10) / 10,
    );
    setExtractMaxTokens(
      typeof cfg.extract_max_tokens === "number" && cfg.extract_max_tokens > 0
        ? cfg.extract_max_tokens
        : AUTO_SENTINEL,
    );
    setLightTimeoutS(
      typeof cfg.extract_light_timeout_s === "number" &&
        cfg.extract_light_timeout_s > 0
        ? cfg.extract_light_timeout_s
        : AUTO_SENTINEL,
    );
    setHeavyTimeoutS(
      typeof cfg.extract_heavy_timeout_s === "number" &&
        cfg.extract_heavy_timeout_s > 0
        ? cfg.extract_heavy_timeout_s
        : AUTO_SENTINEL,
    );
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    memoryDashboardApi
      .getExtractConfig(agentId)
      .then((cfg) => {
        if (!cancelled) applyConfig(cfg);
      })
      .catch(() => {
        if (!cancelled) {
          message.error(loadFailedMessage);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [agentId, applyConfig, loadFailedMessage]);

  const handleSave = async () => {
    let parsedExtraBody: Record<string, unknown>;
    try {
      const parsed: unknown = extraBody.trim() ? JSON.parse(extraBody) : {};
      if (
        parsed === null ||
        Array.isArray(parsed) ||
        typeof parsed !== "object"
      )
        throw new Error("object required");
      parsedExtraBody = parsed as Record<string, unknown>;
      setExtraBodyError(false);
    } catch {
      setExtraBodyError(true);
      message.error(
        t(
          "memory.settings.extraBodyInvalid",
          "模型扩展参数必须是有效的 JSON 对象",
        ),
      );
      return;
    }
    setSaving(true);
    try {
      const cfg = await memoryDashboardApi.putExtractConfig(agentId, {
        memory_enabled: memoryEnabled,
        extract_on_session_end: true,
        extract_trigger_mode: mode,
        extract_idle_seconds: Math.round(
          Math.max(MIN_IDLE_MINUTES, idleMinutes) * 60,
        ),
        extract_interval_seconds: Math.round(intervalHours * 3600),
        aux_model_mode: auxModelMode,
        aux_model:
          auxModelMode === "custom" ? defaultModelFromForm(auxModel) : null,
        extract_rules_mode: rulesMode,
        extract_keep_rules: rulesMode === "custom" ? keepRules.trim() : "",
        extract_skip_rules: rulesMode === "custom" ? skipRules.trim() : "",
        extract_max_tokens:
          extractMaxTokens > 0 ? extractMaxTokens : AUTO_SENTINEL,
        extract_light_timeout_s:
          lightTimeoutS > 0 ? lightTimeoutS : AUTO_SENTINEL,
        extract_heavy_timeout_s:
          heavyTimeoutS > 0 ? heavyTimeoutS : AUTO_SENTINEL,
        extract_thinking: thinking,
        extract_max_retries: maxRetries,
        extract_retry_backoff_s: retryBackoffS,
        extract_extra_body: parsedExtraBody,
      });
      applyConfig(cfg);
      message.success(t("memory.settings.saved", "已保存，agent 将自动重载"));
    } catch {
      message.error(t("memory.settings.saveFailed", "保存失败"));
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className={styles.settingsPage}>
        <Skeleton active paragraph={{ rows: 8 }} />
      </div>
    );
  }

  return (
    <div className={styles.settingsPage}>
      <header className={styles.pageHeader}>
        <div className={styles.headerIcon}>
          <Brain size={22} />
        </div>
        <div>
          <h2>{t("memory.settings.title", "记忆设置")}</h2>
          <p>
            {t(
              "memory.settings.description",
              "控制这个 Agent 是否使用记忆，以及对话内容何时被整理成长期记忆。",
            )}
          </p>
        </div>
      </header>

      <Card className={styles.settingCard}>
        <div className={styles.settingRow}>
          <div className={styles.settingIdentity}>
            <span className={styles.settingIcon}>
              <Database size={18} />
            </span>
            <div>
              <div className={styles.settingTitle}>
                {t("memory.settings.storageTitle", "存储记忆")}
              </div>
              <div className={styles.settingDescription}>
                {t(
                  "memory.settings.storageDescription",
                  "允许 Agent 读取已有记忆，并从新对话中持续积累记忆。",
                )}
              </div>
            </div>
          </div>
          <div className={styles.switchBlock}>
            <span
              className={memoryEnabled ? styles.statusOn : styles.statusOff}
            >
              {memoryEnabled
                ? t("memory.settings.enabled", "已开启")
                : t("memory.settings.disabled", "已关闭")}
            </span>
            <Switch checked={memoryEnabled} onChange={setMemoryEnabled} />
          </div>
        </div>

        {!memoryEnabled ? (
          <Alert
            className={styles.memoryWarning}
            type="warning"
            showIcon
            message={t(
              "memory.settings.disabledTitle",
              "关闭后 Agent 将不再使用记忆",
            )}
            description={t(
              "memory.settings.disabledDescription",
              "Agent 不会读取已有记忆，也不会捕获或提炼新的记忆。已有记忆和对话记录不会被删除，重新开启后可以继续使用。",
            )}
          />
        ) : null}
      </Card>

      <Card
        className={cx(
          styles.settingCard,
          !memoryEnabled && styles.cardDisabled,
        )}
      >
        <div className={styles.sectionHeading}>
          <span className={styles.settingIcon}>
            <Sparkles size={18} />
          </span>
          <div>
            <div className={styles.settingTitle}>
              {t("memory.settings.distillTitle", "记忆提炼时机")}
            </div>
            <div className={styles.settingDescription}>
              {t(
                "memory.settings.distillDescription",
                "选择何时把对话记忆整理为可召回的长期记忆。",
              )}
            </div>
          </div>
        </div>

        <fieldset className={styles.strategyFields} disabled={!memoryEnabled}>
          <Radio.Group
            value={mode}
            onChange={(event) =>
              setMode(event.target.value as ExtractTriggerMode)
            }
          >
            <Space direction="vertical" size={14}>
              <Radio value="idle">
                <span className={styles.radioTitle}>
                  {t("memory.extractConfig.modeIdle", "对话空闲后提炼")}
                </span>
                <Typography.Text type="secondary" className={styles.radioHint}>
                  {t(
                    "memory.extractConfig.modeIdleHint",
                    "等对话安静一段时间再提炼，记忆质量最好（推荐）",
                  )}
                </Typography.Text>
              </Radio>
              <Radio value="interval">
                <span className={styles.radioTitle}>
                  {t("memory.extractConfig.modeInterval", "固定间隔提炼")}
                </span>
                <Typography.Text type="secondary" className={styles.radioHint}>
                  {t(
                    "memory.extractConfig.modeIntervalHint",
                    "按固定周期批量整理，可能包含尚未结束的对话",
                  )}
                </Typography.Text>
              </Radio>
            </Space>
          </Radio.Group>

          <div className={styles.timeControl}>
            {mode === "idle" ? (
              <>
                <span>{t("memory.extractConfig.idlePrefix", "对话空闲")}</span>
                <InputNumber
                  min={MIN_IDLE_MINUTES}
                  max={7 * 24 * 60}
                  value={idleMinutes}
                  onChange={(value) =>
                    setIdleMinutes(
                      Math.max(MIN_IDLE_MINUTES, value ?? MIN_IDLE_MINUTES),
                    )
                  }
                />
                <span>{t("memory.extractConfig.minutes", "分钟后提炼")}</span>
              </>
            ) : (
              <>
                <span>{t("memory.extractConfig.intervalPrefix", "每隔")}</span>
                <InputNumber
                  min={MIN_INTERVAL_HOURS}
                  max={7 * 24}
                  step={0.5}
                  value={intervalHours}
                  onChange={(value) =>
                    setIntervalHours(value ?? MIN_INTERVAL_HOURS)
                  }
                />
                <span>{t("memory.extractConfig.hours", "小时提炼一次")}</span>
              </>
            )}
          </div>

          {mode === "interval" ? (
            <Alert
              type="info"
              showIcon
              message={t(
                "memory.extractConfig.intervalNote",
                "固定间隔可能在会话尚未结束时运行；多数场景推荐使用“对话空闲后提炼”。",
              )}
            />
          ) : null}
          <Alert
            type="info"
            showIcon
            message={t(
              "memory.settings.timeoutVsIdleNote",
              "空闲时间只决定何时开始提炼；请求超时决定每次请求最多等多久。超时或临时服务错误会按设置重试，重试和模型回退可能延长总耗时。思考参数仅在模型支持时生效。",
            )}
          />
        </fieldset>
      </Card>

      <Card
        className={cx(
          styles.settingCard,
          !memoryEnabled && styles.cardDisabled,
        )}
      >
        <div className={styles.overrideHeader}>
          <div className={styles.sectionHeading}>
            <span className={styles.settingIcon}>
              <Cpu size={18} />
            </span>
            <div>
              <div className={styles.settingTitle}>
                {t("memory.settings.extractModelTitle", "记忆提取模型")}
              </div>
              <div className={styles.settingDescription}>
                {t(
                  "memory.settings.extractModelDescription",
                  "提炼记忆时调用的模型。默认继承全局设置，也可为当前专家单独指定模型或跟随其对话模型。",
                )}
              </div>
            </div>
          </div>
          <Radio.Group
            optionType="button"
            size="small"
            disabled={!memoryEnabled}
            value={auxModelMode}
            onChange={(e) => {
              const next = e.target.value as MemoryOverrideMode;
              setAuxModelMode(next);
              if (
                next === "custom" &&
                auxModel === MODEL_AUTO_VALUE &&
                globalDefaults.aux_model &&
                globalDefaults.aux_model_usable !== false
              ) {
                setAuxModel(defaultModelToForm(globalDefaults.aux_model));
              }
            }}
            aria-label={t(
              "memory.settings.extractModelSource",
              "记忆提取模型来源",
            )}
            options={[
              {
                value: "inherit",
                label: t("memory.settings.inheritGlobal", "继承全局"),
              },
              {
                value: "custom",
                label: t("memory.settings.customOverride", "自定义"),
              },
            ]}
          />
        </div>
        <fieldset className={styles.strategyFields} disabled={!memoryEnabled}>
          {auxModelMode === "inherit" ? (
            <div className={styles.inheritSummary}>
              <div className={styles.inheritRow}>
                <span>
                  {globalDefaults.aux_model
                    ? globalDefaults.aux_model_usable === false
                      ? t(
                          "memory.settings.inheritModelUnavailable",
                          "当前继承全局：{{model}}（该模型当前不可用，已自动回退到本专家对话模型）",
                          { model: globalDefaults.aux_model },
                        )
                      : t(
                          "memory.settings.inheritModelValue",
                          "当前继承全局：{{model}}",
                          { model: globalDefaults.aux_model },
                        )
                    : t(
                        "memory.settings.inheritModelUnset",
                        "当前继承全局：未设置（沿用本专家对话模型）",
                      )}
                </span>
                {canEditGlobalMemory ? (
                  <Link to="/admin/memory">
                    {t("memory.settings.manageGlobalMemory", "管理全局默认")}
                  </Link>
                ) : null}
              </div>
            </div>
          ) : (
            <div className={styles.customControlsRow}>
              <Select
                aria-label={t(
                  "memory.settings.extractModelTitle",
                  "记忆提取模型",
                )}
                style={{ minWidth: 280, maxWidth: 420 }}
                value={auxModel}
                loading={modelsLoading}
                disabled={!memoryEnabled}
                onChange={setAuxModel}
                options={buildModelSelectOptions(
                  models,
                  t("memory.settings.extractModelAuto", "自动（跟随对话模型）"),
                )}
                showSearch
                optionFilterProp="label"
              />
              <Button
                type="link"
                size="small"
                disabled={!memoryEnabled}
                onClick={() => {
                  setAuxModelMode("inherit");
                  setAuxModel(MODEL_AUTO_VALUE);
                }}
              >
                {t("memory.settings.restoreInherit", "恢复继承全局")}
              </Button>
            </div>
          )}
        </fieldset>
      </Card>

      <Card
        className={cx(
          styles.settingCard,
          !memoryEnabled && styles.cardDisabled,
        )}
      >
        <div className={styles.overrideHeader}>
          <div className={styles.sectionHeading}>
            <span className={styles.settingIcon}>
              <ScrollText size={18} />
            </span>
            <div>
              <div className={styles.settingTitle}>
                {t("memory.settings.rulesTitle", "记忆规则")}
              </div>
              <div className={styles.settingDescription}>
                {t(
                  "memory.settings.rulesDescription",
                  "定义哪些信息值得保留为长期记忆、哪些信息应跳过。默认继承全局规则，也可为当前专家单独覆盖。",
                )}
              </div>
            </div>
          </div>
          <Radio.Group
            optionType="button"
            size="small"
            disabled={!memoryEnabled}
            value={rulesMode}
            onChange={(e) => {
              const next = e.target.value as MemoryOverrideMode;
              setRulesMode(next);
              if (next === "custom" && !keepRules && !skipRules) {
                if (globalDefaults.extract_keep_rules) {
                  setKeepRules(globalDefaults.extract_keep_rules);
                }
                if (globalDefaults.extract_skip_rules) {
                  setSkipRules(globalDefaults.extract_skip_rules);
                }
              }
            }}
            aria-label={t("memory.settings.rulesSource", "记忆规则来源")}
            options={[
              {
                value: "inherit",
                label: t("memory.settings.inheritGlobal", "继承全局"),
              },
              {
                value: "custom",
                label: t("memory.settings.customOverride", "自定义"),
              },
            ]}
          />
        </div>
        <fieldset className={styles.strategyFields} disabled={!memoryEnabled}>
          {Array.isArray(supportedCallOptions) &&
          !supportedCallOptions.includes("extract_rules") ? (
            <Alert
              type="info"
              showIcon
              message={t(
                "memory.settings.rulesUnsupported",
                "当前运行环境尚不支持自定义记忆规则。规则会保存，升级 octop-harness 和 octop-memory 后生效。",
              )}
            />
          ) : null}

          {rulesMode === "inherit" ? (
            <div className={styles.inheritSummary}>
              {globalDefaults.extract_keep_rules ||
              globalDefaults.extract_skip_rules ? (
                <>
                  {globalDefaults.extract_keep_rules ? (
                    <div className={styles.inheritRuleBlock}>
                      <span className={styles.inheritRuleLabel}>
                        {t(
                          "memory.settings.keepRulesLabel",
                          "值得保留为长期记忆的信息",
                        )}
                      </span>
                      <span className={styles.inheritRuleText}>
                        {globalDefaults.extract_keep_rules}
                      </span>
                    </div>
                  ) : null}
                  {globalDefaults.extract_skip_rules ? (
                    <div className={styles.inheritRuleBlock}>
                      <span className={styles.inheritRuleLabel}>
                        {t("memory.settings.skipRulesLabel", "应当跳过的信息")}
                      </span>
                      <span className={styles.inheritRuleText}>
                        {globalDefaults.extract_skip_rules}
                      </span>
                    </div>
                  ) : null}
                </>
              ) : (
                <div className={styles.inheritRow}>
                  <span>
                    {t(
                      "memory.settings.inheritRulesUnset",
                      "当前继承全局：未设置自定义规则（沿用内置默认策略）",
                    )}
                  </span>
                  {canEditGlobalMemory ? (
                    <Link to="/admin/memory">
                      {t("memory.settings.manageGlobalMemory", "管理全局默认")}
                    </Link>
                  ) : null}
                </div>
              )}
            </div>
          ) : (
            <>
              <div className={styles.ruleField}>
                <label
                  htmlFor="expert-memory-keep-rules"
                  className={styles.ruleFieldLabel}
                >
                  {t(
                    "memory.settings.keepRulesLabel",
                    "值得保留为长期记忆的信息",
                  )}
                </label>
                <div className={styles.ruleFieldHint}>
                  {t(
                    "memory.settings.keepRulesHint",
                    "例如：该专家专属领域的长期决策、客户约束、偏好与后续必用信息。",
                  )}
                </div>
                <Input.TextArea
                  id="expert-memory-keep-rules"
                  rows={3}
                  maxLength={MAX_RULE_CHARS}
                  showCount
                  disabled={!memoryEnabled}
                  value={keepRules}
                  onChange={(e) => setKeepRules(e.target.value)}
                  placeholder={t(
                    "memory.settings.keepRulesPlaceholder",
                    "描述需要优先记住的信息，留空表示不额外指定",
                  )}
                />
              </div>

              <div className={styles.ruleField}>
                <label
                  htmlFor="expert-memory-skip-rules"
                  className={styles.ruleFieldLabel}
                >
                  {t("memory.settings.skipRulesLabel", "应当跳过的信息")}
                </label>
                <div className={styles.ruleFieldHint}>
                  {t(
                    "memory.settings.skipRulesHint",
                    "例如：临时草稿、一次性问答或无需长期留存的上下文。",
                  )}
                </div>
                <Input.TextArea
                  id="expert-memory-skip-rules"
                  rows={3}
                  maxLength={MAX_RULE_CHARS}
                  showCount
                  disabled={!memoryEnabled}
                  value={skipRules}
                  onChange={(e) => setSkipRules(e.target.value)}
                  placeholder={t(
                    "memory.settings.skipRulesPlaceholder",
                    "描述应跳过的信息，留空表示不额外指定",
                  )}
                />
              </div>

              <div>
                <Button
                  type="link"
                  size="small"
                  style={{ paddingLeft: 0 }}
                  disabled={!memoryEnabled}
                  onClick={() => {
                    setRulesMode("inherit");
                    setKeepRules("");
                    setSkipRules("");
                  }}
                >
                  {t("memory.settings.restoreInherit", "恢复继承全局")}
                </Button>
              </div>
            </>
          )}
        </fieldset>
      </Card>

      <Collapse
        className={styles.advancedSettings}
        expandIconPosition="end"
        items={[
          {
            key: "advanced",
            label: (
              <div className={styles.sectionHeading}>
                <span className={styles.settingIcon}>
                  <SlidersHorizontal size={18} />
                </span>
                <div>
                  <div className={styles.settingTitle}>
                    {t("memory.settings.advancedTitle", "记忆高级设置")}
                  </div>
                  <div className={styles.settingDescription}>
                    {t(
                      "memory.settings.advancedDescription",
                      "调整提炼调用参数，检查记忆存储并查看维护进度。",
                    )}
                  </div>
                </div>
              </div>
            ),
            children: (
              <>
                <Typography.Title level={5}>
                  {t("memory.settings.callParametersTitle", "提炼调用参数")}
                </Typography.Title>
                <fieldset
                  className={styles.strategyFields}
                  disabled={!memoryEnabled}
                >
                  <Space direction="vertical" size={14}>
                    {supportedCallOptions &&
                      [
                        "extract_max_tokens",
                        "extract_light_timeout_s",
                        "extract_heavy_timeout_s",
                        "extract_thinking",
                        "extract_extra_body",
                        "extract_max_retries",
                        "extract_retry_backoff_s",
                      ].some((key) => !supportedCallOptions.includes(key)) && (
                        <Alert
                          type="warning"
                          showIcon
                          message={t(
                            "memory.settings.upgradeRequired",
                            "当前版本尚不支持全部调用设置",
                          )}
                          description={t(
                            "memory.settings.upgradeHint",
                            "请配套更新记忆运行组件（octop-harness）。当前不可用的设置已禁用，更新后会恢复。",
                          )}
                        />
                      )}
                    <div className={styles.timeControl}>
                      <span>
                        {t(
                          "memory.settings.maxTokensLabel",
                          "单次提炼最多生成",
                        )}
                      </span>
                      <InputNumber
                        aria-label={t(
                          "memory.settings.maxTokensLabel",
                          "单次提炼最多生成",
                        )}
                        disabled={
                          supportedCallOptions &&
                          !supportedCallOptions.includes("extract_max_tokens")
                        }
                        precision={0}
                        min={0}
                        max={MAX_AUX_TOKENS}
                        value={extractMaxTokens}
                        onChange={(value) =>
                          setExtractMaxTokens(
                            Math.max(0, value ?? AUTO_SENTINEL),
                          )
                        }
                      />
                      <span>
                        {t(
                          "memory.settings.maxTokensSuffix",
                          "token（0 为默认 2048；最小 128）",
                        )}
                      </span>
                    </div>
                    <div className={styles.timeControl}>
                      <span>
                        {t(
                          "memory.settings.lightTimeoutLabel",
                          "单次提炼请求超时",
                        )}
                      </span>
                      <InputNumber
                        aria-label={t(
                          "memory.settings.lightTimeoutLabel",
                          "单次提炼请求超时",
                        )}
                        min={0}
                        max={MAX_AUX_TIMEOUT_S}
                        disabled={
                          supportedCallOptions &&
                          !supportedCallOptions.includes(
                            "extract_light_timeout_s",
                          )
                        }
                        value={lightTimeoutS}
                        onChange={(value) =>
                          setLightTimeoutS(Math.max(0, value ?? AUTO_SENTINEL))
                        }
                      />
                      <span>
                        {t(
                          "memory.settings.lightTimeoutSuffix",
                          "秒（0 为默认 120；范围 30–3600）",
                        )}
                      </span>
                    </div>
                    <div className={styles.timeControl}>
                      <span>
                        {t("memory.settings.heavyTimeoutLabel", "整理请求超时")}
                      </span>
                      <InputNumber
                        aria-label={t(
                          "memory.settings.heavyTimeoutLabel",
                          "整理请求超时",
                        )}
                        min={0}
                        max={MAX_AUX_TIMEOUT_S}
                        disabled={
                          supportedCallOptions &&
                          !supportedCallOptions.includes(
                            "extract_heavy_timeout_s",
                          )
                        }
                        value={heavyTimeoutS}
                        onChange={(value) =>
                          setHeavyTimeoutS(Math.max(0, value ?? AUTO_SENTINEL))
                        }
                      />
                      <span>
                        {t(
                          "memory.settings.heavyTimeoutSuffix",
                          "秒（0 为默认 300；范围 30–3600）",
                        )}
                      </span>
                    </div>
                    <div className={styles.timeControl}>
                      <span>
                        {t("memory.settings.thinkingLabel", "提炼思考模式")}
                      </span>
                      <Select
                        aria-label={t(
                          "memory.settings.thinkingLabel",
                          "提炼思考模式",
                        )}
                        style={{ minWidth: 240 }}
                        value={thinking}
                        disabled={
                          !memoryEnabled ||
                          (supportedCallOptions &&
                            !supportedCallOptions.includes("extract_thinking"))
                        }
                        onChange={setThinking}
                        options={[
                          {
                            value: "auto",
                            label: t(
                              "memory.settings.thinkingAuto",
                              "自动（已适配模型关闭思考）",
                            ),
                          },
                          {
                            value: "off",
                            label: t(
                              "memory.settings.thinkingOff",
                              "关闭（模型支持时）",
                            ),
                          },
                          {
                            value: "on",
                            label: t(
                              "memory.settings.thinkingDefault",
                              "沿用模型默认",
                            ),
                          },
                        ]}
                      />
                    </div>
                    <div className={styles.timeControl}>
                      <span>
                        {t("memory.settings.retriesLabel", "失败重试次数")}
                      </span>
                      <InputNumber
                        aria-label={t(
                          "memory.settings.retriesLabel",
                          "失败重试次数",
                        )}
                        disabled={
                          supportedCallOptions &&
                          !supportedCallOptions.includes("extract_max_retries")
                        }
                        min={0}
                        max={10}
                        precision={0}
                        value={maxRetries}
                        onChange={(value) => setMaxRetries(value ?? 2)}
                      />
                      <span>
                        {t(
                          "memory.settings.retriesHint",
                          "次（0 为不重试，默认 2）",
                        )}
                      </span>
                    </div>
                    <div className={styles.timeControl}>
                      <span>
                        {t("memory.settings.backoffLabel", "首次重试间隔")}
                      </span>
                      <InputNumber
                        aria-label={t(
                          "memory.settings.backoffLabel",
                          "首次重试间隔",
                        )}
                        disabled={
                          supportedCallOptions &&
                          !supportedCallOptions.includes(
                            "extract_retry_backoff_s",
                          )
                        }
                        min={0}
                        max={60}
                        step={0.5}
                        value={retryBackoffS}
                        onChange={(value) => setRetryBackoffS(value ?? 1)}
                      />
                      <span>
                        {t(
                          "memory.settings.backoffHint",
                          "秒（后续翻倍，最多 60 秒）",
                        )}
                      </span>
                    </div>
                    <Collapse
                      className={styles.callParameterDetail}
                      items={[
                        {
                          key: "extras",
                          label: t(
                            "memory.settings.extraBodyLabel",
                            "高级模型参数（JSON）",
                          ),
                          children: (
                            <Space
                              direction="vertical"
                              style={{ width: "100%" }}
                            >
                              <Typography.Text type="secondary">
                                {t(
                                  "memory.settings.extraBodyHint",
                                  "可填写模型支持的思考深度等参数，例如 reasoning_effort。仅用于首选的 OpenAI 兼容模型，回退时不携带；这些参数优先于上方思考模式。留空恢复默认。",
                                )}
                              </Typography.Text>
                              <Input.TextArea
                                aria-label={t(
                                  "memory.settings.extraBodyLabel",
                                  "高级模型参数（JSON）",
                                )}
                                disabled={
                                  supportedCallOptions &&
                                  !supportedCallOptions.includes(
                                    "extract_extra_body",
                                  )
                                }
                                rows={5}
                                value={extraBody}
                                status={extraBodyError ? "error" : undefined}
                                placeholder={'{ "reasoning_effort": "low" }'}
                                onChange={(event) => {
                                  setExtraBody(event.target.value);
                                  setExtraBodyError(false);
                                }}
                              />
                              {extraBodyError && (
                                <Typography.Text type="danger">
                                  {t(
                                    "memory.settings.extraBodyInvalid",
                                    "模型扩展参数必须是有效的 JSON 对象",
                                  )}
                                </Typography.Text>
                              )}
                            </Space>
                          ),
                        },
                      ]}
                    />
                  </Space>
                </fieldset>
                <MemoryStorage key={agentId} agentId={agentId} />
              </>
            ),
          },
        ]}
      />

      <div className={styles.saveBar}>
        <span>
          {t(
            "memory.settings.reloadHint",
            "保存后 Agent 会自动重载，当前对话不会被删除。",
          )}
        </span>
        <Button type="primary" loading={saving} onClick={handleSave}>
          {t("common.save", "保存设置")}
        </Button>
      </div>
    </div>
  );
}
