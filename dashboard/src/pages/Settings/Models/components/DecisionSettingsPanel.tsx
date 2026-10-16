import { useEffect, useState } from "react";
import {
  App,
  AutoComplete,
  Button,
  Checkbox,
  Collapse,
  Drawer,
  Form,
  Input,
  InputNumber,
  Radio,
  Slider,
  Switch,
  Typography,
} from "antd";
import { Activity, Pencil } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  decisionApi,
  type DecisionProvider,
  type DecisionSettings,
  type LayaStatus,
} from "../../../../api/modules/decision";
import customProviderLogo from "../../../../assets/providers/custom-provider.svg";
import jevLogo from "../../../../assets/providers/jev.png";
import layaLogo from "../../../../assets/providers/laya.png";
import microsoftLogo from "../../../../assets/providers/microsoft.png";
import { apiErrorMessage } from "../../../../utils/apiError";
import styles from "./DecisionSettingsPanel.module.less";
import { LayaLocalInstall } from "./LayaLocalInstall";

const { Paragraph, Text } = Typography;

const OPENROUTER_DECISIONS = "https://openrouter.ai/api/alpha/decisions";
const JEV_MODEL = "typesafe/jev-1.13";
const MICROSOFT_MODEL = "microsoft/microsoft-decision-1";
const LAYA_ENDPOINT = "http://127.0.0.1:8000/v1/systemone";
const LAYA_AUTO = "auto";

type PresetId = "jev" | "microsoft" | "laya" | "custom";

const PRESETS: PresetId[] = ["jev", "microsoft", "laya", "custom"];

const JEV_MODELS = [JEV_MODEL, "~typesafe/jev-latest"];
const MICROSOFT_MODELS = [MICROSOFT_MODEL];

function inferPreset(settings: DecisionSettings): PresetId {
  if (!settings.endpoint) return "jev";
  if (settings.provider === "custom") return "custom";
  if (settings.provider === "microsoft") return "microsoft";
  if (settings.provider === "laya") return "laya";
  return "jev";
}

function defaultEndpoint(preset: PresetId): string {
  if (preset === "laya") return LAYA_ENDPOINT;
  if (preset === "custom") return "";
  return OPENROUTER_DECISIONS;
}

function defaultModel(preset: PresetId): string {
  if (preset === "jev") return JEV_MODEL;
  if (preset === "microsoft") return MICROSOFT_MODEL;
  if (preset === "laya") return LAYA_AUTO;
  return "";
}

function wireModel(preset: PresetId, model: string): string {
  const trimmed = model.trim();
  if (preset === "laya" && (trimmed === "" || trimmed === LAYA_AUTO)) return "";
  return trimmed;
}

function connectionFor(
  preset: PresetId,
  endpoint: string,
  model: string,
): { provider: DecisionProvider; endpoint: string; model: string } {
  const provider: DecisionProvider =
    preset === "microsoft"
      ? "microsoft"
      : preset === "laya"
      ? "laya"
      : preset === "custom"
      ? "custom"
      : "jev";
  return {
    provider,
    endpoint: endpoint.trim(),
    model: wireModel(preset, model),
  };
}

