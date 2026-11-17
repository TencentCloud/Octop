import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Alert,
  Button,
  Form,
  Input,
  InputNumber,
  Select,
  Spin,
  Switch,
} from "antd";
import { ChevronLeft, ChevronRight, FileJson, Power, Save } from "lucide-react";
import { useTranslation } from "react-i18next";
import { message } from "@/utils/antdMessage";
import {
  appConfigApi,
  type AppConfigInput,
  type AppConfigView,
} from "../../../api/modules/appConfig";
import { useServiceRestartContext } from "../../../context/ServiceRestartContext";
import { apiErrorMessage } from "../../../utils/apiError";
import CodeEditor from "../../Agent/Workspace/components/CodeEditor";
import { TabPanelHeader } from "./TabPanelHeader";
import styles from "./AppConfigPanel.module.less";

const LOG_LEVELS = ["debug", "info", "warning", "error"] as const;

const INITIAL: AppConfigInput = {
  bind_host: "127.0.0.1",
  port: 8088,
  log_level: "info",
  access_token_ttl_seconds: 86400,
  login_max_attempts: 5,
  login_lockout_seconds: 900,
  cors_origins: [],
  default_timezone: "Asia/Shanghai",
  enable_dashboard: true,
  enable_api_docs: false,
  require_setup_password: true,
  max_upload_mb: 100,
  database: {
    driver: "sqlite",
    sqlite_path: "octop.db",
    host: "127.0.0.1",
    port: 5432,
    database: "octop",
    user: "octop",
    password: "",
    url: "",
  },
  tls: {
    enabled: false,
    mode: "",
    domains: [],
    cert_file: "",
    key_file: "",
    issued_at: "",
    expires_at: "",
    acme_staging: false,
    http_port: 80,
  },
};

function joinLines(value: string[] | undefined): string {
  return (value ?? []).join("\n");
}

function splitLines(value: string): string[] {
  return String(value ?? "").split(/\r?\n/);
}

function cleanLines(value: string[] | undefined): string[] {
  return (value ?? []).map((item) => item.trim()).filter(Boolean);
}

function ianaTimeZones(): readonly string[] {
  const supported = (
    Intl as typeof Intl & { supportedValuesOf?: (key: string) => string[] }
  ).supportedValuesOf;
  if (typeof supported === "function") return supported("timeZone");
  return ["UTC", "Asia/Shanghai"];
}

const IANA_TIME_ZONES = ianaTimeZones();

function parseConfigJson(text: string): "invalid" | "not-object" | null {
  try {
    const parsed = JSON.parse(text) as unknown;
    if (
      parsed === null ||
      typeof parsed !== "object" ||
      Array.isArray(parsed)
    ) {
      return "not-object";
    }
    return null;
  } catch {
    return "invalid";
  }
}

