import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { App, Button, Empty, Form, Switch } from "antd";

import { useTranslation } from "react-i18next";
import PageShell from "../../../layouts/PageShell";
import { CardSkeleton } from "../../../components/Skeleton";
import { acpApi } from "../../../api/modules/acp";
import {
  ACP_DEFAULT_STDIO_BUFFER_LIMIT_BYTES,
  type ACPRunnerConfig,
} from "../../../api/types/acp";
import { useAgent } from "../../../context/AgentContext";
import { ACPCard } from "./components/ACPCard";
import {
  ACPDrawer,
  formValuesToRunner,
  runnerToFormValues,
} from "./components/ACPDrawer";
import { BUILTIN_RUNNER_ORDER, isBuiltinRunner } from "./constants";
import channelStyles from "../Channels/index.module.less";
import styles from "./index.module.less";

const EMPTY_RUNNERS: Record<string, ACPRunnerConfig> = {};

export default function ACPPage() {
  const { t } = useTranslation();
  const { modal, message } = App.useApp();
  const { activeAgentId } = useAgent();
  const [runners, setRunners] =
    useState<Record<string, ACPRunnerConfig>>(EMPTY_RUNNERS);
  const [toolEnabled, setToolEnabled] = useState(false);
  const [runnersLoading, setRunnersLoading] = useState(true);
  const [toolLoading, setToolLoading] = useState(false);
  const [toolToggleLoading, setToolToggleLoading] = useState(false);
  const [hoverKey, setHoverKey] = useState<string | null>(null);
  const [toggleLoadingKey, setToggleLoadingKey] = useState<string | null>(null);
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [isCreateMode, setIsCreateMode] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm();
  const activeAgentIdRef = useRef(activeAgentId);

  useEffect(() => {
    activeAgentIdRef.current = activeAgentId;
  }, [activeAgentId]);

  useEffect(() => {
    let cancelled = false;
    setRunnersLoading(true);
    void (async () => {
      try {
        const data = await acpApi.getGlobalRunners();
        if (!cancelled) {
          setRunners(data.runners || EMPTY_RUNNERS);
        }
      } catch {
        if (!cancelled) {
          message.error(t("acp.loadFailed"));
        }
      } finally {
        if (!cancelled) {
          setRunnersLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [t]);

  useEffect(() => {
    if (!activeAgentId) {
      setToolEnabled(false);
      setToolLoading(false);
      return;
    }

    const agentId = activeAgentId;
    setToolLoading(true);

    let cancelled = false;
    void (async () => {
      try {
        const data = await acpApi.getConfig(agentId);
        if (!cancelled && activeAgentIdRef.current === agentId) {
          setToolEnabled(data.tool_enabled);
        }
      } catch {
        if (!cancelled && activeAgentIdRef.current === agentId) {
          message.error(t("acp.loadFailed"));
        }
      } finally {
        if (!cancelled && activeAgentIdRef.current === agentId) {
          setToolLoading(false);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [activeAgentId, t]);

  const orderedKeys = useMemo(() => {
    const keys = Object.keys(runners || {});
    return [
      ...BUILTIN_RUNNER_ORDER.filter((k) => keys.includes(k)),
      ...keys.filter((k) => !isBuiltinRunner(k)).sort(),
    ];
  }, [runners]);

  const cards = useMemo(() => {
    const enabled: { key: string; cfg: ACPRunnerConfig }[] = [];
    const disabled: { key: string; cfg: ACPRunnerConfig }[] = [];
    for (const key of orderedKeys) {
      const cfg = runners[key];
      if (!cfg) continue;
      (cfg.enabled ? enabled : disabled).push({ key, cfg });
    }
    return [...enabled, ...disabled];
  }, [runners, orderedKeys]);

  const persistRunners = useCallback(
    async (next: Record<string, ACPRunnerConfig>) => {
      const saved = await acpApi.updateGlobalRunners(next);
      setRunners(saved.runners || EMPTY_RUNNERS);
      return saved.runners;
    },
    [],
  );

  const persistToolEnabled = useCallback(
    async (agentId: string, checked: boolean) => {
      const saved = await acpApi.updateToolEnabled(agentId, checked);
      if (activeAgentIdRef.current === agentId) {
        setToolEnabled(saved.tool_enabled);
      }
      return saved.tool_enabled;
    },
    [],
  );

  const handleToolToggle = async (checked: boolean) => {
    const agentId = activeAgentIdRef.current;
    if (!agentId || toolLoading) return;
    setToolToggleLoading(true);
    try {
      await persistToolEnabled(agentId, checked);
      message.success(t("acp.configSaved"));
    } catch {
      message.error(t("acp.configFailed"));
    } finally {
      setToolToggleLoading(false);
    }
  };

  const handleToggleEnabled = async (runnerKey: string, checked: boolean) => {
    if (runnersLoading) return;
    const runner = runners[runnerKey];
    if (!runner) return;
    if (!runner.command?.trim() && checked) {
      message.warning(t("acp.commandRequired"));
      return;
    }
    setToggleLoadingKey(runnerKey);
    try {
      const nextRunners = {
        ...runners,
        [runnerKey]: { ...runner, enabled: checked },
      };
      await persistRunners(nextRunners);
      message.success(t("acp.configSaved"));
    } catch {
      message.error(t("acp.configFailed"));
    } finally {
      setToggleLoadingKey(null);
    }
  };

  const openEdit = (key: string) => {
    const cfg = runners[key];
    setIsCreateMode(false);
    setActiveKey(key);
    setDrawerOpen(true);
    form.setFieldsValue(runnerToFormValues(key, cfg));
  };

  const openCreate = () => {
    setIsCreateMode(true);
    setActiveKey(null);
    setDrawerOpen(true);
    form.resetFields();
    form.setFieldsValue({
      runnerKey: "",
      enabled: true,
      command: "",
      argsText: "",
      envText: "",
      trusted: true,
      tool_parse_mode: "update_detail",
      stdio_buffer_limit_bytes: ACP_DEFAULT_STDIO_BUFFER_LIMIT_BYTES,
    });
  };

  const handleSubmit = async (values: Record<string, unknown>) => {
    const targetKey = String(values.runnerKey || activeKey || "").trim();
    if (!targetKey) return;
    if ((isCreateMode || targetKey !== activeKey) && runners[targetKey]) {
      message.error(t("acp.runnerKeyExists"));
      return;
    }
    const runner = formValuesToRunner(values);
    setSaving(true);
    try {
      const nextRunners = { ...runners };
      if (!isCreateMode && activeKey && activeKey !== targetKey) {
        delete nextRunners[activeKey];
      }
      nextRunners[targetKey] = runner;
      await persistRunners(nextRunners);
      setDrawerOpen(false);
      message.success(
        isCreateMode ? t("acp.createSuccess") : t("acp.configSaved"),
      );
    } catch {
      message.error(t("acp.configFailed"));
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = () => {
    if (!activeKey || isBuiltinRunner(activeKey)) return;
    modal.confirm({
      title: t("acp.deleteTitle", { name: activeKey }),
      content: t("acp.deleteConfirm"),
      okText: t("common.delete"),
      cancelText: t("common.cancel"),
      okButtonProps: { danger: true },
      onOk: async () => {
        const nextRunners = { ...runners };
        delete nextRunners[activeKey];
        await persistRunners(nextRunners);
        setDrawerOpen(false);
        message.success(t("acp.deleteSuccess"));
      },
    });
  };

  const toolSwitch = (
    <Switch
      key={activeAgentId ?? "none"}
      checked={toolEnabled}
      loading={toolLoading || toolToggleLoading}
      disabled={!activeAgentId || toolLoading}
      onChange={handleToolToggle}
    />
  );

  return (
    <PageShell
      title={t("pageShell.acp.title")}
      subtitle={t("pageShell.acp.subtitle")}
      agentScoped
      actions={
        <Button type="primary" onClick={openCreate}>
          {t("acp.create")}
        </Button>
      }
    >
      <div className={styles.description}>{t("acp.description")}</div>
      <p className={styles.scopeHint}>{t("acp.globalRunnersHint")}</p>

      {runnersLoading && cards.length === 0 ? (
        <CardSkeleton count={4} />
      ) : (
        <div className={channelStyles.channelsGrid}>
          {cards.map(({ key, cfg }) => (
            <ACPCard
              key={key}
              runnerKey={key}
              config={cfg}
              isHover={hoverKey === key}
              toggleLoading={toggleLoadingKey === key}
              onClick={() => openEdit(key)}
              onMouseEnter={() => setHoverKey(key)}
              onMouseLeave={() => setHoverKey(null)}
              onToggleEnabled={handleToggleEnabled}
            />
          ))}
        </div>
      )}

      <div className={styles.agentToolSection}>
        <p className={styles.scopeHint}>{t("acp.toolEnabledHint")}</p>
        {!activeAgentId ? (
          <Empty
            description={t("mbtiPage.pickAgent")}
            image={Empty.PRESENTED_IMAGE_SIMPLE}
          />
        ) : (
          <div className={styles.toolToggle}>
            <span>{t("acp.toolEnabled")}</span>
            {toolSwitch}
          </div>
        )}
      </div>

      <ACPDrawer
        open={drawerOpen}
        activeKey={activeKey}
        isCreateMode={isCreateMode}
        form={form}
        saving={saving}
        canEditKey={
          isCreateMode || (activeKey ? !isBuiltinRunner(activeKey) : false)
        }
        canDelete={
          !isCreateMode && activeKey !== null && !isBuiltinRunner(activeKey)
        }
        onClose={() => setDrawerOpen(false)}
        onSubmit={handleSubmit}
        onDelete={handleDelete}
      />
    </PageShell>
  );
}
