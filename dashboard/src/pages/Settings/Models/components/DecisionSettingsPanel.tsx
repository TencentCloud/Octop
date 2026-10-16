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
import { Activity, Settings2 } from "lucide-react";
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
  if (
    settings.provider === "custom" ||
    settings.provider === "microsoft" ||
    settings.provider === "laya" ||
    settings.provider === "jev"
  ) {
    return settings.provider;
  }
  return "jev";
}

interface ServiceDraft {
  endpoint: string;
  model: string;
  apiKey: string;
  apiKeySet: boolean;
  filledSavedKey: boolean;
  edited: boolean;
}

function blankDraft(): ServiceDraft {
  return {
    endpoint: "",
    model: "",
    apiKey: "",
    apiKeySet: false,
    filledSavedKey: false,
    edited: false,
  };
}

function savedEndpointsFrom(
  settings: DecisionSettings,
): Record<PresetId, string> {
  const endpoints = { jev: "", microsoft: "", laya: "", custom: "" };
  for (const id of PRESETS) {
    const saved = settings.services?.find((item) => item.provider === id);
    endpoints[id] =
      saved?.endpoint ?? (settings.provider === id ? settings.endpoint : "");
  }
  return endpoints;
}

function draftsFrom(
  settings: DecisionSettings,
): Record<PresetId, ServiceDraft> {
  const drafts = {
    jev: blankDraft(),
    microsoft: blankDraft(),
    laya: blankDraft(),
    custom: blankDraft(),
  };
  for (const id of PRESETS) {
    const saved = settings.services?.find((item) => item.provider === id);
    const selected = settings.provider === id;
    const endpoint = saved?.endpoint ?? (selected ? settings.endpoint : "");
    const model = saved?.model ?? (selected ? settings.model : "");
    drafts[id] = {
      endpoint,
      model: id === "laya" && endpoint && !model ? LAYA_AUTO : model,
      apiKey: "",
      apiKeySet:
        saved?.api_key_set ?? (selected ? settings.api_key_set : false),
      filledSavedKey: false,
      edited: false,
    };
  }
  const selected = inferPreset(settings);
  if (!drafts[selected].endpoint && !drafts[selected].model) {
    drafts[selected] = {
      ...drafts[selected],
      endpoint: defaultEndpoint(selected),
      model: defaultModel(selected),
    };
  }
  return drafts;
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
  const [preset, setPreset] = useState<PresetId>("jev");
  const [drafts, setDrafts] = useState<Record<PresetId, ServiceDraft>>(() =>
    draftsFrom({
      enabled: false,
      provider: "jev",
      endpoint: "",
      model: "",
      skills: true,
      tools: true,
      team: true,
      threshold: 0.6,
      tool_min_count: 8,
      api_key_set: false,
      active: false,
    }),
  );
  const [savedProvider, setSavedProvider] = useState<PresetId>("jev");
  const [savedEndpoints, setSavedEndpoints] = useState<
    Record<PresetId, string>
  >({ jev: "", microsoft: "", laya: "", custom: "" });
  const [savedActive, setSavedActive] = useState(false);
  const [layaReady, setLayaReady] = useState(false);
  const [editing, setEditing] = useState<PresetId | null>(null);
  const enabled = Form.useWatch("enabled", form);
  const skills = Form.useWatch("skills", form);
  const tools = Form.useWatch("tools", form);
  const team = Form.useWatch("team", form);

  const applySaved = (saved: DecisionSettings) => {
    const next = inferPreset(saved);
    setPreset(next);
    setSavedProvider(next);
    setSavedEndpoints(savedEndpointsFrom(saved));
    setSavedActive(saved.active);
    setDrafts(draftsFrom(saved));
    form.setFieldsValue({ ...saved, provider: next, api_key: "" });
  };

  useEffect(() => {
    let cancelled = false;
    void decisionApi
      .get()
      .then((settings) => {
        if (cancelled) return;
        applySaved(settings);
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
    // applySaved closes over the form instance, which is stable.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form, message, t]);

  useEffect(() => {
    void decisionApi
      .layaStatus()
      .then((status) => setLayaReady(status.running))
      .catch(() => setLayaReady(false));
  }, []);

  const patchDraft = (id: PresetId, patch: Partial<ServiceDraft>) => {
    setDrafts((current) => ({
      ...current,
      [id]: { ...current[id], ...patch },
    }));
  };

  const selectProvider = (id: PresetId) => {
    setPreset(id);
    form.setFieldValue("provider", id);
    setDrafts((current) => {
      const draft = current[id];
      if (draft.endpoint || draft.model) return current;
      return {
        ...current,
        [id]: {
          ...draft,
          endpoint: defaultEndpoint(id),
          model: defaultModel(id),
        },
      };
    });
  };

  const openEditor = (id: PresetId) => {
    setEditing(id);
    setDrafts((current) => {
      const draft = current[id];
      if (draft.endpoint || draft.model) return current;
      return {
        ...current,
        [id]: {
          ...draft,
          endpoint: defaultEndpoint(id),
          model: defaultModel(id),
        },
      };
    });
  };

  const persist = async (forceId?: PresetId) => {
    const values = form.getFieldsValue(true);
    const selected = connectionFor(
      preset,
      drafts[preset].endpoint,
      drafts[preset].model,
    );
    if (values.enabled && !/^https?:\/\//i.test(selected.endpoint)) {
      message.error(t("models.decisionNeedEndpoint"));
      return false;
    }
    if (
      values.enabled &&
      (preset === "jev" || preset === "microsoft") &&
      !selected.model
    ) {
      message.error(t("models.decisionNeedModel"));
      return false;
    }
    setSaving(true);
    try {
      const saved = await decisionApi.save({
        enabled: Boolean(values.enabled),
        provider: selected.provider,
        endpoint: selected.endpoint,
        model: selected.model,
        skills: Boolean(values.skills),
        tools: Boolean(values.tools),
        team: Boolean(values.team),
        threshold: Number(values.threshold),
        tool_min_count: Number(values.tool_min_count),
        services: PRESETS.map((id) => {
          const keep =
            id === preset ||
            id === forceId ||
            Boolean(savedEndpoints[id]) ||
            drafts[id].edited;
          const connection = keep
            ? connectionFor(id, drafts[id].endpoint, drafts[id].model)
            : { provider: id, endpoint: "", model: "" };
          return {
            provider: id,
            endpoint: connection.endpoint,
            model: connection.model,
            api_key: keep && drafts[id].apiKey ? drafts[id].apiKey : null,
          };
        }),
      });
      applySaved(saved);
      message.success(t("models.decisionSaved"));
      return true;
    } catch (error) {
      message.error(apiErrorMessage(error, t("common.saveFailed"), t));
      return false;
    } finally {
      setSaving(false);
    }
  };

  const saveEditor = async () => {
    if (!editing) return;
    const connection = connectionFor(
      editing,
      drafts[editing].endpoint,
      drafts[editing].model,
    );
    if (!/^https?:\/\//i.test(connection.endpoint)) {
      message.error(t("models.decisionNeedEndpoint"));
      return;
    }
    if ((editing === "jev" || editing === "microsoft") && !connection.model) {
      message.error(t("models.decisionNeedModel"));
      return;
    }
    if (await persist(editing)) setEditing(null);
  };

  const runTest = async (id: PresetId) => {
    const connection = connectionFor(id, drafts[id].endpoint, drafts[id].model);
    if (!connection.endpoint.trim()) {
      message.error(t("models.decisionNeedEndpoint"));
      return;
    }
    setTestingId(id);
    try {
      const result = await decisionApi.test({
        endpoint: connection.endpoint,
        model: connection.model,
        provider: connection.provider,
        api_key: drafts[id].apiKey || undefined,
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
                const configured = Boolean(savedEndpoints[id]);
                const selected = preset === id;
                return (
                  <div
                    key={id}
                    className={`${styles.choice} ${
                      selected ? styles.choiceOn : ""
                    }`}
                    aria-pressed={selected}
                    onClick={() => selectProvider(id)}
                  >
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
                      </span>
                      <span className={styles.badgeRow}>
                        <span className={styles.badgePair}>
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
                        </span>
                        {configured && !selected ? (
                          <span
                            className={`${styles.hostFlag} ${styles.serviceConfigured}`}
                          >
                            {t("models.decisionConfiguredInactive")}
                          </span>
                        ) : null}
                      </span>
                    </span>
                    <span className={styles.choiceBlurb}>{copy.blurb}</span>
                    <span className={styles.actions}>
                      {drafts[id].endpoint ? (
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
                            void runTest(id);
                          }}
                        />
                      ) : null}
                      <Button
                        size="small"
                        type={configured ? "default" : "primary"}
                        icon={<Settings2 size={14} />}
                        onClick={(event) => {
                          event.stopPropagation();
                          openEditor(id);
                        }}
                      >
                        {configured
                          ? t("common.edit")
                          : t("advancedSettings.search.configure")}
                      </Button>
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
          <Button
            type="primary"
            loading={saving}
            onClick={() => void persist()}
          >
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
              loading={editing !== null && testingId === editing}
              onClick={() => {
                if (editing) void runTest(editing);
              }}
            >
              {t("models.decisionTest")}
            </Button>
            <Button
              type="primary"
              loading={saving}
              onClick={() => void saveEditor()}
            >
              {t("common.save")}
            </Button>
          </div>
        }
      >
        {editing ? (
          <DrawerFields
            preset={editing}
            endpoint={drafts[editing].endpoint}
            model={drafts[editing].model}
            apiKey={drafts[editing].apiKey}
            apiKeySet={drafts[editing].apiKeySet && !drafts[editing].apiKey}
            filledSavedKey={drafts[editing].filledSavedKey}
            openRouterKey={openRouterKey}
            layaActive={savedActive && savedProvider === "laya"}
            onLayaStatus={(status) => setLayaReady(status.running)}
            onEndpoint={(value) =>
              patchDraft(editing, { endpoint: value, edited: true })
            }
            onModel={(value) =>
              patchDraft(editing, { model: value, edited: true })
            }
            onApiKey={(value) =>
              patchDraft(editing, { apiKey: value, edited: true })
            }
            onUseSavedKey={() => {
              if (!openRouterKey) return;
              patchDraft(editing, {
                apiKey: openRouterKey,
                filledSavedKey: true,
                edited: true,
              });
            }}
          />
        ) : null}
      </Drawer>
    </>
  );
}