export default function AppConfigPanel() {
  const { t } = useTranslation();
  const [form] = Form.useForm<AppConfigInput>();
  const { restartPhase, requestRestart } = useServiceRestartContext();
  const hydratingRef = useRef(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [filePath, setFilePath] = useState("");
  const [rawText, setRawText] = useState("");
  const [savedRaw, setSavedRaw] = useState("");
  const [valid, setValid] = useState(true);
  const [fileError, setFileError] = useState<string | null>(null);
  const [overrides, setOverrides] = useState<string[]>([]);
  const [restartAvailable, setRestartAvailable] = useState(false);
  const [hasPassword, setHasPassword] = useState(false);
  const [clearPassword, setClearPassword] = useState(false);
  const [formDirty, setFormDirty] = useState(false);
  const [rawDirty, setRawDirty] = useState(false);
  const [jsonError, setJsonError] = useState<"invalid" | "not-object" | null>(
    null,
  );
  const [fileOpen, setFileOpen] = useState(true);

  const driver = Form.useWatch(["database", "driver"], form) ?? "sqlite";
  const dbUrl = Form.useWatch(["database", "url"], form) ?? "";
  const timezone = Form.useWatch("default_timezone", form) ?? "";
  const timezoneOptions = useMemo(() => {
    const current = String(timezone);
    const names =
      current && !IANA_TIME_ZONES.includes(current)
        ? [current, ...IANA_TIME_ZONES]
        : IANA_TIME_ZONES;
    return names.map((value) => ({ value, label: value }));
  }, [timezone]);
  const urlSet = String(dbUrl).trim().length > 0;
  const restartLocked = restartPhase !== "idle" && restartPhase !== "timeout";
  const dirty = formDirty || rawDirty;

  const applyView = useCallback(
    (view: AppConfigView) => {
      hydratingRef.current = true;
      setFilePath(view.path);
      setRawText(view.raw);
      setSavedRaw(view.raw);
      setValid(view.valid);
      setFileError(view.error);
      setOverrides(view.overrides);
      setRestartAvailable(view.restart_available);
      setHasPassword(view.has_database_password);
      setClearPassword(false);
      setFormDirty(false);
      setRawDirty(false);
      setJsonError(parseConfigJson(view.raw));
      if (!view.valid) setFileOpen(true);
      if (view.config) {
        form.setFieldsValue({
          ...view.config,
          database: { ...view.config.database, password: "" },
        });
      }
      queueMicrotask(() => {
        hydratingRef.current = false;
      });
    },
    [form],
  );

  const load = useCallback(async () => {
    setLoading(true);
    try {
      applyView(await appConfigApi.get());
    } catch (err) {
      message.error(apiErrorMessage(err, t("adminAppConfig.loadFailed"), t));
    } finally {
      setLoading(false);
    }
  }, [applyView, t]);

  useEffect(() => {
    void load();
  }, [load]);

  const envExtra = (hint: string, ...names: string[]) => {
    const hit = names.filter((name) => overrides.includes(name));
    const override = hit.length
      ? t("adminAppConfig.envOverride", { name: hit.join(", ") })
      : "";
    return [hint, override].filter(Boolean).join(" ");
  };

  const saveForm = async (values: AppConfigInput) => {
    const typed = values.database.password;
    const password = urlSet ? null : clearPassword ? "" : typed ? typed : null;
    const body: AppConfigInput = {
      ...values,
      cors_origins: cleanLines(values.cors_origins),
      database: {
        ...values.database,
        password,
        url: String(values.database.url ?? "").trim() || null,
      },
      tls: {
        ...values.tls,
        domains: cleanLines(values.tls.domains),
      },
    };
    setSaving(true);
    try {
      const saved = await appConfigApi.save(body);
      applyView(saved);
      message.success(t("adminAppConfig.saved"));
    } catch (err) {
      message.error(apiErrorMessage(err, t("adminAppConfig.saveFailed"), t));
    } finally {
      setSaving(false);
    }
  };

  const saveRaw = async () => {
    setSaving(true);
    try {
      const saved = await appConfigApi.saveRaw(rawText);
      applyView(saved);
      message.success(t("adminAppConfig.saved"));
    } catch (err) {
      message.error(apiErrorMessage(err, t("adminAppConfig.saveFailed"), t));
    } finally {
      setSaving(false);
    }
  };

  const requestSave = () => {
    const problem = parseConfigJson(rawText);
    if (problem) {
      setJsonError(problem);
      message.error(
        problem === "not-object"
          ? t("adminAppConfig.jsonNotObject")
          : t("adminAppConfig.jsonInvalid"),
      );
      return;
    }
    setJsonError(null);
    if (rawDirty || !valid) {
      void saveRaw();
      return;
    }
    form.submit();
  };

  const dbOverrides = overrides.filter((name) =>
    name.startsWith("OCTOP_DATABASE_"),
  );

  const jsonMessage =
    jsonError === "not-object"
      ? t("adminAppConfig.jsonNotObject")
      : jsonError === "invalid"
      ? t("adminAppConfig.jsonInvalid")
      : null;

  return (
    <Spin spinning={loading}>
      <TabPanelHeader
        icon={<FileJson size={22} />}
        title={t("adminAppConfig.title")}
        description={t("adminAppConfig.description")}
      />
      <div className={styles.intro}>
        {filePath ? (
          <p className={styles.path}>
            {t("adminAppConfig.pathLabel")} <code>{filePath}</code>
          </p>
        ) : null}
        <Alert
          className={styles.alert}
          type="info"
          showIcon
          message={
            restartAvailable ? (
              t("adminAppConfig.restartHint")
            ) : (
              <span className={styles.restartLine}>
                {t("adminAppConfig.restartUnavailable")}{" "}
                <code>octop service restart</code>
                {t("adminAppConfig.restartOr")} <code>octop run</code>
              </span>
            )
          }
        />
        {dbOverrides.length > 0 ? (
          <Alert
            className={styles.alert}
            type="warning"
            showIcon
            message={t("adminAppConfig.envOverride", {
              name: dbOverrides.join(", "),
            })}
          />
        ) : null}
        {!valid ? (
          <Alert
            className={styles.alert}
            type="error"
            showIcon
            message={t("adminAppConfig.rawInvalid")}
            description={fileError ?? undefined}
          />
        ) : null}
      </div>

      <div
        className={
          fileOpen ? styles.split : `${styles.split} ${styles.splitCollapsed}`
        }
      >
        <Form<AppConfigInput>
          form={form}
          layout="vertical"
          requiredMark={false}
          disabled={!valid}
          initialValues={INITIAL}
          className={
            fileOpen ? styles.form : `${styles.form} ${styles.formRelaxed}`
          }
          onValuesChange={() => {
            if (hydratingRef.current) return;
            setFormDirty(true);
          }}
          onFinish={(values) => {
            const problem = parseConfigJson(rawText);
            if (problem) {
              setJsonError(problem);
              message.error(
                problem === "not-object"
                  ? t("adminAppConfig.jsonNotObject")
                  : t("adminAppConfig.jsonInvalid"),
              );
              return;
            }
            if (rawDirty || !valid) {
              void saveRaw();
              return;
            }
            void saveForm(values);
          }}
        >
          <div className={fileOpen ? undefined : styles.sectionGrid}>
            <section className={styles.section}>
              <div className={styles.sectionHeader}>
                <h4 className={styles.sectionTitle}>
                  {t("adminAppConfig.sectionServer")}
                </h4>
                <p className={styles.sectionHint}>
                  {t("adminAppConfig.sectionServerHint")}
                </p>
              </div>
              <div className={styles.fieldGrid}>
                <Form.Item
                  name="bind_host"
                  label={t("adminAppConfig.bindHost")}
                  extra={envExtra(
                    t("adminAppConfig.bindHostHint"),
                    "OCTOP_BIND_HOST",
                  )}
                  rules={[
                    { required: true, message: t("adminAppConfig.required") },
                  ]}
                >
                  <Input autoComplete="off" />
                </Form.Item>
                <Form.Item
                  name="port"
                  label={t("adminAppConfig.port")}
                  extra={envExtra(t("adminAppConfig.portHint"), "OCTOP_PORT")}
                  rules={[
                    { required: true, message: t("adminAppConfig.required") },
                  ]}
                >
                  <InputNumber
                    min={0}
                    max={65535}
                    precision={0}
                    style={{ width: "100%" }}
                  />
                </Form.Item>
                <Form.Item
                  name="log_level"
                  label={t("adminAppConfig.logLevel")}
                  extra={envExtra("", "OCTOP_LOG_LEVEL") || undefined}
                >
                  <Select
                    options={LOG_LEVELS.map((level) => ({
                      value: level,
                      label: level,
                    }))}
                  />
                </Form.Item>
                <Form.Item
                  name="max_upload_mb"
                  label={t("adminAppConfig.maxUpload")}
                  extra={envExtra(
                    t("adminAppConfig.maxUploadHint"),
                    "OCTOP_MAX_UPLOAD_MB",
                  )}
                  rules={[
                    { required: true, message: t("adminAppConfig.required") },
                  ]}
                >
                  <InputNumber
                    min={1}
                    max={1024}
                    precision={0}
                    style={{ width: "100%" }}
                  />
                </Form.Item>
              </div>
              <Form.Item
                name="default_timezone"
                label={t("adminAppConfig.timezone")}
                extra={envExtra(
                  t("adminAppConfig.timezoneHint"),
                  "OCTOP_DEFAULT_TIMEZONE",
                  "OCTOP_CRON_TIMEZONE",
                )}
                rules={[
                  { required: true, message: t("adminAppConfig.required") },
                ]}
              >
                <Select
                  showSearch
                  optionFilterProp="label"
                  options={timezoneOptions}
                  style={{ width: "100%" }}
                />
              </Form.Item>
              <Form.Item
                name="cors_origins"
                label={t("adminAppConfig.cors")}
                extra={envExtra(
                  t("adminAppConfig.corsHint"),
                  "OCTOP_CORS_ORIGINS",
                )}
                getValueProps={(value: string[] | undefined) => ({
                  value: joinLines(value),
                })}
                normalize={splitLines}
              >
                <Input.TextArea autoSize={{ minRows: 3, maxRows: 8 }} />
              </Form.Item>
            </section>

            <section className={styles.section}>
              <div className={styles.sectionHeader}>
                <h4 className={styles.sectionTitle}>
                  {t("adminAppConfig.sectionAccess")}
                </h4>
                <p className={styles.sectionHint}>
                  {t("adminAppConfig.sectionAccessHint")}
                </p>
              </div>
              <div className={styles.fieldGrid}>
                <Form.Item
                  name="access_token_ttl_seconds"
                  label={t("adminAppConfig.tokenTtl")}
                  extra={envExtra(
                    t("adminAppConfig.tokenTtlHint"),
                    "OCTOP_ACCESS_TOKEN_TTL",
                  )}
                  rules={[
                    { required: true, message: t("adminAppConfig.required") },
                  ]}
                >
                  <InputNumber
                    min={1}
                    precision={0}
                    style={{ width: "100%" }}
                  />
                </Form.Item>
                <Form.Item
                  name="login_max_attempts"
                  label={t("adminAppConfig.loginAttempts")}
                  extra={envExtra("", "OCTOP_LOGIN_MAX_ATTEMPTS") || undefined}
                  rules={[
                    { required: true, message: t("adminAppConfig.required") },
                  ]}
                >
                  <InputNumber
                    min={1}
                    precision={0}
                    style={{ width: "100%" }}
                  />
                </Form.Item>
                <Form.Item
                  name="login_lockout_seconds"
                  label={t("adminAppConfig.loginLockout")}
                  extra={
                    envExtra("", "OCTOP_LOGIN_LOCKOUT_SECONDS") || undefined
                  }
                  rules={[
                    { required: true, message: t("adminAppConfig.required") },
                  ]}
                >
                  <InputNumber
                    min={0}
                    precision={0}
                    style={{ width: "100%" }}
                  />
                </Form.Item>
              </div>
              <div className={styles.switches}>
                <SwitchRow
                  name="enable_dashboard"
                  label={t("adminAppConfig.enableDashboard")}
                  hint={envExtra(
                    t("adminAppConfig.enableDashboardHint"),
                    "OCTOP_ENABLE_DASHBOARD",
                  )}
                />
                <SwitchRow
                  name="enable_api_docs"
                  label={t("adminAppConfig.enableApiDocs")}
                  hint={envExtra(
                    t("adminAppConfig.enableApiDocsHint"),
                    "OCTOP_ENABLE_API_DOCS",
                  )}
                />
                <SwitchRow
                  name="require_setup_password"
                  label={t("adminAppConfig.requireSetupPassword")}
                  hint={envExtra(
                    t("adminAppConfig.requireSetupPasswordHint"),
                    "OCTOP_REQUIRE_SETUP_PASSWORD",
                  )}
                />
              </div>
            </section>

            <section className={styles.section}>
              <div className={styles.sectionHeader}>
                <h4 className={styles.sectionTitle}>
                  {t("adminAppConfig.sectionDatabase")}
                </h4>
                <p className={styles.sectionHint}>
                  {t("adminAppConfig.sectionDatabaseHint")}
                </p>
              </div>
              <Form.Item
                name={["database", "driver"]}
                label={t("adminAppConfig.driver")}
              >
                <Select
                  options={[
                    {
                      value: "sqlite",
                      label: t("adminAppConfig.driverSqlite"),
                    },
                    {
                      value: "postgresql",
                      label: t("adminAppConfig.driverPostgres"),
                    },
                  ]}
                />
              </Form.Item>
              {driver === "sqlite" ? (
                <Form.Item
                  name={["database", "sqlite_path"]}
                  label={t("adminAppConfig.sqlitePath")}
                  extra={envExtra(
                    t("adminAppConfig.sqlitePathHint"),
                    "OCTOP_DATABASE_SQLITE_PATH",
                  )}
                  rules={[
                    { required: true, message: t("adminAppConfig.required") },
                  ]}
                >
                  <Input autoComplete="off" />
                </Form.Item>
              ) : (
                <>
                  <div className={styles.fieldGrid}>
                    <Form.Item
                      name={["database", "host"]}
                      label={t("adminAppConfig.dbHost")}
                      extra={envExtra("", "OCTOP_DATABASE_HOST") || undefined}
                      rules={[
                        {
                          required: !urlSet,
                          message: t("adminAppConfig.required"),
                        },
                      ]}
                    >
                      <Input autoComplete="off" disabled={urlSet} />
                    </Form.Item>
                    <Form.Item
                      name={["database", "port"]}
                      label={t("adminAppConfig.dbPort")}
                      extra={envExtra("", "OCTOP_DATABASE_PORT") || undefined}
                      rules={[
                        {
                          required: !urlSet,
                          message: t("adminAppConfig.required"),
                        },
                      ]}
                    >
                      <InputNumber
                        min={1}
                        max={65535}
                        precision={0}
                        style={{ width: "100%" }}
                        disabled={urlSet}
                      />
                    </Form.Item>
                    <Form.Item
                      name={["database", "database"]}
                      label={t("adminAppConfig.dbName")}
                      extra={envExtra("", "OCTOP_DATABASE_NAME") || undefined}
                      rules={[
                        {
                          required: !urlSet,
                          message: t("adminAppConfig.required"),
                        },
                      ]}
                    >
                      <Input autoComplete="off" disabled={urlSet} />
                    </Form.Item>
                    <Form.Item
                      name={["database", "user"]}
                      label={t("adminAppConfig.dbUser")}
                      extra={envExtra("", "OCTOP_DATABASE_USER") || undefined}
                      rules={[
                        {
                          required: !urlSet,
                          message: t("adminAppConfig.required"),
                        },
                      ]}
                    >
                      <Input autoComplete="off" disabled={urlSet} />
                    </Form.Item>
                  </div>
                  <Form.Item
                    name={["database", "password"]}
                    label={t("adminAppConfig.dbPassword")}
                    extra={
                      urlSet
                        ? t("adminAppConfig.dbUrlPasswordHint")
                        : hasPassword
                        ? envExtra(
                            t("adminAppConfig.dbPasswordKeep"),
                            "OCTOP_DATABASE_PASSWORD",
                          )
                        : envExtra(
                            t("adminAppConfig.dbPasswordEmpty"),
                            "OCTOP_DATABASE_PASSWORD",
                          )
                    }
                  >
                    <Input.Password
                      autoComplete="new-password"
                      disabled={urlSet || clearPassword}
                    />
                  </Form.Item>
                  {hasPassword && !urlSet ? (
                    <label className={styles.check}>
                      <input
                        type="checkbox"
                        checked={clearPassword}
                        onChange={(event) => {
                          setClearPassword(event.target.checked);
                          setFormDirty(true);
                        }}
                      />
                      {t("adminAppConfig.dbPasswordClear")}
                    </label>
                  ) : null}
                  <Form.Item
                    name={["database", "url"]}
                    label={t("adminAppConfig.dbUrl")}
                    extra={envExtra(
                      t("adminAppConfig.dbUrlHint"),
                      "OCTOP_DATABASE_URL",
                    )}
                  >
                    <Input.TextArea
                      autoSize={{ minRows: 2, maxRows: 4 }}
                      autoComplete="off"
                    />
                  </Form.Item>
                </>
              )}
            </section>

            <section className={styles.section}>
              <div className={styles.sectionHeader}>
                <h4 className={styles.sectionTitle}>
                  {t("adminAppConfig.sectionTls")}
                </h4>
                <p className={styles.sectionHint}>
                  {t("adminAppConfig.sectionTlsHint")}
                </p>
              </div>
              <div className={styles.switches}>
                <SwitchRow
                  name={["tls", "enabled"]}
                  label={t("adminAppConfig.tlsEnabled")}
                  hint={t("adminAppConfig.tlsEnabledHint")}
                />
                <SwitchRow
                  name={["tls", "acme_staging"]}
                  label={t("adminAppConfig.tlsStaging")}
                  hint={t("adminAppConfig.tlsStagingHint")}
                />
              </div>
              <div className={styles.fieldGrid}>
                <Form.Item
                  name={["tls", "mode"]}
                  label={t("adminAppConfig.tlsMode")}
                >
                  <Input autoComplete="off" />
                </Form.Item>
                <Form.Item
                  name={["tls", "http_port"]}
                  label={t("adminAppConfig.tlsHttpPort")}
                  rules={[
                    { required: true, message: t("adminAppConfig.required") },
                  ]}
                >
                  <InputNumber
                    min={1}
                    max={65535}
                    precision={0}
                    style={{ width: "100%" }}
                  />
                </Form.Item>
                <Form.Item
                  name={["tls", "cert_file"]}
                  label={t("adminAppConfig.tlsCert")}
                >
                  <Input autoComplete="off" />
                </Form.Item>
                <Form.Item
                  name={["tls", "key_file"]}
                  label={t("adminAppConfig.tlsKey")}
                >
                  <Input autoComplete="off" />
                </Form.Item>
                <Form.Item
                  name={["tls", "issued_at"]}
                  label={t("adminAppConfig.tlsIssued")}
                >
                  <Input readOnly />
                </Form.Item>
                <Form.Item
                  name={["tls", "expires_at"]}
                  label={t("adminAppConfig.tlsExpires")}
                >
                  <Input readOnly />
                </Form.Item>
              </div>
              <Form.Item
                name={["tls", "domains"]}
                label={t("adminAppConfig.tlsDomains")}
                extra={t("adminAppConfig.tlsDomainsHint")}
                getValueProps={(value: string[] | undefined) => ({
                  value: joinLines(value),
                })}
                normalize={splitLines}
              >
                <Input.TextArea autoSize={{ minRows: 2, maxRows: 6 }} />
              </Form.Item>
            </section>
          </div>
        </Form>
        <aside className={fileOpen ? styles.rawColumn : styles.fileRail}>
          {fileOpen ? (
            <>
              <div className={styles.fileHeader}>
                <span className={styles.rawTitle}>
                  {t("adminAppConfig.rawTitle")}
                </span>
                <button
                  type="button"
                  className={styles.fileToggle}
                  aria-expanded
                  aria-label={t("adminAppConfig.collapseFile")}
                  onClick={() => setFileOpen(false)}
                >
                  <ChevronRight size={16} />
                </button>
              </div>
              <p className={styles.sectionHint}>
                {t("adminAppConfig.rawHint")}
              </p>
              <div
                className={
                  jsonMessage
                    ? `${styles.editorFrame} ${styles.editorInvalid}`
                    : styles.editorFrame
                }
              >
                <CodeEditor
                  path="config.json"
                  language="json"
                  value={rawText}
                  onChange={(next) => {
                    setRawText(next);
                    setRawDirty(next !== savedRaw);
                    setJsonError(parseConfigJson(next));
                  }}
                />
              </div>
              {jsonMessage ? (
                <p className={styles.jsonError}>{jsonMessage}</p>
              ) : null}
            </>
          ) : (
            <button
              type="button"
              className={styles.fileRailButton}
              aria-expanded={false}
              aria-label={t("adminAppConfig.expandFile")}
              onClick={() => setFileOpen(true)}
            >
              <ChevronLeft size={16} />
              <span className={styles.fileRailLabel}>
                {t("adminAppConfig.rawTitle")}
              </span>
              {jsonMessage ? <span className={styles.fileRailError} /> : null}
            </button>
          )}
        </aside>
      </div>

      <div className={styles.footer}>
        <div className={styles.footerActions}>
          <Button
            type="primary"
            icon={<Save size={15} />}
            loading={saving}
            disabled={!dirty || saving}
            onClick={requestSave}
          >
            {t("adminAppConfig.save")}
          </Button>
          {restartAvailable ? (
            <Button
              icon={<Power size={15} />}
              disabled={restartLocked || saving}
              onClick={requestRestart}
            >
              {restartPhase === "restarting"
                ? t("advancedSettings.update.restarting")
                : t("advancedSettings.update.restartServiceBtn")}
            </Button>
          ) : null}
          {dirty ? (
            <Button type="link" onClick={() => void load()} disabled={saving}>
              {t("adminAppConfig.discard")}
            </Button>
          ) : null}
        </div>
        <div className={styles.footerMeta}>
          {rawDirty ? (
            <span className={styles.dirtyHint}>
              {t("adminAppConfig.rawWins")}
            </span>
          ) : formDirty ? (
            <span className={styles.dirtyHint}>
              {t("adminAppConfig.unsaved")}
            </span>
          ) : (
            <span className={styles.quietHint}>
              {t("adminAppConfig.restartHint")}
            </span>
          )}
        </div>
      </div>
    </Spin>
  );
}

function SwitchRow({
  name,
  label,
  hint,
}: {
  name: string | (string | number)[];
  label: string;
  hint: string;
}) {
  return (
    <div className={styles.enableRow}>
      <div className={styles.enableText}>
        <div className={styles.sectionTitle}>{label}</div>
        {hint ? <p className={styles.sectionHint}>{hint}</p> : null}
      </div>
      <Form.Item
        name={name}
        valuePropName="checked"
        className={styles.enableSwitch}
      >
        <Switch />
      </Form.Item>
    </div>
  );
}
