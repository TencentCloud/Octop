/**
 * Admin → Audit log page (plan §14.7).
 *
 * Paginated table with filters (since / actor / action). Backed by
 * GET /api/admin/audit-log?since=&actor=&action=&limit=.
 *
 * Mobile (<= 767 px) shows the same rows as a stacked list of items so
 * the time/actor/action/target fields stay readable without horizontal
 * scrolling. Desktop keeps the antd Table.
 */

import { useEffect, useState, useCallback } from "react";
import {
  Table,
  Button,
  Select,
  Space,
  message,
  Typography,
  DatePicker,
  Form,
  Tag,
} from "antd";
import { RefreshCw, Search } from "lucide-react";
import { useTranslation } from "react-i18next";
import PageShell from "../../../layouts/PageShell";
import { useIsMobile } from "../../../hooks/useIsMobile";
import { useServerTimezone } from "../../../hooks/useServerTimezone";
import { formatServerDateTime } from "../../../utils/formatMessageTime";
import { request } from "../../../api/request";
import styles from "./index.module.less";

const { Text } = Typography;

interface AuditRow {
  id: number;
  ts: number;
  actor: string;
  action: string;
  target: string | null;
  payload: string | null;
}

interface FilterValues {
  actor?: string;
  action?: string;
  since?: string;
  limit?: number;
}

/** Actions whose target is an agent_id — used to format target as "name (id)". */
const AGENT_ACTIONS = new Set([
  "agent.create",
  "agent.delete",
  "agent.stream.error",
]);

/** All known audit actions for the filter dropdown. */
const ACTION_OPTIONS = [
  "agent.create",
  "agent.delete",
  "agent.stream.error",
  "auth.failed",
  "auth.login",
  "auth.logout",
  "backup.restore",
  "connector.instance.create",
  "connector.instance.delete",
  "cron.create",
  "cron.delete",
  "cron.run_ok",
  "cron.run_failed",
  "security.policy.update",
  "security.tool_guard_rules.update",
  "security.tool_guard_rules.reset",
  "user.create",
  "user.delete",
  "user.disable",
  "user.enable",
  "user.unlock_login",
  "user.password_changed",
  "user.password_reset",
  "user.set_role",
];

function formatTs(ts: number, timeZone: string): string {
  return formatServerDateTime(ts, timeZone);
}

