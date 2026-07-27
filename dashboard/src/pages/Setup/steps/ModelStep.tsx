import { useEffect, useMemo, useRef, useState } from "react";
import {
  Form,
  Input,
  Button,
  Typography,
  Space,
  Checkbox,
  Spin,
  Segmented,
  Select,
  InputNumber,
  Tag,
  Divider,
  message,
  Switch,
  Modal,
} from "antd";
import { Plus, Trash2, Zap } from "lucide-react";
import { useTranslation } from "react-i18next";
import { request } from "../../../api/request";
import {
  wizardApi,
  wizardSession,
  resolveSetupProbeToken,
} from "../wizardClient";
import type { ProviderDraft, WizardProviderModel } from "../wizardClient";
import { getProviderLogo, customProviderLogo } from "../../../assets/providers";
import { ModelMetaTags } from "../../Settings/Models/modelMeta";
import modelStyles from "../../Settings/Models/index.module.less";
import setupStyles from "../setup.module.less";
import { enrichWizardModel } from "../../Settings/Models/wizardModelMeta";
import {
  groupPresets,
  isLocalPreset,
  presetLogoId,
  presetVariantLabel,
  type PresetGroup,
} from "../../Settings/Models/presetUtils";
import type { ProviderPreset as AdminProviderPreset } from "../../Settings/Models/useProviders";

const { Text } = Typography;

interface ProviderPresetModel {
  id: string;
  name: string;
  max_input_tokens?: number | null;
  context_window?: number | null;
  max_tokens?: number | null;
  input?: string[];
  reasoning?: boolean | null;
  description?: string | null;
}

interface ProviderPreset {
  id: string;
  name: string;
  base_url: string;
  protocol: string;
  api_key_prefix: string;
  models: ProviderPresetModel[];
  provider_group?: string;
  provider_group_name?: string;
  provider_variant?: string;
  logo_id?: string;
}

type PresetDisplayItem =
  | { kind: "single"; preset: ProviderPreset }
  | { kind: "group"; group: PresetGroup };

interface PresetFormValues {
  name: string;
  api_key?: string;
  base_url?: string;
  selectedModels: string[];
}

interface CustomFormValues {
  name: string;
  kind: string;
  api_key?: string;
  base_url?: string;
}

interface CustomModelEntry {
  id: string;
  name: string;
  input: string[];
  context_window?: number;
  max_tokens?: number;
  reasoning?: boolean;
}

interface Props {
  onBack: () => void;
  onSkip: () => void;
  onContinue: (draft: ProviderDraft) => void;
}

type SetupMode = "preset" | "custom";

/** Match admin/models Cloud tab order (grouped brands, then singles); show this many by default. */
const WIZARD_FEATURED_COUNT = 6;

function buildWizardPresetDisplay(presets: ProviderPreset[]): {
  featured: PresetDisplayItem[];
  more: PresetDisplayItem[];
} {
  const cloud = presets.filter((p) => !isLocalPreset(p as AdminProviderPreset));
  const local = presets.filter((p) => isLocalPreset(p as AdminProviderPreset));
  const { grouped, ungrouped } = groupPresets(cloud as AdminProviderPreset[]);
  const ordered: PresetDisplayItem[] = [
    ...grouped.map((group): PresetDisplayItem => ({ kind: "group", group })),
    ...ungrouped.map(
      (preset): PresetDisplayItem => ({
        kind: "single",
        preset: preset as ProviderPreset,
      }),
    ),
  ];
  const featured = ordered.slice(0, WIZARD_FEATURED_COUNT);
  const more: PresetDisplayItem[] = [
    ...ordered.slice(WIZARD_FEATURED_COUNT),
    ...local.map((preset): PresetDisplayItem => ({ kind: "single", preset })),
  ];
  return { featured, more };
}

function defaultPresetFromItem(item: PresetDisplayItem): ProviderPreset {
  return item.kind === "group"
    ? (item.group.presets[0] as ProviderPreset)
    : item.preset;
}

const CUSTOM_KINDS = [
  { value: "openai", labelKey: "kindOpenaiCompat" as const },
  { value: "anthropic", labelKey: "anthropic" as const },
  { value: "bedrock", labelKey: "bedrock" as const },
];

const INPUT_TYPE_OPTIONS = [
  { value: "text", label: "inputTypeText" as const },
  { value: "image", label: "inputTypeImage" as const },
  { value: "audio", label: "inputTypeAudio" as const },
];

