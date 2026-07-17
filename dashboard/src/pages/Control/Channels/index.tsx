/**
 * Per-agent channels page — preset-card grid style (finnie-compatible).
 *
 * Shows a fixed grid of all supported channel kinds. Each card represents
 * one ChannelKey. If the active agent has a channel row for that kind the
 * card shows as enabled (brand background + green badge); otherwise it
 * shows as inactive.
 *
 * Clicking a card always opens ChannelDrawer:
 *   - no existing row  → create mode (kind pre-set and locked)
 *   - existing row     → edit mode
 *
 * Toggle switch:
 *   - no existing row  → open drawer (must configure first)
 *   - existing row     → PATCH enabled flag directly
 */
import { useCallback, useMemo, useState } from "react";
import { Form, Button, Empty, message } from "antd";
import { RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";

import PageShell from "../../../layouts/PageShell";
import { CardSkeleton } from "../../../components/Skeleton";
import { useAgent } from "../../../context/AgentContext";
import {
  ChannelCard,
  ChannelDrawer,
  useChannels,
  CHANNEL_KEYS,
  DEFAULT_CHANNEL_DISPLAY_CONFIG,
  CHANNEL_BOOLEAN_CONFIG_KEYS,
  CHANNEL_FIELDS,
  type ChannelKey,
} from "./components";
import type { ChannelRow } from "./useChannels";
import type { ChannelFormValues } from "./components/ChannelDrawer";
import styles from "./index.module.less";

function configFromFormValues(
  values: ChannelFormValues,
): Record<string, unknown> {
  const { __raw_config, show_thinking, show_tool_hints } = values;
  let config: Record<string, unknown> = {
    show_thinking:
      show_thinking ?? DEFAULT_CHANNEL_DISPLAY_CONFIG.show_thinking,
    show_tool_hints:
      show_tool_hints ?? DEFAULT_CHANNEL_DISPLAY_CONFIG.show_tool_hints,
  };
  const fields = CHANNEL_FIELDS[values.kind as ChannelKey];
  const hasSchema = !!fields && fields.length > 0;
  if (hasSchema) {
    for (const [k, v] of Object.entries(values)) {
      if (
        k === "kind" ||
        k === "name" ||
        k === "enabled" ||
        k === "__raw_config" ||
        k === "show_thinking" ||
        k === "show_tool_hints"
      ) {
        continue;
      }
      if (v === undefined || v === null || v === "") continue;
      config[k] = v;
    }
  } else if (__raw_config !== undefined) {
    const trimmed = __raw_config.trim();
    if (trimmed) {
      const parsed = JSON.parse(trimmed) as Record<string, unknown>;
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
        config = parsed;
      }
    }
  }
  return config;
}

interface TestState {
  loadingKey: ChannelKey | null;
  results: Partial<Record<ChannelKey, { ok: boolean; error?: string }>>;
}