export default function AdminAuditPage() {
  const { t } = useTranslation();
  const isMobile = useIsMobile();
  const timeZone = useServerTimezone();
  const [rows, setRows] = useState<AuditRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [form] = Form.useForm<FilterValues>();

  const fetchAudit = useCallback(
    async (values: FilterValues = {}) => {
      setLoading(true);
      try {
        const qs = new URLSearchParams();
        if (values.actor) qs.set("actor", values.actor);
        if (values.action) qs.set("action", values.action);
        if (values.since) {
          const parsed = Date.parse(values.since);
          if (!Number.isNaN(parsed))
            qs.set("since", String(Math.floor(parsed / 1000)));
        }
        qs.set("limit", String(values.limit ?? 100));
        const data = await request<AuditRow[]>(`/admin/audit-log?${qs}`);
        setRows(data);
      } catch (err) {
        message.error(
          err instanceof Error ? err.message : t("adminAudit.loadFailed"),
        );
      } finally {
        setLoading(false);
      }
    },
    [t],
  );

  useEffect(() => {
    void fetchAudit();
  }, [fetchAudit]);

  const formatAction = useCallback(
    (action: string) => t(`adminAudit.actions.${action}`, action),
    [t],
  );

  const formatActor = useCallback(
    (actor: string) => {
      if (actor === "_system") return t("adminAudit.actorSystem");
      if (actor === "_admin") return t("adminAudit.actorAdmin");
      return actor;
    },
    [t],
  );

  const formatTarget = useCallback(
    (target: string | null, action: string) => {
      if (!target) return null;
      // Agent actions: show payload (agent name) + target (agent id)
      if (AGENT_ACTIONS.has(action)) {
        const row = rows.find(
          (r) => r.target === target && r.action === action,
        );
        const name = row?.payload;
        return name ? `${name} (${target})` : target;
      }
      return target;
    },
    [rows],
  );

  return (
    <PageShell
      title={t("pageShell.adminAudit.title")}
      subtitle={t("pageShell.adminAudit.subtitle")}
      actions={
        <Space>
          <Button
            icon={<RefreshCw size={14} />}
            onClick={() => fetchAudit(form.getFieldsValue())}
          >
            {t("common.refresh")}
          </Button>
        </Space>
      }
    >
      <Form<FilterValues>
        form={form}
        layout={isMobile ? "vertical" : "inline"}
        style={{
          marginBottom: 16,
          gap: isMobile ? 8 : 12,
        }}
        onFinish={fetchAudit}
        initialValues={{ limit: 100 }}
      >
        <Form.Item label={t("adminAudit.actor")} name="actor">
          <Select
            allowClear
            placeholder={t("adminAudit.actorPlaceholder")}
            options={[
              { value: "_system", label: t("adminAudit.actorSystem") },
              { value: "_admin", label: t("adminAudit.actorAdmin") },
            ]}
          />
        </Form.Item>
        <Form.Item label={t("adminAudit.action")} name="action">
          <Select
            allowClear
            showSearch
            placeholder={t("adminAudit.actionPlaceholder")}
            options={ACTION_OPTIONS.map((a) => ({
              value: a,
              label: formatAction(a),
            }))}
            optionFilterProp="label"
          />
        </Form.Item>
        <Form.Item
          label={t("adminAudit.since")}
          name="since"
          getValueFromEvent={(_, s) => s}
        >
          <DatePicker showTime format="YYYY-MM-DDTHH:mm:ss" />
        </Form.Item>
        <Form.Item label={t("adminAudit.limit")} name="limit">
          <Select
            options={[
              { value: 50, label: "50" },
              { value: 100, label: "100" },
              { value: 200, label: "200" },
              { value: 500, label: "500" },
            ]}
            style={{ width: 80 }}
          />
        </Form.Item>
        <Form.Item>
          <Button type="primary" htmlType="submit" icon={<Search size={14} />}>
            {t("adminAudit.filter")}
          </Button>
        </Form.Item>
      </Form>

      {isMobile ? (
        // Mobile: stacked item list
        <div className={styles.itemList}>
          {rows.map((row) => (
            <div key={row.id} className={styles.item}>
              <div className={styles.itemHeader}>
                <span className={styles.itemTime}>
                  {formatTs(row.ts, timeZone)}
                </span>
                <span className={styles.itemActor}>
                  {formatActor(row.actor)}
                </span>
              </div>
              <div className={styles.itemAction}>
                <Tag>{formatAction(row.action)}</Tag>
              </div>
              {row.target && (
                <div className={styles.itemField}>
                  <span className={styles.itemFieldLabel}>
                    {t("adminAudit.colTarget")}
                  </span>
                  <span className={styles.itemFieldValue}>
                    {formatTarget(row.target, row.action)}
                  </span>
                </div>
              )}
              {row.payload && !AGENT_ACTIONS.has(row.action) && (
                <div className={styles.itemField}>
                  <span className={styles.itemFieldLabel}>
                    {t("adminAudit.colPayload")}
                  </span>
                  <Text code style={{ fontSize: 12, wordBreak: "break-all" }}>
                    {row.payload}
                  </Text>
                </div>
              )}
            </div>
          ))}
          {rows.length === 0 && !loading && (
            <div className={styles.itemEmpty}>
              {t("adminAudit.empty", "No audit records")}
            </div>
          )}
        </div>
      ) : (
        <Table<AuditRow>
          rowKey="id"
          loading={loading}
          dataSource={rows}
          pagination={{ pageSize: 15 }}
          scroll={{ x: "max-content" }}
          columns={[
            {
              title: t("adminAudit.colTime"),
              dataIndex: "ts",
              width: 180,
              render: (ts: number) => formatTs(ts, timeZone),
            },
            {
              title: t("adminAudit.colActor"),
              dataIndex: "actor",
              width: 140,
              render: (actor: string) => formatActor(actor),
            },
            {
              title: t("adminAudit.colAction"),
              dataIndex: "action",
              width: 220,
              render: (action: string) => <Tag>{formatAction(action)}</Tag>,
            },
            {
              title: t("adminAudit.colTarget"),
              dataIndex: "target",
              render: (target: string | null, row: AuditRow) =>
                formatTarget(target, row.action),
            },
            {
              title: t("adminAudit.colPayload"),
              dataIndex: "payload",
              render: (p: string | null, row: AuditRow) =>
                p && !AGENT_ACTIONS.has(row.action) ? (
                  <Text code style={{ fontSize: 12 }}>
                    {p}
                  </Text>
                ) : null,
            },
          ]}
        />
      )}
    </PageShell>
  );
}