export default function ModelStep({ onBack, onSkip, onContinue }: Props) {
  const { t } = useTranslation();
  const [presetForm] = Form.useForm<PresetFormValues>();
  const [customForm] = Form.useForm<CustomFormValues>();
  const [modelForm] = Form.useForm();
  const [presets, setPresets] = useState<ProviderPreset[]>([]);
  const [loadingPresets, setLoadingPresets] = useState(true);
  const [mode, setMode] = useState<SetupMode>("preset");
  const [selectedPresetId, setSelectedPresetId] = useState<string>("");
  const [showAllPresets, setShowAllPresets] = useState(false);
  const [customModels, setCustomModels] = useState<CustomModelEntry[]>([]);
  const [addingCustomModel, setAddingCustomModel] = useState(false);
  const [addingPresetModel, setAddingPresetModel] = useState(false);
  const [extraPresetModels, setExtraPresetModels] = useState<
    CustomModelEntry[]
  >([]);
  const [selectedModelIds, setSelectedModelIds] = useState<string[]>([]);
  const [testing, setTesting] = useState(false);
  const [testPassed, setTestPassed] = useState(false);
  const [variantGroup, setVariantGroup] = useState<PresetGroup | null>(null);
  const apiKeySectionRef = useRef<HTMLDivElement>(null);

  const resetTest = () => setTestPassed(false);

  const scrollToApiKey = () => {
    // Wait for Modal close / form re-render before scrolling.
    window.setTimeout(() => {
      apiKeySectionRef.current?.scrollIntoView({
        behavior: "smooth",
        block: "center",
      });
      const input =
        apiKeySectionRef.current?.querySelector<HTMLInputElement>("input");
      input?.focus({ preventScroll: true });
    }, 120);
  };

  useEffect(() => {
    let cancelled = false;
    setLoadingPresets(true);
    request<ProviderPreset[]>("/setup/presets")
      .then((data) => {
        if (!cancelled && Array.isArray(data) && data.length > 0) {
          setPresets(data);
          const { featured } = buildWizardPresetDisplay(data);
          const initial =
            (featured[0] ? defaultPresetFromItem(featured[0]) : null) ??
            data[0];
          setSelectedPresetId(initial.id);
          const modelIds = initial.models.map((m) => m.id);
          setSelectedModelIds(modelIds);
          presetForm.setFieldsValue({
            name: initial.name,
            base_url: initial.base_url,
            selectedModels: modelIds,
          });
        }
      })
      .catch(() => {
        if (!cancelled) setPresets([]);
      })
      .finally(() => {
        if (!cancelled) setLoadingPresets(false);
      });
    return () => {
      cancelled = true;
    };
  }, [presetForm]);

  useEffect(() => {
    if (!loadingPresets && presets.length === 0) {
      setMode("custom");
    }
  }, [loadingPresets, presets.length]);

  useEffect(() => {
    if (mode === "custom") {
      customForm.setFieldsValue({ kind: "openai" });
    }
  }, [mode, customForm]);

  const preset = useMemo(
    () => presets.find((p) => p.id === selectedPresetId) ?? presets[0],
    [presets, selectedPresetId],
  );

  const { featuredDisplayItems, moreDisplayItems } = useMemo(() => {
    const { featured, more } = buildWizardPresetDisplay(presets);
    return { featuredDisplayItems: featured, moreDisplayItems: more };
  }, [presets]);

  const visibleDisplayItems = showAllPresets
    ? [...featuredDisplayItems, ...moreDisplayItems]
    : featuredDisplayItems;

  const morePresetCount = moreDisplayItems.reduce(
    (n, item) => n + (item.kind === "group" ? item.group.presets.length : 1),
    0,
  );

  const isOllama = preset?.id === "ollama";

  const applyPreset = (p: ProviderPreset) => {
    resetTest();
    setSelectedPresetId(p.id);
    setExtraPresetModels([]);
    const modelIds = p.models.map((m) => m.id);
    setSelectedModelIds(modelIds);
    presetForm.setFieldsValue({
      name: p.name,
      base_url: p.base_url,
      selectedModels: modelIds,
      api_key: undefined,
    });
    scrollToApiKey();
  };

  const handleSelectAll = () => {
    if (!preset) return;
    const modelIds = preset.models.map((m) => m.id);
    setSelectedModelIds(modelIds);
    presetForm.setFieldsValue({ selectedModels: modelIds });
    resetTest();
  };

  const handleDeselectAll = () => {
    setSelectedModelIds([]);
    presetForm.setFieldsValue({ selectedModels: [] });
    resetTest();
  };

  const handleSelectedModelsChange = (ids: string[]) => {
    setSelectedModelIds(ids);
    presetForm.setFieldsValue({ selectedModels: ids });
    resetTest();
  };

  const buildWizardModels = (
    entries: Array<{
      id: string;
      name: string;
      input?: string[];
      reasoning?: boolean;
    }>,
  ): WizardProviderModel[] =>
    entries.map((m) => {
      const model: WizardProviderModel = {
        id: m.id,
        name: m.name,
        enabled: true,
        input: m.input?.length ? m.input : ["text"],
        thinking: null,
      };
      if (m.reasoning) model.reasoning = true;
      return model;
    });

  type DraftCollectResult =
    | { ok: true; draft: ProviderDraft }
    | { ok: false; message: string; field?: string };

  const collectPresetDraft = (
    formValues?: Partial<PresetFormValues>,
  ): DraftCollectResult => {
    if (!preset) {
      return { ok: false, message: t("models.noProvidersHint") };
    }

    const values = formValues ?? presetForm.getFieldsValue(true);
    const name = String(values.name ?? "").trim() || preset.name;
    const apiKey = String(values.api_key ?? "").trim();
    const baseUrl = String(values.base_url ?? "").trim() || undefined;

    if (!name) {
      return {
        ok: false,
        message: t("wizard.model.providerNameRequired"),
        field: "name",
      };
    }
    if (!isOllama && !apiKey) {
      return {
        ok: false,
        message: t("models.pleaseEnterApiKey"),
        field: "api_key",
      };
    }
    if (selectedModelIds.length === 0) {
      return { ok: false, message: t("models.addModelFirst") };
    }

    const selectedIds = new Set(selectedModelIds);
    const modelEntries = buildWizardModels(
      preset.models
        .filter((m) => selectedIds.has(m.id))
        .map((m) => {
          const meta = enrichWizardModel(m, t);
          return {
            id: m.id,
            name: m.name,
            input: meta.input,
            ...(meta.reasoning ? { reasoning: true } : {}),
          };
        }),
    );

    for (const extra of extraPresetModels) {
      if (
        selectedIds.has(extra.id) &&
        !modelEntries.some((m) => m.id === extra.id)
      ) {
        modelEntries.push(...buildWizardModels([extra]));
      }
    }

    if (modelEntries.length === 0) {
      return { ok: false, message: t("models.addModelFirst") };
    }

    return {
      ok: true,
      draft: {
        name,
        type: preset.protocol,
        api_key: apiKey || (isOllama ? "ollama" : ""),
        base_url: baseUrl,
        models: modelEntries,
      },
    };
  };

  const collectCustomDraft = (
    formValues?: Partial<CustomFormValues>,
  ): DraftCollectResult => {
    const values = formValues ?? customForm.getFieldsValue(true);
    const name =
      String(values.name ?? "").trim() || (customModels[0]?.id ?? "").trim();
    const kind = String(values.kind ?? "").trim();
    const apiKey = String(values.api_key ?? "").trim();
    const baseUrl = String(values.base_url ?? "").trim() || undefined;

    if (!name) {
      return {
        ok: false,
        message: t("wizard.model.providerNameRequired"),
        field: "name",
      };
    }
    if (!kind) {
      return {
        ok: false,
        message: t("models.pleaseSelectKind"),
        field: "kind",
      };
    }
    if (customModels.length === 0) {
      return { ok: false, message: t("models.addModelFirst") };
    }
    if (!apiKey) {
      return {
        ok: false,
        message: t("models.pleaseEnterApiKey"),
        field: "api_key",
      };
    }

    return {
      ok: true,
      draft: {
        name,
        type: kind,
        api_key: apiKey,
        base_url: baseUrl,
        models: buildWizardModels(customModels),
      },
    };
  };

  const buildPresetDraft = async (): Promise<ProviderDraft | null> => {
    let values: PresetFormValues;
    try {
      values = await presetForm.validateFields();
    } catch {
      return null;
    }
    const result = collectPresetDraft(values);
    if (!result.ok) {
      message.error(result.message);
      if (result.field) presetForm.scrollToField(result.field);
      return null;
    }
    return result.draft;
  };

  const buildCustomDraft = async (): Promise<ProviderDraft | null> => {
    let values: CustomFormValues;
    try {
      values = await customForm.validateFields();
    } catch {
      return null;
    }
    const result = collectCustomDraft(values);
    if (!result.ok) {
      message.error(result.message);
      if (result.field) customForm.scrollToField(result.field);
      return null;
    }
    return result.draft;
  };

  const handleContinuePreset = async () => {
    const draft = await buildPresetDraft();
    if (!draft) return;
    wizardSession.saveDraft({ provider: draft });
    onContinue(draft);
  };

  const handleContinueCustom = async () => {
    const draft = await buildCustomDraft();
    if (!draft) return;
    wizardSession.saveDraft({ provider: draft });
    onContinue(draft);
  };

  const handleTest = async () => {
    const probeToken = await resolveSetupProbeToken();
    if (!probeToken) {
      message.error(t("wizard.sessionExpired"));
      return;
    }

    let validatedValues: PresetFormValues | CustomFormValues;
    try {
      validatedValues =
        mode === "preset"
          ? await presetForm.validateFields()
          : await customForm.validateFields();
    } catch (err) {
      if (err && typeof err === "object" && "errorFields" in err) return;
      return;
    }

    const result =
      mode === "preset"
        ? collectPresetDraft(validatedValues as PresetFormValues)
        : collectCustomDraft(validatedValues as CustomFormValues);
    if (!result.ok) {
      message.warning(result.message);
      if (result.field) {
        if (mode === "preset") {
          presetForm.scrollToField(result.field);
        } else {
          customForm.scrollToField(result.field);
        }
      }
      return;
    }

    const draft = result.draft;
    setTesting(true);
    resetTest();
    try {
      const result = await wizardApi.testProvider(
        {
          name: draft.name,
          type: draft.type,
          api_key: draft.api_key,
          base_url: draft.base_url,
          model_id: draft.models[0].id,
        },
        probeToken,
      );
      if (result.ok) {
        message.success(
          t("models.testSuccess", {
            name: draft.models[0].name,
            time: result.latency_ms ?? 0,
          }),
        );
        setTestPassed(true);
      } else {
        message.error(
          t("wizard.model.testFailed", { error: result.error ?? "unknown" }),
        );
      }
    } catch (err) {
      message.error(
        t("wizard.model.testFailed", {
          error: err instanceof Error ? err.message : String(err),
        }),
      );
    } finally {
      setTesting(false);
    }
  };

  const handleContinue = async () => {
    if (!testPassed) {
      message.warning(t("wizard.model.testFirstHint"));
      return;
    }
    try {
      if (mode === "preset") {
        await handleContinuePreset();
      } else {
        await handleContinueCustom();
      }
    } catch (err) {
      if (err && typeof err === "object" && "errorFields" in err) return;
    }
  };

  const renderFooter = () => (
    <div className={setupStyles.modelStepFooter}>
      <Space>
        <Button onClick={onBack}>{t("wizard.back")}</Button>
        <Button onClick={onSkip}>{t("wizard.model.skip")}</Button>
      </Space>
      <Space>
        <Button
          htmlType="button"
          icon={<Zap size={14} />}
          loading={testing}
          onClick={() => void handleTest()}
        >
          {t("wizard.model.testButton")}
        </Button>
        <Button
          type="primary"
          disabled={!testPassed}
          onClick={() => void handleContinue()}
        >
          {t("wizard.model.continue")}
        </Button>
      </Space>
    </div>
  );

  const handleAddPresetModel = async () => {
    const values = await modelForm.validateFields();
    const id = (values.id as string).trim();
    if (
      extraPresetModels.some((m) => m.id === id) ||
      preset?.models.some((m) => m.id === id)
    ) {
      return;
    }
    const name =
      (values.model_display_name as string | undefined)?.trim() || id;
    const input: string[] = (values.input as string[] | undefined) || ["text"];
    const entry: CustomModelEntry = { id, name, input };
    if (values.context_window != null) {
      entry.context_window = values.context_window as number;
    }
    if (values.max_tokens != null) {
      entry.max_tokens = values.max_tokens as number;
    }
    if (values.reasoning) {
      entry.reasoning = true;
    }
    setExtraPresetModels((prev) => [...prev, entry]);
    resetTest();
    const nextSelected = [...selectedModelIds, id];
    setSelectedModelIds(nextSelected);
    presetForm.setFieldsValue({
      selectedModels: nextSelected,
    });
    modelForm.resetFields();
    setAddingPresetModel(false);
  };

  const handleAddCustomModel = async () => {
    const values = await modelForm.validateFields();
    const id = (values.id as string).trim();
    if (customModels.some((m) => m.id === id)) return;
    const name =
      (values.model_display_name as string | undefined)?.trim() || id;
    const input: string[] = (values.input as string[] | undefined) || ["text"];
    const entry: CustomModelEntry = { id, name, input };
    if (values.context_window != null) {
      entry.context_window = values.context_window as number;
    }
    if (values.max_tokens != null) {
      entry.max_tokens = values.max_tokens as number;
    }
    if (values.reasoning) {
      entry.reasoning = true;
    }
    setCustomModels((prev) => [...prev, entry]);
    const providerName = String(customForm.getFieldValue("name") ?? "").trim();
    if (!providerName) {
      customForm.setFieldsValue({ name: id });
    }
    resetTest();
    modelForm.resetFields();
    setAddingCustomModel(false);
  };

  const renderAddModelForm = (onAdd: () => void, onCancel: () => void) => (
    <div className={modelStyles.modelAddForm}>
      <Form form={modelForm} layout="vertical" style={{ marginBottom: 0 }}>
        <Form.Item
          name="id"
          label={t("models.modelIdLabel")}
          rules={[{ required: true, message: t("models.modelIdLabel") }]}
          style={{ marginBottom: 12 }}
        >
          <Input placeholder={t("models.modelIdPlaceholder")} />
        </Form.Item>
        <Form.Item
          name="model_display_name"
          label={t("models.modelNameLabel")}
          style={{ marginBottom: 12 }}
        >
          <Input placeholder={t("models.modelNamePlaceholder")} />
        </Form.Item>
        <Form.Item
          name="input"
          label={t("models.inputTypes")}
          initialValue={["text"]}
          style={{ marginBottom: 12 }}
        >
          <Select
            mode="multiple"
            allowClear
            placeholder={t("models.inputTypes")}
            options={INPUT_TYPE_OPTIONS.map((opt) => ({
              value: opt.value,
              label: t(`models.${opt.label}`),
            }))}
          />
        </Form.Item>
        <div style={{ display: "flex", gap: 12 }}>
          <Form.Item
            name="context_window"
            label={t("models.contextWindow")}
            style={{ flex: 1, marginBottom: 12 }}
          >
            <InputNumber
              min={0}
              style={{ width: "100%" }}
              placeholder="128000"
            />
          </Form.Item>
          <Form.Item
            name="max_tokens"
            label={t("models.maxTokens")}
            style={{ flex: 1, marginBottom: 12 }}
          >
            <InputNumber
              min={0}
              style={{ width: "100%" }}
              placeholder="16000"
            />
          </Form.Item>
        </div>
        <Form.Item
          name="reasoning"
          label={t("models.reasoning")}
          valuePropName="checked"
          style={{ marginBottom: 12 }}
        >
          <Switch size="small" />
        </Form.Item>
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <Button size="small" onClick={onCancel}>
            {t("common.cancel")}
          </Button>
          <Button type="primary" size="small" onClick={() => void onAdd()}>
            {t("models.addModel")}
          </Button>
        </div>
      </Form>
    </div>
  );

  const renderModelTileBody = (m: {
    id: string;
    name: string;
    input?: string[];
    context_window?: number | null;
    max_input_tokens?: number | null;
    max_tokens?: number | null;
    reasoning?: boolean | null;
    description?: string | null;
  }) => {
    const meta = enrichWizardModel(m, t);
    return (
      <div className={setupStyles.wizardModelTileBody}>
        <span className={setupStyles.wizardModelName}>{m.name}</span>
        {m.name !== m.id && (
          <span className={setupStyles.wizardModelId}>{m.id}</span>
        )}
        <span className={setupStyles.wizardModelDesc}>{meta.description}</span>
        <ModelMetaTags
          includeText
          input={meta.input}
          reasoning={meta.reasoning}
          context_window={meta.context_window}
          max_tokens={meta.max_tokens}
        />
      </div>
    );
  };

  const renderPresetPanel = () => {
    if (!preset) return null;

    const allExtraModels = extraPresetModels;

    return (
      <>
        <Form<PresetFormValues>
          form={presetForm}
          layout="vertical"
          requiredMark={false}
          onValuesChange={resetTest}
          initialValues={{
            name: preset.name,
            base_url: preset.base_url,
            selectedModels: preset.models.map((m) => m.id),
          }}
        >
          <div className={setupStyles.presetSectionTitle}>
            {t("wizard.model.choosePreset")}
          </div>
          <Text
            type="secondary"
            style={{ fontSize: 12, display: "block", marginBottom: 10 }}
          >
            {t("wizard.model.choosePresetHint")}
          </Text>

          <div className={setupStyles.wizardPresetGrid}>
            {visibleDisplayItems.map((item) => {
              if (item.kind === "group") {
                const { group } = item;
                const logoId = presetLogoId(group.presets[0]);
                const logo = getProviderLogo(logoId) ?? customProviderLogo;
                const active = group.presets.some(
                  (p) => p.id === selectedPresetId,
                );
                const modelCount = Math.max(
                  ...group.presets.map((p) => p.models.length),
                );
                return (
                  <div
                    key={`group-${group.groupKey}`}
                    className={`${setupStyles.wizardPresetCard}${
                      active ? ` ${setupStyles.wizardPresetCardActive}` : ""
                    }`}
                    onClick={() => setVariantGroup(group)}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        setVariantGroup(group);
                      }
                    }}
                  >
                    {logo && (
                      <img
                        src={logo}
                        alt={group.groupName}
                        className={setupStyles.wizardPresetLogo}
                      />
                    )}
                    <div className={setupStyles.wizardPresetMeta}>
                      <div className={setupStyles.wizardPresetName}>
                        {group.groupName}
                      </div>
                      <div className={setupStyles.wizardPresetCount}>
                        {t("models.modelsCount", { count: modelCount })}
                        {" · "}
                        {t("wizard.model.siteCount", {
                          count: group.presets.length,
                        })}
                      </div>
                    </div>
                  </div>
                );
              }

              const p = item.preset;
              const logo =
                getProviderLogo(presetLogoId(p as AdminProviderPreset)) ??
                customProviderLogo;
              const active = p.id === selectedPresetId;
              return (
                <div
                  key={p.id}
                  className={`${setupStyles.wizardPresetCard}${
                    active ? ` ${setupStyles.wizardPresetCardActive}` : ""
                  }`}
                  onClick={() => applyPreset(p)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") applyPreset(p);
                  }}
                >
                  {logo && (
                    <img
                      src={logo}
                      alt={p.name}
                      className={setupStyles.wizardPresetLogo}
                    />
                  )}
                  <div className={setupStyles.wizardPresetMeta}>
                    <div className={setupStyles.wizardPresetName}>{p.name}</div>
                    <div className={setupStyles.wizardPresetCount}>
                      {t("models.modelsCount", { count: p.models.length })}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          {morePresetCount > 0 && (
            <Button
              type="link"
              size="small"
              className={setupStyles.showMoreBtn}
              onClick={() => setShowAllPresets((v) => !v)}
            >
              {showAllPresets
                ? t("wizard.model.hideMorePresets")
                : t("wizard.model.showMorePresets", {
                    count: morePresetCount,
                  })}
            </Button>
          )}

          <Modal
            title={
              variantGroup
                ? t("models.selectVariant", { name: variantGroup.groupName })
                : undefined
            }
            open={!!variantGroup}
            footer={null}
            onCancel={() => setVariantGroup(null)}
            destroyOnHidden
          >
            {variantGroup && (
              <div className={modelStyles.variantList}>
                {variantGroup.presets.map((p) => (
                  <div
                    key={p.id}
                    className={modelStyles.variantItem}
                    onClick={() => {
                      applyPreset(p as ProviderPreset);
                      setVariantGroup(null);
                    }}
                  >
                    <span className={modelStyles.variantItemName}>
                      {presetVariantLabel(p)}
                    </span>
                    <span className={modelStyles.variantItemMeta}>
                      {p.base_url}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </Modal>

          <Divider style={{ margin: "12px 0 16px" }} />

          <Form.Item
            name="name"
            label={t("wizard.model.providerName")}
            rules={[
              {
                required: true,
                message: t("wizard.model.providerNameRequired"),
              },
            ]}
          >
            <Input placeholder={preset.name} />
          </Form.Item>

          <Form.Item label={t("models.kindLabel")}>
            <Tag color="blue">{preset.protocol}</Tag>
          </Form.Item>

          <div ref={apiKeySectionRef}>
            <Form.Item
              name="api_key"
              label="API Key"
              rules={
                isOllama
                  ? []
                  : [{ required: true, message: t("models.pleaseEnterApiKey") }]
              }
              extra={isOllama ? t("models.apiKeyExtraOptional") : undefined}
              getValueFromEvent={(e) =>
                typeof e === "string" ? e : String(e?.target?.value ?? "")
              }
            >
              <Input.Password
                placeholder={
                  preset.api_key_prefix
                    ? `${preset.api_key_prefix}...`
                    : t("models.apiKeyExtraOptional")
                }
                autoComplete="new-password"
              />
            </Form.Item>
          </div>

          <Form.Item name="base_url" label="Base URL">
            <Input placeholder={preset.base_url} />
          </Form.Item>

          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: 8,
            }}
          >
            <Text strong style={{ fontSize: 13 }}>
              {t("models.initialModelsLabel")}
            </Text>
            <Space size={4}>
              <Button type="link" size="small" onClick={handleSelectAll}>
                {t("models.selectAllModels")}
              </Button>
              <Button type="link" size="small" onClick={handleDeselectAll}>
                {t("models.deselectAllModels")}
              </Button>
            </Space>
          </div>

          <Text
            type="secondary"
            style={{ fontSize: 12, display: "block", marginBottom: 8 }}
          >
            {t("models.initialModelsHint")}
          </Text>

          <div style={{ marginBottom: 12 }}>
            <Checkbox.Group
              className={setupStyles.wizardModelGrid}
              value={selectedModelIds}
              onChange={handleSelectedModelsChange}
            >
              {preset.models.map((m) => (
                <Checkbox
                  key={m.id}
                  value={m.id}
                  className={setupStyles.wizardModelTile}
                >
                  {renderModelTileBody(m)}
                </Checkbox>
              ))}
              {allExtraModels.map((m) => (
                <div key={m.id} className={setupStyles.wizardModelTileWrap}>
                  <Checkbox
                    value={m.id}
                    className={setupStyles.wizardModelTile}
                  >
                    {renderModelTileBody(m)}
                  </Checkbox>
                  <Button
                    type="text"
                    size="small"
                    danger
                    className={setupStyles.wizardModelDeleteFab}
                    icon={<Trash2 size={14} />}
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      resetTest();
                      setExtraPresetModels((prev) =>
                        prev.filter((x) => x.id !== m.id),
                      );
                      const nextSelected = selectedModelIds.filter(
                        (mid) => mid !== m.id,
                      );
                      setSelectedModelIds(nextSelected);
                      presetForm.setFieldsValue({
                        selectedModels: nextSelected,
                      });
                    }}
                  />
                </div>
              ))}
              {preset.models.length === 0 && allExtraModels.length === 0 && (
                <div className={setupStyles.wizardModelEmpty}>
                  {t("models.noModels")}
                </div>
              )}
            </Checkbox.Group>
          </div>

          <Button
            type="dashed"
            block
            icon={<Plus size={14} />}
            onClick={() => setAddingPresetModel(true)}
            style={{ display: addingPresetModel ? "none" : undefined }}
          >
            {t("models.addModel")}
          </Button>
        </Form>
        {addingPresetModel &&
          renderAddModelForm(
            () => void handleAddPresetModel(),
            () => {
              setAddingPresetModel(false);
              modelForm.resetFields();
            },
          )}
      </>
    );
  };

  const renderCustomPanel = () => (
    <>
      <Form<CustomFormValues>
        form={customForm}
        layout="vertical"
        requiredMark={false}
        onValuesChange={resetTest}
        initialValues={{ kind: "openai" }}
      >
        <Form.Item
          name="name"
          label={t("wizard.model.providerName")}
          rules={[
            {
              required: true,
              message: t("wizard.model.providerNameRequired"),
            },
          ]}
        >
          <Input placeholder={t("models.namePlaceholder")} />
        </Form.Item>

        <Form.Item
          name="kind"
          label={t("models.kindLabel")}
          rules={[{ required: true, message: t("models.pleaseSelectKind") }]}
        >
          <Select
            options={CUSTOM_KINDS.map((k) => ({
              value: k.value,
              label:
                k.value === "openai"
                  ? t("models.kindOpenaiCompat")
                  : k.value === "anthropic"
                  ? "Anthropic"
                  : "AWS Bedrock",
            }))}
          />
        </Form.Item>

        <Form.Item
          name="base_url"
          label="Base URL"
          extra={t("models.baseUrlExtra")}
        >
          <Input placeholder="https://api.openai.com/v1" />
        </Form.Item>

        <Form.Item
          name="api_key"
          label="API Key"
          rules={[{ required: true, message: t("models.pleaseEnterApiKey") }]}
          getValueFromEvent={(e) =>
            typeof e === "string" ? e : String(e?.target?.value ?? "")
          }
        >
          <Input.Password placeholder="sk-..." autoComplete="new-password" />
        </Form.Item>

        <Divider style={{ margin: "8px 0 12px" }}>
          {t("models.initialModelsLabel")}
        </Divider>
        <Text
          type="secondary"
          style={{ fontSize: 12, display: "block", marginBottom: 8 }}
        >
          {t("models.initialModelsHint")}
        </Text>

        <div className={setupStyles.wizardModelGridStatic}>
          {customModels.length === 0 ? (
            <div className={setupStyles.wizardModelEmpty}>
              {t("models.noModels")}
            </div>
          ) : (
            customModels.map((m) => (
              <div key={m.id} className={setupStyles.wizardModelTileWrap}>
                <div className={setupStyles.wizardModelTileStatic}>
                  {renderModelTileBody(m)}
                </div>
                <Button
                  type="text"
                  size="small"
                  danger
                  className={setupStyles.wizardModelDeleteFab}
                  icon={<Trash2 size={14} />}
                  onClick={() => {
                    resetTest();
                    setCustomModels((prev) =>
                      prev.filter((x) => x.id !== m.id),
                    );
                  }}
                />
              </div>
            ))
          )}
        </div>

        <Button
          type="dashed"
          block
          icon={<Plus size={14} />}
          onClick={() => setAddingCustomModel(true)}
          style={{
            marginTop: 12,
            display: addingCustomModel ? "none" : undefined,
          }}
        >
          {t("models.addModel")}
        </Button>
      </Form>
      {addingCustomModel &&
        renderAddModelForm(
          () => void handleAddCustomModel(),
          () => {
            setAddingCustomModel(false);
            modelForm.resetFields();
          },
        )}
    </>
  );

  if (loadingPresets) {
    return (
      <div style={{ textAlign: "center", padding: 32 }}>
        <Spin />
      </div>
    );
  }

  if (!preset && mode === "preset" && !loadingPresets) {
    return (
      <div className={setupStyles.modelStep}>
        <div className={setupStyles.modelStepHeader}>
          <div
            style={{
              fontSize: 16,
              fontWeight: 600,
              color: "var(--fn-text-primary)",
              marginBottom: 4,
            }}
          >
            {t("wizard.stepModel")}
          </div>
          <Text type="secondary" style={{ fontSize: 13 }}>
            {t("models.noProvidersHint")}
          </Text>
        </div>
        <div className={setupStyles.modelStepMode}>
          <Segmented<SetupMode>
            block
            value="custom"
            onChange={(v) => setMode(v)}
            options={[
              {
                label: t("wizard.model.presetTab"),
                value: "preset",
                disabled: true,
              },
              { label: t("wizard.model.customTab"), value: "custom" },
            ]}
          />
        </div>
        <div className={setupStyles.modelStepScroll}>{renderCustomPanel()}</div>
        {renderFooter()}
      </div>
    );
  }

  return (
    <div className={setupStyles.modelStep}>
      <div className={setupStyles.modelStepHeader}>
        <div
          style={{
            fontSize: 16,
            fontWeight: 600,
            color: "var(--fn-text-primary)",
            marginBottom: 4,
          }}
        >
          {t("wizard.stepModel")}
        </div>
        <Text type="secondary" style={{ fontSize: 13 }}>
          {t("wizard.model.intro")}
        </Text>
      </div>

      <div className={setupStyles.modelStepMode}>
        <Segmented<SetupMode>
          block
          value={mode}
          onChange={(v) => {
            setMode(v);
            resetTest();
            setAddingCustomModel(false);
            setAddingPresetModel(false);
            modelForm.resetFields();
          }}
          options={[
            { label: t("wizard.model.presetTab"), value: "preset" },
            { label: t("wizard.model.customTab"), value: "custom" },
          ]}
        />
      </div>

      <div className={setupStyles.modelStepScroll}>
        <div hidden={mode !== "preset"}>{renderPresetPanel()}</div>
        <div hidden={mode !== "custom"}>{renderCustomPanel()}</div>
      </div>

      {renderFooter()}
    </div>
  );
}