export default function ChannelsPage() {
  const { t } = useTranslation();
  const { activeAgentId } = useAgent();
  const {
    channels,
    loading,
    fetchChannels,
    getChannel,
    createChannel,
    updateChannel,
    deleteChannel,
    probeChannelConfig,
  } = useChannels(activeAgentId);

  const [hoverId, setHoverId] = useState<ChannelKey | null>(null);
  const [enableLoadingKey, setEnableLoadingKey] = useState<ChannelKey | null>(
    null,
  );
  const [testState, setTestState] = useState<TestState>({
    loadingKey: null,
    results: {},
  });

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editing, setEditing] = useState<ChannelRow | null>(null);
  const [loadingConfig, setLoadingConfig] = useState(false);
  const [drawerInitialValues, setDrawerInitialValues] = useState<
    ChannelFormValues | undefined
  >(undefined);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [form] = Form.useForm<ChannelFormValues>();

  /**
   * Index: ChannelKey → best ChannelRow for the active agent.
   * "Best" = enabled row if multiple exist for the same kind, else first row.
   */
  const channelByKind = useMemo<Map<ChannelKey, ChannelRow>>(() => {
    const map = new Map<ChannelKey, ChannelRow>();
    for (const row of channels) {
      const key = row.kind as ChannelKey;
      if (!CHANNEL_KEYS.includes(key)) continue;
      const existing = map.get(key);
      if (!existing || (!existing.enabled && row.enabled)) {
        map.set(key, row);
      }
    }
    return map;
  }, [channels]);

  const openCreate = useCallback(
    (kind: ChannelKey) => {
      setEditing(null);
      setLoadingConfig(false);
      const defaults: ChannelFormValues = {
        kind,
        enabled: false,
        ...DEFAULT_CHANNEL_DISPLAY_CONFIG,
      };
      setDrawerInitialValues(defaults);
      form.resetFields();
      form.setFieldsValue(defaults);
      setDrawerOpen(true);
    },
    [form],
  );

  const openEdit = useCallback(
    async (row: ChannelRow) => {
      setEditing(row);
      setLoadingConfig(true);
      const baseValues: ChannelFormValues = {
        kind: row.kind as ChannelKey,
        enabled: row.enabled,
        ...DEFAULT_CHANNEL_DISPLAY_CONFIG,
      };
      setDrawerInitialValues(baseValues);
      form.resetFields();
      form.setFieldsValue(baseValues);
      setDrawerOpen(true);
      const detail = await getChannel(row.id);
      if (detail) {
        const cfg = detail.config ?? {};
        const stringCfg: Record<string, string | undefined> = {};
        for (const [k, v] of Object.entries(cfg)) {
          if (v === undefined || v === null) continue;
          if (
            CHANNEL_BOOLEAN_CONFIG_KEYS.includes(
              k as (typeof CHANNEL_BOOLEAN_CONFIG_KEYS)[number],
            )
          ) {
            continue;
          }
          if (typeof v === "string") stringCfg[k] = v;
          else if (typeof v === "number" || typeof v === "boolean")
            stringCfg[k] = String(v);
          else stringCfg[k] = JSON.stringify(v);
        }
        if (row.kind === "qq" && stringCfg.client_secret && !stringCfg.secret) {
          stringCfg.secret = stringCfg.client_secret;
        }
        const next: ChannelFormValues = {
          kind: row.kind as ChannelKey,
          enabled: row.enabled,
          show_thinking:
            typeof cfg.show_thinking === "boolean"
              ? cfg.show_thinking
              : DEFAULT_CHANNEL_DISPLAY_CONFIG.show_thinking,
          show_tool_hints:
            typeof cfg.show_tool_hints === "boolean"
              ? cfg.show_tool_hints
              : DEFAULT_CHANNEL_DISPLAY_CONFIG.show_tool_hints,
          ...stringCfg,
          __raw_config: JSON.stringify(cfg, null, 2),
        };
        setDrawerInitialValues(next);
        form.setFieldsValue(next);
      }
      setLoadingConfig(false);
    },
    [form, getChannel],
  );

  const handleCardClick = useCallback(
    (key: ChannelKey) => {
      const row = channelByKind.get(key);
      if (row) {
        void openEdit(row);
      } else {
        openCreate(key);
      }
    },
    [channelByKind, openCreate, openEdit],
  );

  const handleDrawerClose = useCallback(() => {
    setDrawerOpen(false);
    setEditing(null);
    setDrawerInitialValues(undefined);
  }, []);

  const handleSubmit = useCallback(
    async (
      kind: ChannelKey,
      _name: string,
      config: Record<string, unknown>,
      enabled: boolean,
    ) => {
      setSaving(true);
      try {
        if (editing) {
          const updated = await updateChannel(editing.id, { config, enabled });
          if (updated) {
            message.success(t("channels.configSaved"));
            setDrawerOpen(false);
            void fetchChannels();
            return true;
          }
          return false;
        }
        const existing = channelByKind.get(kind);
        if (existing) {
          const updated = await updateChannel(existing.id, { config, enabled });
          if (updated) {
            message.success(t("channels.configSaved"));
            setDrawerOpen(false);
            void fetchChannels();
            return true;
          }
          return false;
        }
        const created = await createChannel({ kind, name: kind, config });
        if (created) {
          if (!enabled) {
            await updateChannel(created.id, { enabled: false });
          }
          message.success(t("channels.configSaved"));
          setDrawerOpen(false);
          void fetchChannels();
          return true;
        }
        return false;
      } finally {
        setSaving(false);
      }
    },
    [editing, channelByKind, createChannel, updateChannel, fetchChannels, t],
  );

  const handleToggleEnabled = useCallback(
    async (key: ChannelKey, checked: boolean) => {
      const row = channelByKind.get(key);
      if (!row) {
        // No row yet — open drawer to configure first.
        openCreate(key);
        return;
      }
      setEnableLoadingKey(key);
      try {
        await updateChannel(row.id, { enabled: checked });
        message.success(
          checked
            ? t("channels.channelEnabled")
            : t("channels.channelDisabled"),
        );
      } finally {
        setEnableLoadingKey(null);
      }
    },
    [channelByKind, openCreate, updateChannel, t],
  );

  const handleDeleteFromDrawer = useCallback(async () => {
    if (!editing) return;
    setDeleting(true);
    try {
      await deleteChannel(editing.id);
      setDrawerOpen(false);
      setEditing(null);
    } finally {
      setDeleting(false);
    }
  }, [editing, deleteChannel]);

  const handleTestFromDrawer = useCallback(async () => {
    const values = form.getFieldsValue(true) as ChannelFormValues;
    const kind = (values.kind ?? editing?.kind) as ChannelKey | undefined;
    if (!kind) return;
    let config: Record<string, unknown>;
    try {
      config = configFromFormValues({ ...values, kind });
    } catch {
      message.error(t("channels.probeNeedConfig"));
      return;
    }
    setTestState((prev) => ({ ...prev, loadingKey: kind }));
    const result = await probeChannelConfig(kind, config);
    setTestState((prev) => ({
      loadingKey: null,
      results: { ...prev.results, [kind]: result },
    }));
    if (result.ok) {
      message.success(t("channels.testSuccess"));
    } else {
      message.error(
        t("channels.testFailed", {
          error: result.error ?? t("common.unknownError"),
        }),
      );
    }
  }, [editing, form, probeChannelConfig, t]);

  if (!activeAgentId) {
    return (
      <PageShell
        title={t("pageShell.channels.title")}
        subtitle={t("pageShell.channels.subtitle")}
        agentScoped
      >
        <Empty
          description={t("channels.noAgentSelected")}
          style={{ marginTop: 60 }}
        />
      </PageShell>
    );
  }

  return (
    <PageShell
      title={t("pageShell.channels.title")}
      subtitle={t("pageShell.channels.subtitle")}
      agentScoped
      actions={
        <Button
          icon={<RefreshCw size={14} />}
          onClick={() => void fetchChannels()}
          loading={loading}
        >
          {t("common.refresh")}
        </Button>
      }
    >
      {loading && channels.length === 0 ? (
        <CardSkeleton count={10} />
      ) : (
        <div className={styles.channelsGrid}>
          {CHANNEL_KEYS.map((key) => {
            const row = channelByKind.get(key);
            return (
              <ChannelCard
                key={key}
                channelKey={key}
                enabled={Boolean(row?.enabled)}
                hasChannel={Boolean(row)}
                isHover={hoverId === key}
                enableLoading={enableLoadingKey === key}
                testLoading={testState.loadingKey === key}
                testResult={testState.results[key] ?? null}
                runtime={row?.runtime}
                onClick={() => handleCardClick(key)}
                onMouseEnter={() => setHoverId(key)}
                onMouseLeave={() => setHoverId(null)}
                onToggleEnabled={handleToggleEnabled}
              />
            );
          })}
        </div>
      )}

      <ChannelDrawer
        open={drawerOpen}
        editing={editing}
        loadingConfig={loadingConfig}
        initialValues={drawerInitialValues}
        form={form}
        saving={saving}
        deleting={deleting}
        onDelete={editing ? handleDeleteFromDrawer : undefined}
        onClose={handleDrawerClose}
        onSubmit={handleSubmit}
        onTest={handleTestFromDrawer}
        testing={
          testState.loadingKey !== null &&
          testState.loadingKey ===
            ((form.getFieldValue("kind") as ChannelKey | undefined) ??
              (editing?.kind as ChannelKey | undefined))
        }
        agentId={activeAgentId}
      />
    </PageShell>
  );
}
