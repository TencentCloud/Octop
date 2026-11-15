import { useEffect, useState } from "react";
import {
  Form,
  Input,
  Button,
  Alert,
  Typography,
  InputNumber,
  Space,
  Modal,
} from "antd";
import { Database, ChevronDown, ChevronUp } from "lucide-react";
import { useTranslation } from "react-i18next";

import { authApi } from "../../../api/modules/auth";
import { wizardApi, type DatabaseSetupBody } from "../wizardClient";
import { apiErrorMessage, parseApiError } from "../../../utils/apiError";
import setupStyles from "../setup.module.less";

const { Text } = Typography;

interface Props {
  onContinue: () => void;
  /** PostgreSQL target already had users; setup is finished, go to login. */
  onAdopted?: () => void;
  onBack?: () => void;
}

export default function DatabaseStep({ onContinue, onAdopted, onBack }: Props) {
  const { t } = useTranslation();
  const [form] = Form.useForm<DatabaseSetupBody>();
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [testing, setTesting] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [testedOk, setTestedOk] = useState(false);
  const [alreadyBound, setAlreadyBound] = useState(false);
  const [boundDriver, setBoundDriver] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [testMsg, setTestMsg] = useState<string | null>(null);
  const [existingUsers, setExistingUsers] = useState(0);

  useEffect(() => {
    let cancelled = false;
    authApi
      .getAuthStatus()
      .then((s) => {
        if (cancelled) return;
        if (s.database_bound) {
          setAlreadyBound(true);
          setBoundDriver(s.database_driver ?? null);
        }
      })
      .catch(() => {
        /* status optional for continue path */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const resetProbeState = () => {
    setTestedOk(false);
    setTestMsg(null);
    setError(null);
    setExistingUsers(0);
  };

  const noteProbe = (userCount: number) => {
    setExistingUsers(userCount);
    setTestedOk(true);
    setTestMsg(
      userCount > 0
        ? t("wizard.database.testOkExisting", { count: userCount })
        : t("wizard.database.testOk"),
    );
  };

  const confirmAdopt = (count: number) =>
    new Promise<boolean>((resolve) => {
      let settled = false;
      const finish = (value: boolean) => {
        if (settled) return;
        settled = true;
        resolve(value);
      };
      Modal.confirm({
        title: t("wizard.database.adoptTitle"),
        content: t("wizard.database.adoptBody", { count }),
        okText: t("wizard.database.adoptOk"),
        cancelText: t("wizard.database.adoptCancel"),
        onOk: () => finish(true),
        onCancel: () => finish(false),
      });
    });

  const buildSqliteBody = (values: DatabaseSetupBody): DatabaseSetupBody => ({
    driver: "sqlite",
    sqlite_path: values.sqlite_path?.trim() || "octop.db",
  });

  const buildPostgresBody = (values: DatabaseSetupBody): DatabaseSetupBody => ({
    driver: "postgresql",
    host: values.host?.trim() || "127.0.0.1",
    port: values.port ?? 5432,
    database: values.database?.trim() || "octop",
    user: values.user?.trim() || "octop",
    password: values.password || undefined,
  });

  const applyAndContinue = async (body: DatabaseSetupBody) => {
    await wizardApi.applyDatabase(body);
    onContinue();
  };

  const applyPostgres = async (body: DatabaseSetupBody, userCount: number) => {
    let payload = body;
    if (userCount > 0) {
      const confirmed = await confirmAdopt(userCount);
      if (!confirmed) return;
      payload = { ...body, adopt_existing: true };
    }
    try {
      const applied = await wizardApi.applyDatabase(payload);
      if (applied.adopted) onAdopted?.();
      else onContinue();
    } catch (e) {
      if (parseApiError(e)?.code !== "DATABASE_NOT_EMPTY") throw e;
      const confirmed = await confirmAdopt(userCount);
      if (!confirmed) return;
      const applied = await wizardApi.applyDatabase({
        ...body,
        adopt_existing: true,
      });
      if (applied.adopted) onAdopted?.();
      else onContinue();
    }
  };

  const onTestPostgres = async () => {
    setError(null);
    setTestMsg(null);
    setTesting(true);
    try {
      const values = await form.validateFields([
        "host",
        "port",
        "database",
        "user",
        "password",
      ]);
      const probed = await wizardApi.testDatabase(buildPostgresBody(values));
      noteProbe(probed.user_count ?? 0);
    } catch (e) {
      setTestedOk(false);
      setError(apiErrorMessage(e, t("wizard.database.testFailed"), t));
    } finally {
      setTesting(false);
    }
  };

  const onContinueSqlite = async () => {
    setError(null);
    if (alreadyBound) {
      onContinue();
      return;
    }
    setSubmitting(true);
    try {
      const values = await form.validateFields(["sqlite_path"]);
      await applyAndContinue(buildSqliteBody(values));
    } catch (e) {
      setError(apiErrorMessage(e, t("wizard.database.applyFailed"), t));
    } finally {
      setSubmitting(false);
    }
  };

  const onContinuePostgres = async () => {
    setError(null);
    setSubmitting(true);
    try {
      const values = await form.validateFields([
        "host",
        "port",
        "database",
        "user",
        "password",
      ]);
      const body = buildPostgresBody(values);
      let userCount = existingUsers;
      if (!testedOk) {
        const probed = await wizardApi.testDatabase(body);
        userCount = probed.user_count ?? 0;
        noteProbe(userCount);
      }
      await applyPostgres(body, userCount);
    } catch (e) {
      setError(apiErrorMessage(e, t("wizard.database.applyFailed"), t));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <div style={{ marginBottom: 20 }}>
        <div
          style={{
            fontSize: 16,
            fontWeight: 600,
            color: "var(--fn-text-primary)",
            marginBottom: 4,
          }}
        >
          {t("wizard.stepDatabase")}
        </div>
        <Text type="secondary" style={{ fontSize: 13 }}>
          {t("wizard.database.hint")}
        </Text>
      </div>

      {alreadyBound ? (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message={t("wizard.database.alreadyBound", {
            driver: boundDriver || "sqlite",
          })}
        />
      ) : null}

      <Form
        form={form}
        layout="vertical"
        initialValues={{
          sqlite_path: "octop.db",
          host: "127.0.0.1",
          port: 5432,
          database: "octop",
          user: "octop",
        }}
      >
        <Form.Item
          label={t("wizard.database.sqlite")}
          name="sqlite_path"
          rules={[
            {
              required: true,
              message: t("wizard.database.sqlitePathRequired"),
            },
          ]}
          extra={t("wizard.database.sqlitePathHint")}
        >
          <Input prefix={<Database size={14} />} placeholder="octop.db" />
        </Form.Item>

        <Button
          type="link"
          size="small"
          className={setupStyles.dbExpandToggle}
          onClick={() => {
            setShowAdvanced((v) => !v);
            setError(null);
            setTestMsg(null);
          }}
        >
          <span className={setupStyles.dbExpandToggleInner}>
            {showAdvanced
              ? t("wizard.database.hideAdvanced")
              : t("wizard.database.showAdvanced")}
            {showAdvanced ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </span>
        </Button>

        {showAdvanced ? (
          <div className={setupStyles.dbAdvancedPanel}>
            <div className={setupStyles.dbAdvancedTitle}>
              {t("wizard.database.postgresql")}
            </div>
            <Alert
              type="warning"
              showIcon
              style={{ marginBottom: 14 }}
              message={t("wizard.database.postgresqlBetaTitle")}
              description={t("wizard.database.postgresqlBetaHint")}
            />
            <Form.Item
              label={t("wizard.database.host")}
              name="host"
              rules={[
                { required: true, message: t("wizard.database.hostRequired") },
              ]}
            >
              <Input onChange={resetProbeState} />
            </Form.Item>
            <Form.Item label={t("wizard.database.port")} name="port">
              <InputNumber
                min={1}
                max={65535}
                style={{ width: "100%" }}
                onChange={resetProbeState}
              />
            </Form.Item>
            <Form.Item
              label={t("wizard.database.name")}
              name="database"
              rules={[
                {
                  required: true,
                  message: t("wizard.database.nameRequired"),
                },
              ]}
            >
              <Input onChange={resetProbeState} />
            </Form.Item>
            <Form.Item
              label={t("wizard.database.user")}
              name="user"
              rules={[
                { required: true, message: t("wizard.database.userRequired") },
              ]}
            >
              <Input onChange={resetProbeState} />
            </Form.Item>
            <Form.Item label={t("wizard.database.password")} name="password">
              <Input.Password onChange={resetProbeState} />
            </Form.Item>

            <Space wrap>
              <Button onClick={() => void onTestPostgres()} loading={testing}>
                {t("wizard.database.test")}
              </Button>
              <Button
                type="default"
                loading={submitting}
                disabled={!testedOk}
                onClick={() => void onContinuePostgres()}
              >
                {t("wizard.database.continueWithPostgresql")}
              </Button>
            </Space>
          </div>
        ) : null}

        {error && (
          <Alert
            type="error"
            showIcon
            style={{ marginBottom: 16 }}
            message={error}
          />
        )}
        {testMsg && (
          <Alert
            type="success"
            showIcon
            style={{ marginBottom: 16 }}
            message={testMsg}
          />
        )}

        <Space style={{ width: "100%", justifyContent: "space-between" }}>
          {onBack ? (
            <Button onClick={onBack}>{t("wizard.back")}</Button>
          ) : (
            <span />
          )}
          <Button
            type="primary"
            loading={submitting}
            onClick={() => void onContinueSqlite()}
          >
            {t("wizard.database.continue")}
          </Button>
        </Space>
      </Form>
    </>
  );
}
