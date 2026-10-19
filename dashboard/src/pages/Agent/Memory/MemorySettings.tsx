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
  SlidersHorizontal,
  Sparkles,
} from "lucide-react";
import { useTranslation } from "react-i18next";

import {
  memoryDashboardApi,
  type ExtractConfig,
  type ExtractTriggerMode,
} from "../../../api/modules/memoryDashboard";
import { providerApi } from "../../../api/modules/provider";
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

export default function MemorySettings({ agentId }: Props) {
  const { t } = useTranslation();
  const loadFailedMessage = t("memory.settings.loadFailed", "记忆设置加载失败");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [memoryEnabled, setMemoryEnabled] = useState(true);
  const [mode, setMode] = useState<ExtractTriggerMode>("idle");
  const [idleMinutes, setIdleMinutes] = useState(5);
  const [intervalHours, setIntervalHours] = useState(6);
  const [auxModel, setAuxModel] = useState<string>(MODEL_AUTO_VALUE);
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
    setAuxModel(defaultModelToForm(cfg.aux_model));
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
        aux_model: defaultModelFromForm(auxModel) ?? "",
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
        className={`${styles.settingCard} ${
          !memoryEnabled ? styles.cardDisabled : ""
        }`}
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
        className={`${styles.settingCard} ${
          !memoryEnabled ? styles.cardDisabled : ""
        }`}
      >
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
                "提炼记忆时调用的模型。选择“自动”跟随对话使用的默认模型；也可以指定一个更便宜或更快的模型专门做提炼。",
              )}
            </div>
          </div>
        </div>
        <fieldset className={styles.strategyFields} disabled={!memoryEnabled}>
          <Select
            aria-label={t("memory.settings.extractModelTitle", "记忆提取模型")}
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
