import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Button, Form, Input, Modal, Select, Switch, Typography } from "antd";
import { message } from "@/utils/antdMessage";
import {
  EyeOff,
  FileSearch,
  FolderLock,
  ScrollText,
  ShieldAlert,
  UserCheck,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import PageShell from "../../../layouts/PageShell";
import { apiErrorMessage } from "../../../utils/apiError";
import {
  securityApi,
  type FilesystemRule,
  type HitlToolCatalogItem,
  type SecurityPolicy,
} from "../../../api/modules/security";
import { TabPanelHeader } from "../AdvancedSettings/TabPanelHeader";
import tabStyles from "../AdvancedSettings/tabContent.module.less";
import SettingsTabBar from "../shared/SettingsTabBar";
import AuditLogPanel from "./AuditLogPanel";
import HitlToolsPicker from "./HitlToolsPicker";
import ToolGuardRulesPanel from "./ToolGuardRulesPanel";
import styles from "./index.module.less";
import ForbiddenPage from "../../../components/ForbiddenPage";
import { useGatedSearchTabs } from "../../../hooks/useGatedSearchTabs";
import { SECURITY_TAB_PERMISSIONS, userCan } from "../../../utils/permissions";

const { Text } = Typography;
const { confirm } = Modal;
const { TextArea } = Input;

type SecurityTabKey =
  | "hitl"
  | "filesystem"
  | "pii"
  | "tool_guard"
  | "skill_scan"
  | "audit";

const TABS: {
  key: SecurityTabKey;
  labelKey: string;
  icon: ReactNode;
}[] = [
  {
    key: "hitl",
    labelKey: "security.tabHitl",
    icon: <UserCheck size={15} />,
  },
  {
    key: "filesystem",
    labelKey: "security.tabFilesystem",
    icon: <FolderLock size={15} />,
  },
  {
    key: "pii",
    labelKey: "security.tabPii",
    icon: <EyeOff size={15} />,
  },
  {
    key: "tool_guard",
    labelKey: "security.tabToolGuard",
    icon: <ShieldAlert size={15} />,
  },
  {
    key: "skill_scan",
    labelKey: "security.tabSkillScan",
    icon: <FileSearch size={15} />,
  },
  {
    key: "audit",
    labelKey: "security.tabAudit",
    icon: <ScrollText size={15} />,
  },
];

function parseTab(raw: string | null): SecurityTabKey {
  if (
    raw === "filesystem" ||
    raw === "pii" ||
    raw === "tool_guard" ||
    raw === "skill_scan" ||
    raw === "audit"
  ) {
    return raw;
  }
  return "hitl";
}

function pathsToText(rules: FilesystemRule[]): string {
  const paths = rules.flatMap((r) => r.paths);
  return paths.join("\n");
}

function textToRules(text: string | undefined): FilesystemRule[] {
  const paths = (text ?? "")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  if (paths.length === 0) return [];
  return [{ operations: ["read", "write"], paths, mode: "deny" }];
}

function PolicyFooter({
  saving,
  onSave,
}: {
  saving: boolean;
  onSave: () => void;
}) {
  const { t } = useTranslation();
  return (
    <div className={styles.footer}>
      <Button type="primary" loading={saving} onClick={onSave}>
        {t("security.saveAll")}
      </Button>
      <Text type="secondary" className={styles.runtimeHint}>
        {t("security.saveAllHint")}
      </Text>
    </div>
  );
}

export default function SecuritySettingsPage() {
  const { t } = useTranslation();
  const { user, allowedTabs, activeTab, forbidden, selectTab } =
    useGatedSearchTabs({
      tabs: TABS,
      tabPermissions: SECURITY_TAB_PERMISSIONS,
      parseTab,
      querylessKey: "hitl",
    });
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [policy, setPolicy] = useState<SecurityPolicy | null>(null);
  const [hitlToolCatalog, setHitlToolCatalog] = useState<HitlToolCatalogItem[]>(
    [],
  );
  const [hitlDefaultTools, setHitlDefaultTools] = useState<string[]>([]);

  const fetchPolicy = useCallback(async () => {
    setLoading(true);
    try {
      const [cfg, defaults] = await Promise.all([
        securityApi.getPolicy(),
        securityApi.getDefaults(),
      ]);
      setPolicy(cfg);
      setHitlToolCatalog(defaults.hitl_tool_catalog);
      setHitlDefaultTools([...defaults.hitl_tools]);
      const tools =
        cfg.hitl.tools === "default"
          ? [...defaults.hitl_tools]
          : cfg.hitl.tools;
      form.setFieldsValue({
        hitl_enabled: cfg.hitl.enabled,
        hitl_tools: tools,
        fs_enabled: cfg.filesystem.enabled,
        fs_paths: pathsToText(cfg.filesystem.rules),
        pii_enabled: cfg.pii.enabled,
        pii_strategy: cfg.pii.strategy,
        skill_scan_mode: cfg.skill_scan.mode,
        tool_guard_enabled: cfg.tool_guard?.enabled ?? true,
        tool_guard_mode: cfg.tool_guard?.mode ?? "warn",
      });
    } catch (err) {
      message.error(apiErrorMessage(err, t("security.loadError"), t));
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [form, t]);

  useEffect(() => {
    if (userCan(user, "security")) {
      void fetchPolicy();
      return;
    }
    setLoading(false);
  }, [fetchPolicy, user]);

  const handleSave = async () => {
    try {
      await form.validateFields();
      const values = form.getFieldsValue(true);
      setSaving(true);
      const body: Partial<SecurityPolicy> = {
        hitl: {
          enabled: values.hitl_enabled ?? policy?.hitl.enabled ?? false,
          tools: (values.hitl_tools as string[] | undefined) ?? [],
          allowed_decisions: policy?.hitl.allowed_decisions ?? [
            "approve",
            "reject",
          ],
        },
        filesystem: {
          enabled: values.fs_enabled ?? policy?.filesystem.enabled ?? true,
          rules: textToRules(values.fs_paths as string | undefined),
        },
        pii: {
          enabled: values.pii_enabled ?? policy?.pii.enabled ?? true,
          strategy: values.pii_strategy ?? policy?.pii.strategy ?? "mask",
          surfaces: policy?.pii.surfaces ?? ["input", "output", "tool_results"],
        },
        skill_scan: {
          mode: values.skill_scan_mode ?? policy?.skill_scan.mode ?? "warn",
        },
        tool_guard: {
          enabled:
            values.tool_guard_enabled ?? policy?.tool_guard?.enabled ?? true,
          mode: values.tool_guard_mode ?? policy?.tool_guard?.mode ?? "warn",
        },
      };
      const saved = await securityApi.savePolicy(body);
      setPolicy(saved);
      message.success(t("security.saved"));
    } catch (err) {
      if (err && typeof err === "object" && "errorFields" in err) return;
      message.error(apiErrorMessage(err, t("security.saveFailed"), t));
      console.error(err);
    } finally {
      setSaving(false);
    }
  };

  const saveFooter = (
    <PolicyFooter saving={saving} onSave={() => void handleSave()} />
  );

  const renderPolicyTab = () => {
    switch (activeTab) {
      case "hitl":
        return (
          <>
            <TabPanelHeader
              icon={<UserCheck size={22} />}
              title={t("security.tabHitl")}
              description={t("security.hitlDesc")}
            />
            <div className={tabStyles.formFields}>
              <Form.Item
                name="hitl_enabled"
                label={t("security.hitlEnable")}
                valuePropName="checked"
                extra={t("security.hitlHint")}
              >
                <Switch
                  onChange={(checked) => {
                    if (checked) {
                      confirm({
                        title: t("security.hitlEnable"),
                        content: t("security.hitlEnableWarning"),
                        okText: t("common.confirm"),
                        cancelText: t("common.cancel"),
                        onCancel: () => {
                          form.setFieldValue("hitl_enabled", false);
                        },
                      });
                    }
                  }}
                />
              </Form.Item>
            </div>
            <div className={styles.hitlToolsSection}>
              <Form.Item name="hitl_tools" label={t("security.hitlTools")}>
                <HitlToolsPicker
                  catalog={hitlToolCatalog}
                  defaultTools={hitlDefaultTools}
                />
              </Form.Item>
            </div>
            {saveFooter}
          </>
        );
      case "filesystem":
        return (
          <>
            <TabPanelHeader
              icon={<FolderLock size={22} />}
              title={t("security.tabFilesystem")}
              description={t("security.fsDesc")}
            />
            <div className={tabStyles.formFieldsWide}>
              <Form.Item
                name="fs_enabled"
                label={t("security.fsEnable")}
                valuePropName="checked"
              >
                <Switch />
              </Form.Item>
              <Form.Item
                name="fs_paths"
                label={t("security.fsPaths")}
                extra={t("security.fsHint")}
              >
                <TextArea
                  rows={10}
                  className={styles.pathTextArea}
                  placeholder={"/etc/**\n/root/**"}
                />
              </Form.Item>
            </div>
            {saveFooter}
          </>
        );
      case "pii":
        return (
          <>
            <TabPanelHeader
              icon={<EyeOff size={22} />}
              title={t("security.tabPii")}
              description={t("security.piiDesc")}
            />
            <div className={tabStyles.formFields}>
              <Form.Item
                name="pii_enabled"
                label={t("security.piiEnable")}
                valuePropName="checked"
              >
                <Switch />
              </Form.Item>
              <Form.Item name="pii_strategy" label={t("security.piiStrategy")}>
                <Select
                  options={[
                    { value: "mask", label: t("security.piiMask") },
                    { value: "redact", label: t("security.piiRedact") },
                    { value: "block", label: t("security.piiBlock") },
                    { value: "hash", label: t("security.piiHash") },
                  ]}
                />
              </Form.Item>
            </div>
            {saveFooter}
          </>
        );
      case "tool_guard":
        return (
          <>
            <TabPanelHeader
              icon={<ShieldAlert size={22} />}
              title={t("security.tabToolGuard")}
              description={t("security.toolGuardDesc")}
            />
            <div className={tabStyles.formFields}>
              <Form.Item
                name="tool_guard_enabled"
                label={t("security.toolGuardEnable")}
                valuePropName="checked"
              >
                <Switch />
              </Form.Item>
              <Form.Item
                name="tool_guard_mode"
                label={t("security.toolGuardMode")}
                extra={t("security.toolGuardHint")}
              >
                <Select
                  options={[
                    {
                      value: "block",
                      label: t("security.toolGuardBlock"),
                    },
                    {
                      value: "require_approval",
                      label: t("security.toolGuardRequireApproval"),
                    },
                    { value: "warn", label: t("security.toolGuardWarn") },
                  ]}
                />
              </Form.Item>
            </div>
            <div className={styles.rulesSection}>
              <h4 className={styles.rulesSectionTitle}>
                {t("security.rulesSection")}
              </h4>
              <ToolGuardRulesPanel />
            </div>
            {saveFooter}
          </>
        );
      case "skill_scan":
        return (
          <>
            <TabPanelHeader
              icon={<FileSearch size={22} />}
              title={t("security.tabSkillScan")}
              description={t("security.skillScanDesc")}
            />
            <div className={tabStyles.formFields}>
              <Form.Item
                name="skill_scan_mode"
                label={t("security.skillScanMode")}
                extra={t("security.skillScanHint")}
              >
                <Select
                  options={[
                    { value: "off", label: t("security.skillScanOff") },
                    { value: "warn", label: t("security.skillScanWarn") },
                    {
                      value: "block",
                      label: t("security.skillScanBlock"),
                    },
                  ]}
                />
              </Form.Item>
            </div>
            {saveFooter}
          </>
        );
      default:
        return null;
    }
  };

  if (forbidden) return <ForbiddenPage />;

  return (
    <PageShell.Tabbed
      title={t("pageShell.security.title")}
      subtitle={t("pageShell.security.subtitle")}
      tabBar={
        <SettingsTabBar
          tabs={allowedTabs}
          activeKey={activeTab}
          onChange={selectTab}
        />
      }
    >
      {activeTab === "audit" ? (
        <div className={styles.panel}>
          <TabPanelHeader
            icon={<ScrollText size={22} />}
            title={t("security.tabAudit")}
            description={t("security.auditDesc")}
          />
          <AuditLogPanel />
        </div>
      ) : null}
      {/* Keep Form mounted (visually hidden on audit) so policy values persist. */}
      <Form
        form={form}
        layout="vertical"
        disabled={loading}
        className={styles.panel}
        hidden={activeTab === "audit"}
        preserve
      >
        {activeTab !== "audit" ? renderPolicyTab() : null}
      </Form>
    </PageShell.Tabbed>
  );
}