function DrawerFields({
  preset,
  endpoint,
  model,
  apiKey,
  apiKeySet,
  filledSavedKey,
  openRouterKey,
  onEndpoint,
  onModel,
  onApiKey,
  onUseSavedKey,
  layaActive,
  onLayaStatus,
}: {
  preset: PresetId;
  endpoint: string;
  model: string;
  apiKey: string;
  apiKeySet: boolean;
  filledSavedKey: boolean;
  openRouterKey?: string | null;
  onEndpoint: (value: string) => void;
  onModel: (value: string) => void;
  onApiKey: (value: string) => void;
  onUseSavedKey: () => void;
  layaActive: boolean;
  onLayaStatus: (status: LayaStatus) => void;
}) {
  const { t } = useTranslation();
  const cloud = preset === "jev" || preset === "microsoft";
  const modelRequired = cloud;
  const keyRequired =
    endpoint.includes("openrouter.ai") && !apiKeySet && !filledSavedKey;
  const label = (text: string, required: boolean) => (
    <span>
      {text}
      {required ? (
        <>
          {" "}
          <span className={styles.requiredMark}>*</span>
        </>
      ) : null}
    </span>
  );
  const layaModels = [
    { value: LAYA_AUTO, label: t("models.decisionLayaModelAuto") },
    { value: "multilingual", label: t("models.decisionLayaModelMulti") },
    { value: "english", label: t("models.decisionLayaModelEn") },
    { value: "typed-decisions", label: t("models.decisionLayaModelTyped") },
  ];
  const modelOptions =
    preset === "laya"
      ? layaModels
      : (preset === "microsoft" ? MICROSOFT_MODELS : JEV_MODELS).map(
          (value) => ({ value, label: value }),
        );
  const showSavedKey =
    cloud && Boolean(openRouterKey) && endpoint.includes("openrouter.ai");
  return (
    <div className={styles.drawerBody}>
      <div className={styles.drawerHint}>
        {t(
          preset === "jev"
            ? "models.decisionJevDetail"
            : preset === "microsoft"
            ? "models.decisionMsDetail"
            : preset === "laya"
            ? "models.decisionLayaDetail"
            : "models.decisionCustomDetail",
        )}
      </div>
      {preset === "laya" ? (
        <LayaLocalInstall
          active={layaActive}
          onStatusChange={onLayaStatus}
          onReady={() => {
            onEndpoint(LAYA_ENDPOINT);
            onModel(LAYA_AUTO);
          }}
        />
      ) : null}
      <div className={styles.configSectionTitle}>
        {t("models.decisionConnection")}
      </div>
      <Form
        className={styles.drawerForm}
        layout="vertical"
        requiredMark={false}
      >
        <Form.Item label={label(t("models.decisionEndpoint"), true)}>
          <Input
            value={endpoint}
            placeholder={defaultEndpoint(preset) || OPENROUTER_DECISIONS}
            spellCheck={false}
            onChange={(event) => onEndpoint(event.target.value)}
          />
        </Form.Item>
        <Form.Item
          label={label(t("models.decisionModel"), modelRequired)}
          extra={
            preset === "laya"
              ? undefined
              : preset === "custom"
              ? t("models.decisionCustomModelHint")
              : t("models.decisionModelPick")
          }
        >
          {preset === "laya" ? (
            <>
              <Radio.Group
                className={styles.modelChoices}
                value={model || LAYA_AUTO}
                onChange={(event) => onModel(event.target.value)}
              >
                {layaModels.map((item) => (
                  <Radio key={item.value} value={item.value}>
                    {item.label}
                  </Radio>
                ))}
              </Radio.Group>
              <p className={styles.modelHint}>
                {t("models.decisionModelOptional")}
              </p>
            </>
          ) : (
            <AutoComplete
              value={model}
              options={preset === "custom" ? [] : modelOptions}
              filterOption={(input, option) => {
                const haystack = `${option?.value ?? ""} ${
                  option?.label ?? ""
                }`;
                return haystack
                  .toLowerCase()
                  .includes(input.trim().toLowerCase());
              }}
              onChange={onModel}
            >
              <Input
                spellCheck={false}
                placeholder={defaultModel(preset) || JEV_MODEL}
              />
            </AutoComplete>
          )}
        </Form.Item>
        <Form.Item
          label={label(t("models.decisionApiKey"), keyRequired)}
          extra={
            filledSavedKey
              ? t("models.decisionSavedKeyReady")
              : apiKeySet
              ? t("models.decisionApiKeyKeep")
              : preset === "laya"
              ? t("models.decisionLayaKeyHint")
              : t("models.decisionApiKeyHint")
          }
        >
          <Input.Password
            value={apiKey}
            autoComplete="new-password"
            onChange={(event) => onApiKey(event.target.value)}
          />
        </Form.Item>
        {showSavedKey || endpoint.includes("openrouter.ai") ? (
          <div className={styles.guideLinks}>
            {showSavedKey ? (
              <Button type="link" size="small" onClick={onUseSavedKey}>
                {t("models.decisionUseSavedKey")}
              </Button>
            ) : null}
            {endpoint.includes("openrouter.ai") ? (
              <a
                href="https://openrouter.ai/keys"
                target="_blank"
                rel="noreferrer"
              >
                {t("models.decisionCreateKey")}
              </a>
            ) : null}
          </div>
        ) : null}
      </Form>
    </div>
  );
}

