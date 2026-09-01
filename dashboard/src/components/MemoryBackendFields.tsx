import { useEffect, useState } from "react";
import {
  Alert,
  Button,
  Form,
  Input,
  InputNumber,
  Radio,
  Space,
  Spin,
  Typography,
} from "antd";
import { useTranslation } from "react-i18next";

import { apiErrorMessage } from "../utils/apiError";

import { authApi } from "../api/modules/auth";
import {
  memoryDashboardApi,
  type MemoryStoreStatus,
} from "../api/modules/memoryDashboard";
import {
  isMemoryBackendChoice,
  type MemoryBackendChoice,
} from "../utils/memoryBackendChoice";

const { Text } = Typography;

export function MemoryBackendFields({
  mode,
  agentId,
}: {
  mode: "create" | "edit";
  agentId?: string;
}) {
  const { t } = useTranslation();
  const form = Form.useFormInstance();
  const choice =
    (Form.useWatch("memory_backend", form) as
      | MemoryBackendChoice
      | undefined) ?? "follow";

  const [controlPlane, setControlPlane] = useState<string | null>(null);
  const [store, setStore] = useState<MemoryStoreStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testedOk, setTestedOk] = useState(false);
  const [testMsg, setTestMsg] = useState<string | null>(null);
  const [testError, setTestError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setLoadFailed(false);

    const load = async () => {
      try {
        const status = await authApi.getAuthStatus();
        if (cancelled) return;
        setControlPlane(status.database_driver ?? "sqlite");

        if (mode === "edit" && agentId) {
          const next = await memoryDashboardApi.getStore(agentId);
          if (cancelled) return;
          setStore(next);
          if (next.connection) {
            form.setFieldsValue({
              memory_pg_host: next.connection.host,
              memory_pg_port: next.connection.port,
              memory_pg_database: next.connection.database,
              memory_pg_user: next.connection.user,
            });
          }
        }
        if (!isMemoryBackendChoice(form.getFieldValue("memory_backend"))) {
          form.setFieldsValue({ memory_backend: "follow" });
        }
      } catch {
        if (!cancelled) setLoadFailed(true);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    void load();
    return () => {
      cancelled = true;
    };
  }, [agentId, form, mode]);

  const postgresOk = controlPlane === "postgresql";
  const original = store?.choice ?? "follow";
  const changed = mode === "edit" && choice !== original;
  const occupied = Boolean(store?.has_data || store?.has_data_unknown);
  const showSwitchWarn = mode === "edit" && changed && (occupied || loadFailed);
  const canKeepExistingDsn =
    mode === "edit" &&
    store?.has_custom_dsn === true &&
    original === "postgres";
  const needsDsn = choice === "postgres" && !postgresOk;
  const markUntested = () => {
    setTestedOk(false);
    setTestMsg(null);
    setTestError(null);
    form.setFieldValue("memory_pg_tested", false);
  };
  const onTestPostgres = async () => {
    setTestError(null);
    setTestMsg(null);
    try {
      const values = await form.validateFields([
        "memory_pg_host",
        "memory_pg_port",
        "memory_pg_database",
        "memory_pg_user",
        "memory_pg_password",
      ]);
      setTesting(true);
      await memoryDashboardApi.probeStore({
        host: String(values.memory_pg_host ?? "").trim(),
        port: values.memory_pg_port ?? 5432,
        database: String(values.memory_pg_database ?? "").trim(),
        user: String(values.memory_pg_user ?? "").trim(),
        password: values.memory_pg_password || undefined,
      });
      setTestedOk(true);
      setTestMsg(t("wizard.database.testOk"));
      form.setFieldValue("memory_pg_tested", true);
    } catch (err) {
      setTestedOk(false);
      form.setFieldValue("memory_pg_tested", false);
      if (err && typeof err === "object" && "errorFields" in err) {
        return;
      }
      setTestError(apiErrorMessage(err, t("wizard.database.testFailed"), t));
    } finally {
      setTesting(false);
    }
  };
  useEffect(() => {
    // Edit must never fill wizard defaults — those look like a saved
    // connection (and will fail probe) even when the agent is already up.
    if (!needsDsn || mode === "edit") return;
    if (form.getFieldValue("memory_pg_host")) return;
    form.setFieldsValue({
      memory_pg_host: "127.0.0.1",
      memory_pg_port: 5432,
      memory_pg_database: "octop",
      memory_pg_user: "octop",
    });
  }, [form, mode, needsDsn]);
  const resolvedType = store?.resolved.type;
  const locationLabel =
    resolvedType === "postgres"
      ? t("experts.memoryStore.locationPostgres")
      : t("experts.memoryStore.locationSqlite");

  return (
    <>
      {loading ? (
        <div style={{ padding: "8px 0 16px" }}>
          <Spin size="small" />
        </div>
      ) : null}

      {mode === "edit" && store && !loading ? (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          message={`${t(
            "experts.memoryStore.currentLocation",
          )}: ${locationLabel}${
            store.resolved.location ? ` · ${store.resolved.location}` : ""
          } · ${t("experts.memoryStore.namespace", {
            namespace: store.resolved.namespace,
          })}`}
        />
      ) : null}

      {mode === "edit" && store && !store.has_data && !loadFailed ? (
        <Text
          type="secondary"
          style={{ display: "block", marginBottom: 8, fontSize: 12 }}
        >
          {t("experts.memoryStore.emptyHint")}
        </Text>
      ) : null}

      {loadFailed ? (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
          message={t("experts.memoryStore.loadFailed")}
        />
      ) : null}

      <Form.Item
        label={t("experts.memoryStore.label")}
        name="memory_backend"
        tooltip={t("experts.memoryStore.tooltip")}
        initialValue="follow"
      >
        <Radio.Group
          disabled={loading && mode === "edit"}
          onChange={markUntested}
        >
          <Space direction="vertical" size={10}>
            <Radio value="follow">
              <span>
                {t("experts.memoryStore.follow")}
                <Text
                  type="secondary"
                  style={{ display: "block", fontSize: 12, fontWeight: 400 }}
                >
                  {postgresOk
                    ? t("experts.memoryStore.followDescPostgres")
                    : t("experts.memoryStore.followDescSqlite")}
                </Text>
              </span>
            </Radio>
            <Radio value="sqlite">
              <span>
                {t("experts.memoryStore.sqlite")}
                <Text
                  type="secondary"
                  style={{ display: "block", fontSize: 12, fontWeight: 400 }}
                >
                  {t("experts.memoryStore.sqliteDesc")}
                </Text>
              </span>
            </Radio>
            <Radio value="postgres">
              <span>
                {t("experts.memoryStore.postgres")}
                <Text
                  type="secondary"
                  style={{ display: "block", fontSize: 12, fontWeight: 400 }}
                >
                  {postgresOk
                    ? t("experts.memoryStore.postgresDesc")
                    : t("experts.memoryStore.postgresOwnDsn")}
                </Text>
              </span>
            </Radio>
          </Space>
        </Radio.Group>
      </Form.Item>

      {needsDsn ? (
        <>
          <Text
            type="secondary"
            style={{ display: "block", marginBottom: 8, fontSize: 12 }}
          >
            {canKeepExistingDsn
              ? t("experts.memoryStore.dsnSavedHint")
              : t("experts.memoryStore.dsnHint")}
          </Text>
          <Form.Item
            label={t("wizard.database.host")}
            name="memory_pg_host"
            rules={
              canKeepExistingDsn
                ? undefined
                : [
                    {
                      required: true,
                      message: t("wizard.database.hostRequired"),
                    },
                  ]
            }
          >
            <Input
              placeholder="127.0.0.1"
              autoComplete="off"
              onChange={markUntested}
            />
          </Form.Item>
          <Form.Item label={t("wizard.database.port")} name="memory_pg_port">
            <InputNumber
              min={1}
              max={65535}
              style={{ width: "100%" }}
              onChange={markUntested}
            />
          </Form.Item>
          <Form.Item
            label={t("wizard.database.name")}
            name="memory_pg_database"
            rules={
              canKeepExistingDsn
                ? undefined
                : [
                    {
                      required: true,
                      message: t("wizard.database.nameRequired"),
                    },
                  ]
            }
          >
            <Input
              placeholder="octop"
              autoComplete="off"
              onChange={markUntested}
            />
          </Form.Item>
          <Form.Item
            label={t("wizard.database.user")}
            name="memory_pg_user"
            rules={
              canKeepExistingDsn
                ? undefined
                : [
                    {
                      required: true,
                      message: t("wizard.database.userRequired"),
                    },
                  ]
            }
          >
            <Input
              placeholder="octop"
              autoComplete="off"
              onChange={markUntested}
            />
          </Form.Item>
          <Form.Item
            label={t("wizard.database.password")}
            name="memory_pg_password"
          >
            <Input.Password
              autoComplete="new-password"
              onChange={markUntested}
            />
          </Form.Item>
          <Form.Item name="memory_pg_tested" hidden />
          <Space wrap style={{ marginBottom: 12 }}>
            <Button onClick={() => void onTestPostgres()} loading={testing}>
              {t("wizard.database.test")}
            </Button>
          </Space>
          {testError ? (
            <Alert
              type="error"
              showIcon
              style={{ marginBottom: 12 }}
              message={testError}
            />
          ) : null}
          {testedOk && testMsg ? (
            <Alert
              type="success"
              showIcon
              style={{ marginBottom: 12 }}
              message={testMsg}
            />
          ) : null}
        </>
      ) : null}

      {showSwitchWarn ? (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
          message={t("experts.memoryStore.switchWarn")}
        />
      ) : null}
    </>
  );
}
