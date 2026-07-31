import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Collapse,
  Input,
  Popconfirm,
  Space,
  Spin,
  Table,
  Tag,
  Typography,
} from "antd";
import { message } from "@/utils/antdMessage";

import type { ColumnsType } from "antd/es/table";
import { useTranslation } from "react-i18next";
import { securityApi, type ToolGuardRule } from "../../../api/modules/security";
import styles from "./index.module.less";

const { Text, Paragraph } = Typography;
const { TextArea } = Input;

const SEVERITY_COLOR: Record<string, string> = {
  CRITICAL: "red",
  HIGH: "orange",
  MEDIUM: "gold",
  LOW: "blue",
  INFO: "default",
};

export default function ToolGuardRulesPanel() {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [rules, setRules] = useState<ToolGuardRule[]>([]);
  const [rulesPath, setRulesPath] = useState("");
  const [yamlDraft, setYamlDraft] = useState("");
  const [yamlDirty, setYamlDirty] = useState(false);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [catalog, raw] = await Promise.all([
        securityApi.getToolGuardRules(),
        securityApi.getToolGuardRulesRaw(),
      ]);
      setRules(catalog.rules);
      setRulesPath(catalog.path);
      setYamlDraft(raw.content);
      setYamlDirty(false);
    } catch (err) {
      console.error(err);
      message.error(t("security.toolGuardLoadError"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  const handleSaveYaml = async () => {
    setSaving(true);
    try {
      const saved = await securityApi.saveToolGuardRulesRaw(yamlDraft);
      message.success(
        t("security.toolGuardRulesSaved", { count: saved.rule_count }),
      );
      setYamlDirty(false);
      await loadAll();
    } catch (err: unknown) {
      let detail: string | null = null;
      if (err instanceof Error) {
        const jsonStart = err.message.indexOf("{");
        if (jsonStart >= 0) {
          try {
            const body = JSON.parse(err.message.slice(jsonStart)) as {
              detail?: { errors?: string[] };
            };
            if (body.detail?.errors?.length) {
              detail = body.detail.errors.join("\n");
            }
          } catch {
            /* ignore */
          }
        }
      }
      message.error(detail || t("security.toolGuardRulesSaveFailed"));
    } finally {
      setSaving(false);
    }
  };

  const handleReset = async () => {
    setResetting(true);
    try {
      const raw = await securityApi.resetToolGuardRules();
      setYamlDraft(raw.content);
      setYamlDirty(false);
      message.success(t("security.toolGuardRulesReset"));
      await loadAll();
    } catch (err) {
      console.error(err);
      message.error(t("security.toolGuardRulesResetFailed"));
    } finally {
      setResetting(false);
    }
  };

  const columns: ColumnsType<ToolGuardRule> = useMemo(
    () => [
      {
        title: t("security.toolGuardColSeverity"),
        dataIndex: "severity",
        width: 110,
        render: (severity: string) => (
          <Tag color={SEVERITY_COLOR[severity] ?? "default"}>{severity}</Tag>
        ),
      },
      {
        title: t("security.toolGuardColDescription"),
        dataIndex: "description",
        render: (text: string, row) => (
          <div>
            <Text>{text || row.id}</Text>
            <div>
              <Text type="secondary" className={styles.ruleId}>
                {row.id}
              </Text>
            </div>
          </div>
        ),
      },
      {
        title: t("security.toolGuardColTools"),
        dataIndex: "tools",
        width: 140,
        render: (tools: string[]) =>
          tools.length > 0 ? (
            tools.map((name) => <Tag key={name}>{name}</Tag>)
          ) : (
            <Tag>*</Tag>
          ),
      },
      {
        title: t("security.toolGuardColPatterns"),
        dataIndex: "patterns",
        width: 220,
        render: (patterns: string[]) => (
          <Text code className={styles.patternCell}>
            {patterns[0] ?? "—"}
            {patterns.length > 1 ? ` (+${patterns.length - 1})` : ""}
          </Text>
        ),
      },
    ],
    [t],
  );

  if (loading) {
    return (
      <div className={styles.rulesLoading}>
        <Spin />
      </div>
    );
  }

  return (
    <div className={styles.rulesPanel}>
      <Alert
        type="info"
        showIcon
        message={t("security.toolGuardRulesTitle", { count: rules.length })}
        description={
          <Paragraph className={styles.rulesMaintain}>
            {t("security.toolGuardRulesMaintain", { path: rulesPath })}
          </Paragraph>
        }
        style={{ marginBottom: 12 }}
      />

      <div className={styles.yamlEditor}>
        <Text strong>{t("security.toolGuardYamlEditor")}</Text>
        <TextArea
          className={styles.yamlTextArea}
          rows={14}
          value={yamlDraft}
          onChange={(e) => {
            setYamlDraft(e.target.value);
            setYamlDirty(true);
          }}
          spellCheck={false}
        />
        <Space style={{ marginTop: 8 }}>
          <Button
            type="primary"
            loading={saving}
            disabled={!yamlDirty}
            onClick={() => void handleSaveYaml()}
          >
            {t("security.toolGuardSaveRules")}
          </Button>
          <Popconfirm
            title={t("security.toolGuardResetConfirm")}
            onConfirm={() => void handleReset()}
          >
            <Button loading={resetting}>
              {t("security.toolGuardResetRules")}
            </Button>
          </Popconfirm>
        </Space>
      </div>

      <Table
        size="small"
        rowKey="id"
        style={{ marginTop: 16 }}
        pagination={{ pageSize: 10, hideOnSinglePage: true }}
        columns={columns}
        dataSource={rules}
        expandable={{
          expandedRowRender: (row) => (
            <div className={styles.ruleDetail}>
              {row.remediation ? (
                <Paragraph>
                  <Text strong>{t("security.toolGuardRemediation")}: </Text>
                  {row.remediation}
                </Paragraph>
              ) : null}
              <Collapse
                size="small"
                items={[
                  {
                    key: "patterns",
                    label: t("security.toolGuardAllPatterns", {
                      count: row.patterns.length,
                    }),
                    children: (
                      <ul className={styles.patternList}>
                        {row.patterns.map((pat) => (
                          <li key={pat}>
                            <Text code>{pat}</Text>
                          </li>
                        ))}
                      </ul>
                    ),
                  },
                ]}
              />
            </div>
          ),
        }}
      />
    </div>
  );
}