export function DecisionSettingsPanel({
  openRouterKey,
}: {
  openRouterKey?: string | null;
}) {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testingId, setTestingId] = useState<string | null>(null);
  const [apiKeySet, setApiKeySet] = useState(false);
  const [preset, setPreset] = useState<PresetId>("jev");
  const [hasSavedService, setHasSavedService] = useState(false);
  const [savedActive, setSavedActive] = useState(false);
  const [layaReady, setLayaReady] = useState(false);
  const [editing, setEditing] = useState<PresetId | null>(null);
  const [draftEndpoint, setDraftEndpoint] = useState("");
  const [draftModel, setDraftModel] = useState("");
  const [draftKey, setDraftKey] = useState("");
  const [filledSavedKey, setFilledSavedKey] = useState(false);
  const enabled = Form.useWatch("enabled", form);
  const skills = Form.useWatch("skills", form);
  const tools = Form.useWatch("tools", form);
  const team = Form.useWatch("team", form);
  const activeModel = String(Form.useWatch("model", form) || "");

  useEffect(() => {
    let cancelled = false;
    void decisionApi
      .get()
      .then((settings) => {
        if (cancelled) return;
        const next = inferPreset(settings);
        const connection = connectionFor(
          next,
          settings.endpoint,
          settings.model,
        );
        setPreset(next);
        setHasSavedService(Boolean(settings.endpoint));
        setSavedActive(settings.active);
        form.setFieldsValue({ ...settings, ...connection, api_key: "" });
        setApiKeySet(settings.api_key_set);
      })
      .catch((error: unknown) => {
        if (!cancelled)
          message.error(
            apiErrorMessage(error, t("models.decisionLoadFailed"), t),
          );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [form, message, t]);

  const applySaved = (saved: DecisionSettings) => {
    const next = inferPreset(saved);
    setPreset(next);
    setHasSavedService(Boolean(saved.endpoint));
    setSavedActive(saved.active);
    form.setFieldsValue({
      ...saved,
      ...connectionFor(next, saved.endpoint, saved.model),
      api_key: "",
    });
    setApiKeySet(saved.api_key_set);
    setFilledSavedKey(false);
  };

  useEffect(() => {
    void decisionApi
      .layaStatus()
      .then((status) => setLayaReady(status.running))
      .catch(() => setLayaReady(false));
  }, []);

  const persist = async (
    connection: { provider: DecisionProvider; endpoint: string; model: string },
    apiKey: string,
  ) => {
    const values = form.getFieldsValue(true);
    if (values.enabled && !/^https?:\/\//i.test(connection.endpoint.trim())) {
      message.error(t("models.decisionNeedEndpoint"));
      return;
    }
    setSaving(true);
    try {
      const savedConnection = connectionFor(
        preset,
        String(values.endpoint || ""),
        String(values.model || ""),
      );
      const sameService =
        hasSavedService && connection.endpoint === savedConnection.endpoint;
      const saved = await decisionApi.save({
        enabled: Boolean(values.enabled),
        provider: connection.provider,
        endpoint: connection.endpoint,
        model: connection.model,
        skills: Boolean(values.skills),
        tools: Boolean(values.tools),
        team: Boolean(values.team),
        threshold: Number(values.threshold),
        tool_min_count: Number(values.tool_min_count),
        api_key: apiKey ? apiKey : sameService ? null : "",
      });
      applySaved(saved);
      setEditing(null);
      message.success(t("models.decisionSaved"));
    } catch (error) {
      message.error(apiErrorMessage(error, t("common.saveFailed"), t));
    } finally {
      setSaving(false);
    }
  };

  const onSave = async () => {
    const values = form.getFieldsValue(true);
    await persist(
      connectionFor(
        preset,
        String(values.endpoint || ""),
        String(values.model || ""),
      ),
      String(values.api_key || ""),
    );
  };

  const runTest = async (
    spin: string,
    connection: { provider: DecisionProvider; endpoint: string; model: string },
    apiKey?: string,
  ) => {
    if (!connection.endpoint.trim()) {
      message.error(t("models.decisionNeedEndpoint"));
      return;
    }
    setTestingId(spin);
    try {
      const values = form.getFieldsValue(true);
      const savedConnection = connectionFor(
        preset,
        String(values.endpoint || ""),
        String(values.model || ""),
      );
      const sameService =
        hasSavedService && connection.endpoint === savedConnection.endpoint;
      const result = await decisionApi.test({
        endpoint: connection.endpoint,
        model: connection.model,
        provider: connection.provider,
        api_key: apiKey || (sameService ? undefined : ""),
      });
      if (result.ok) {
        message.success(
          t("models.decisionTestOk", {
            probability: Number(result.probability).toFixed(2),
          }),
        );
      } else {
        message.error(result.error || t("models.decisionTestFailed"));
      }
    } catch (error) {
      message.error(apiErrorMessage(error, t("models.decisionTestFailed"), t));
    } finally {
      setTestingId(null);
    }
  };

  const openEditor = (id: PresetId) => {
    setEditing(id);
    setFilledSavedKey(false);
    setDraftKey("");
    if (id === preset && hasSavedService) {
      setDraftEndpoint(String(form.getFieldValue("endpoint") || ""));
      const savedModel = String(form.getFieldValue("model") || "");
      setDraftModel(id === "laya" && !savedModel ? LAYA_AUTO : savedModel);
      return;
    }
    setDraftEndpoint(defaultEndpoint(id));
    setDraftModel(defaultModel(id));
  };

  const testPreset = (id: PresetId) => {
    const values = form.getFieldsValue(true);
    const connection =
      id === preset
        ? connectionFor(
            id,
            String(values.endpoint || ""),
            String(values.model || ""),
          )
        : connectionFor(id, defaultEndpoint(id), defaultModel(id));
    void runTest(id, connection);
  };

  const presetLogos: Record<PresetId, { src: string; mark: boolean }> = {
    jev: { src: jevLogo, mark: true },
    microsoft: { src: microsoftLogo, mark: false },
    laya: { src: layaLogo, mark: false },
    custom: { src: customProviderLogo, mark: false },
  };

  const choiceCopy: Record<
    PresetId,
    { name: string; host: string; blurb: string; hostTone: string }
  > = {
    jev: {
      name: t("models.decisionJevName"),
      host: t("models.decisionJevHost"),
      blurb: t("models.decisionJevBlurb"),
      hostTone: styles.hostCloud,
    },
    microsoft: {
      name: t("models.decisionMsName"),
      host: t("models.decisionMsHost"),
      blurb: t("models.decisionMsBlurb"),
      hostTone: styles.hostCloud,
    },
    laya: {
      name: t("models.decisionLayaName"),
      host: t("models.decisionLayaHost"),
      blurb: t("models.decisionLayaBlurb"),
      hostTone: styles.hostLocal,
    },
    custom: {
      name: t("models.decisionCustomName"),
      host: t("models.decisionCustomHost"),
      blurb: t("models.decisionCustomBlurb"),
      hostTone: styles.hostOwn,
    },
  };

  const taskChecked = { skills, tools, team } as const;

  return (
    <>
      <Form
        className={styles.panel}
        form={form}
        layout="vertical"
        disabled={loading}
        initialValues={{
          enabled: false,
          provider: "jev",
          endpoint: OPENROUTER_DECISIONS,
          model: JEV_MODEL,
          skills: true,
          tools: true,
          team: true,
          threshold: 0.6,
          tool_min_count: 8,
        }}
      >
        <p className={styles.intro}>{t("models.decisionIntro")}</p>
        <div className={styles.enableRow}>
          <Form.Item name="enabled" valuePropName="checked" noStyle>
            <Switch />
          </Form.Item>
          <span className={styles.enableLabel}>
            {t("models.decisionEnabled")}
          </span>
        </div>
        {enabled ? (
          <>
            <div className={styles.sectionLabel}>
              {t("models.decisionPick")}
            </div>
            <div className={styles.choices}>
              {PRESETS.map((id) => {
                const copy = choiceCopy[id];
                const configured = hasSavedService && preset === id;
                const inUse = configured && savedActive;
                const canTest = configured;
                return (
                  <div
                    key={id}
                    className={`${styles.choice} ${
                      inUse ? styles.choiceOn : ""
                    }`}
                    onClick={() => openEditor(id)}
                  >
                    {inUse ? (
                      <span className={styles.flag}>
                        {t("models.decisionInUse")}
                      </span>
                    ) : null}
                    <span className={styles.choiceTop}>
                      <span className={styles.logoTile}>
                        <img
                          className={`${styles.logo} ${
                            presetLogos[id].mark ? styles.logoMark : ""
                          }`}
                          src={presetLogos[id].src}
                          alt=""
                        />
                      </span>
                      <span className={styles.titleBlock}>
                        <span className={styles.choiceName}>{copy.name}</span>
                        <span className={styles.badgeRow}>
                          <span
                            className={`${styles.hostFlag} ${copy.hostTone}`}
                          >
                            {copy.host}
                          </span>
                          {id === "laya" && layaReady ? (
                            <span
                              className={`${styles.hostFlag} ${styles.serviceReady}`}
                            >
                              {t("models.decisionServiceReady")}
                            </span>
                          ) : null}
                          {configured && !inUse ? (
                            <span
                              className={`${styles.hostFlag} ${styles.serviceConfigured}`}
                            >
                              {t("models.decisionConfiguredInactive")}
                            </span>
                          ) : null}
                        </span>
                      </span>
                    </span>
                    <span className={styles.choiceBlurb}>{copy.blurb}</span>
                    {inUse && (activeModel || id === "laya") ? (
                      <span className={styles.choiceModel}>
                        {activeModel || t("models.decisionLayaModelAuto")}
                      </span>
                    ) : null}
                    <span className={styles.actions}>
                      {canTest ? (
                        <Button
                          type="text"
                          size="small"
                          className={styles.iconBtn}
                          aria-label={t("models.decisionTest")}
                          title={t("models.decisionTest")}
                          icon={<Activity size={15} />}
                          loading={testingId === id}
                          onClick={(event) => {
                            event.stopPropagation();
                            testPreset(id);
                          }}
                        />
                      ) : null}
                      <Button
                        type="text"
                        size="small"
                        className={styles.iconBtn}
                        aria-label={t("common.edit")}
                        title={t("common.edit")}
                        icon={<Pencil size={15} />}
                        onClick={(event) => {
                          event.stopPropagation();
                          openEditor(id);
                        }}
                      />
                    </span>
                  </div>
                );
              })}
            </div>

            <div className={styles.sectionLabel}>
              {t("models.decisionScope")}
            </div>
            <div className={styles.tasks}>
              {(
                [
                  [
                    "skills",
                    "models.decisionSkills",
                    "models.decisionSkillsDesc",
                  ],
                  ["tools", "models.decisionTools", "models.decisionToolsDesc"],
                  ["team", "models.decisionTeam", "models.decisionTeamDesc"],
                ] as const
              ).map(([name, titleKey, descKey]) => {
                const checked = Boolean(taskChecked[name]);
                return (
                  <div
                    key={name}
                    className={`${styles.task} ${checked ? styles.taskOn : ""}`}
                    role="checkbox"
                    aria-checked={checked}
                    onClick={() => form.setFieldValue(name, !checked)}
                  >
                    <span className={styles.taskHead}>
                      <Checkbox
                        checked={checked}
                        onClick={(event) => event.stopPropagation()}
                        onChange={(event) =>
                          form.setFieldValue(name, event.target.checked)
                        }
                      />
                      <span className={styles.taskTitle}>{t(titleKey)}</span>
                    </span>
                    <span className={styles.taskDesc}>{t(descKey)}</span>
                  </div>
                );
              })}
            </div>
            <Form.Item name="skills" valuePropName="checked" hidden>
              <Switch />
            </Form.Item>
            <Form.Item name="tools" valuePropName="checked" hidden>
              <Switch />
            </Form.Item>
            <Form.Item name="team" valuePropName="checked" hidden>
              <Switch />
            </Form.Item>

            <Collapse
              className={styles.more}
              ghost
              items={[
                {
                  key: "more",
                  label: t("models.decisionMore"),
                  children: (
                    <>
                      <Form.Item
                        name="threshold"
                        label={t("models.decisionThreshold")}
                        extra={t("models.decisionThresholdHint")}
                      >
                        <Slider
                          min={0.05}
                          max={0.95}
                          step={0.05}
                          marks={{
                            0.4: t("models.decisionLoose"),
                            0.6: t("models.decisionBalanced"),
                            0.8: t("models.decisionStrict"),
                          }}
                        />
                      </Form.Item>
                      <Form.Item
                        name="tool_min_count"
                        label={t("models.decisionToolMin")}
                        extra={t("models.decisionToolMinHint")}
                      >
                        <InputNumber min={1} max={100} step={1} />
                      </Form.Item>
                    </>
                  ),
                },
              ]}
            />
          </>
        ) : null}

        <div className={styles.footer}>
          <Button type="primary" loading={saving} onClick={() => void onSave()}>
            {t("common.save")}
          </Button>
        </div>
        <Paragraph className={styles.fallback}>
          <Text type="secondary">
            {enabled
              ? t("models.decisionFallback")
              : t("models.decisionOffHint")}
          </Text>
        </Paragraph>
      </Form>
      <Drawer
        title={editing ? choiceCopy[editing].name : ""}
        open={editing !== null}
        onClose={() => setEditing(null)}
        width={440}
        placement="right"
        destroyOnHidden
        footer={
          <div className={styles.drawerFooter}>
            <Button onClick={() => setEditing(null)}>
              {t("common.cancel")}
            </Button>
            <Button
              icon={<Activity size={14} />}
              loading={testingId === "drawer"}
              onClick={() => {
                if (!editing) return;
                void runTest(
                  "drawer",
                  connectionFor(editing, draftEndpoint, draftModel),
                  draftKey,
                );
              }}
            >
              {t("models.decisionTest")}
            </Button>
            <Button
              type="primary"
              loading={saving}
              onClick={() => {
                if (!editing) return;
                void persist(
                  connectionFor(editing, draftEndpoint, draftModel),
                  draftKey,
                );
              }}
            >
              {t("models.decisionSaveUse")}
            </Button>
          </div>
        }
      >
        {editing ? (
          <DrawerFields
            preset={editing}
            endpoint={draftEndpoint}
            model={draftModel}
            apiKey={draftKey}
            apiKeySet={
              apiKeySet &&
              draftEndpoint.trim() ===
                String(form.getFieldValue("endpoint") || "").trim()
            }
            filledSavedKey={filledSavedKey}
            openRouterKey={openRouterKey}
            layaActive={savedActive && preset === "laya"}
            onLayaStatus={(status) => setLayaReady(status.running)}
            onEndpoint={setDraftEndpoint}
            onModel={setDraftModel}
            onApiKey={setDraftKey}
            onUseSavedKey={() => {
              if (!openRouterKey) return;
              setDraftKey(openRouterKey);
              setFilledSavedKey(true);
            }}
          />
        ) : null}
      </Drawer>
    </>
  );
}
