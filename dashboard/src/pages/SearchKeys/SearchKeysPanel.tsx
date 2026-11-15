/**
 * SearchKeys — per-user web-search credentials.
 *
 * Self-service page: any logged-in user manages their own search keys here. A
 * personal key overrides the administrator's global env key for this user's
 * turns; keys are write-only and never echoed back.
 */
import { useCallback, useEffect, useState } from "react";
import { Button, Empty, Input, Popconfirm, Spin, Tag, Typography } from "antd";
import { KeyRound, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { message } from "@/utils/antdMessage";
import {
  userSearchKeysApi,
  type SearchKeyStatus,
} from "../../api/modules/userSearchKeys";
import { apiErrorMessage } from "../../utils/apiError";
import { useServerTimezone } from "../../hooks/useServerTimezone";
import { formatServerDateTime } from "../../utils/formatMessageTime";

const { Text, Title } = Typography;

type Drafts = Record<string, Record<string, string>>;

function envNames(row: SearchKeyStatus): string[] {
  return [...row.env_vars, ...row.optional_env_vars];
}

function hasAnyValue(
  row: SearchKeyStatus,
  draft: Record<string, string>,
): boolean {
  return envNames(row).some((key) => (draft[key] ?? "").trim().length > 0);
}

function isComplete(
  row: SearchKeyStatus,
  draft: Record<string, string>,
): boolean {
  return row.env_vars.every((key) => (draft[key] ?? "").trim().length > 0);
}

export function SearchKeysPanel() {
  const { t } = useTranslation();
  const timeZone = useServerTimezone();
  const [rows, setRows] = useState<SearchKeyStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Drafts>({});

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const all = await userSearchKeysApi.list();
      setRows(all.filter((row) => row.personal_key));
    } catch (error) {
      message.error(apiErrorMessage(error, t("searchKeys.loadFailed"), t));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  const setDraft = (providerId: string, key: string, value: string) => {
    setDrafts((prev) => ({
      ...prev,
      [providerId]: { ...prev[providerId], [key]: value },
    }));
  };

  const save = async (row: SearchKeyStatus) => {
    const draft = drafts[row.provider_id] ?? {};
    const env: Record<string, string> = {};
    envNames(row).forEach((key) => {
      const value = (draft[key] ?? "").trim();
      if (value) env[key] = value;
    });
    if (!isComplete(row, draft) || !hasAnyValue(row, draft)) return;
    setSaving(row.provider_id);
    try {
      const status = await userSearchKeysApi.set(row.provider_id, env);
      setRows((prev) =>
        prev.map((item) =>
          item.provider_id === row.provider_id
            ? { ...status, personal_key: true }
            : item,
        ),
      );
      setDrafts((prev) => ({ ...prev, [row.provider_id]: {} }));
      message.success(t("searchKeys.saved"));
    } catch (error) {
      message.error(apiErrorMessage(error, t("searchKeys.saveFailed"), t));
    } finally {
      setSaving(null);
    }
  };

  const remove = async (row: SearchKeyStatus) => {
    setSaving(row.provider_id);
    try {
      await userSearchKeysApi.remove(row.provider_id);
      setRows((prev) =>
        prev.map((item) =>
          item.provider_id === row.provider_id
            ? { ...item, has_own_key: false, updated_at: null }
            : item,
        ),
      );
      message.success(
        t(
          row.user_key_required
            ? "searchKeys.deletedNoGlobal"
            : "searchKeys.deleted",
        ),
      );
    } catch (error) {
      message.error(apiErrorMessage(error, t("searchKeys.deleteFailed"), t));
    } finally {
      setSaving(null);
    }
  };

  return (
    <section>
      <Title level={5} style={{ marginBottom: 4 }}>
        <KeyRound size={14} style={{ marginRight: 6, verticalAlign: -2 }} />
        {t("searchKeys.title")}
      </Title>
      <Text type="secondary" style={{ display: "block", marginBottom: 12 }}>
        {t("searchKeys.hint")}
      </Text>
      <Spin spinning={loading}>
        {rows.length === 0 && !loading ? (
          <Empty description={t("searchKeys.empty")} />
        ) : (
          rows.map((row) => {
            const draft = drafts[row.provider_id] ?? {};
            const names = envNames(row);
            return (
              <div
                key={row.provider_id}
                style={{
                  padding: "12px 0",
                  borderTop: "1px solid rgba(128,128,128,0.15)",
                }}
              >
                <div
                  style={{
                    display: "flex",
                    flexWrap: "wrap",
                    alignItems: "center",
                    gap: 8,
                  }}
                >
                  <Text strong style={{ minWidth: 120 }}>
                    {t(row.label_key)}
                  </Text>
                  {row.has_own_key ? (
                    <Tag color="green">{t("searchKeys.hasOwn")}</Tag>
                  ) : row.user_key_required ? (
                    <Tag color="orange">{t("searchKeys.requiredTag")}</Tag>
                  ) : row.env_vars.length === 0 ? (
                    <Tag>{t("searchKeys.keyless")}</Tag>
                  ) : (
                    <Tag>{t("searchKeys.usingGlobal")}</Tag>
                  )}
                  {row.has_own_key && row.updated_at ? (
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      {t("searchKeys.updated", {
                        time: formatServerDateTime(row.updated_at, timeZone),
                      })}
                    </Text>
                  ) : null}
                </div>
                <div
                  style={{
                    display: "flex",
                    flexWrap: "wrap",
                    alignItems: "center",
                    gap: 8,
                    marginTop: 8,
                  }}
                >
                  {names.map((name) => (
                    <Input.Password
                      key={name}
                      style={{ flex: "1 1 220px", maxWidth: 300 }}
                      autoComplete="new-password"
                      placeholder={
                        row.optional_env_vars.includes(name)
                          ? t("searchKeys.optionalPlaceholder", { key: name })
                          : t("searchKeys.inputPlaceholder", { key: name })
                      }
                      value={draft[name] ?? ""}
                      onChange={(e) =>
                        setDraft(row.provider_id, name, e.target.value)
                      }
                      onPressEnter={() => void save(row)}
                    />
                  ))}
                  <Button
                    type="primary"
                    size="small"
                    loading={saving === row.provider_id}
                    disabled={
                      !isComplete(row, draft) || !hasAnyValue(row, draft)
                    }
                    onClick={() => void save(row)}
                  >
                    {t("searchKeys.save")}
                  </Button>
                  {row.has_own_key && (
                    <Popconfirm
                      title={t("searchKeys.delete")}
                      description={
                        row.user_key_required
                          ? t("searchKeys.deleteWarnNoGlobal")
                          : undefined
                      }
                      onConfirm={() => void remove(row)}
                    >
                      <Button
                        size="small"
                        danger
                        icon={<Trash2 size={13} />}
                        loading={saving === row.provider_id}
                      />
                    </Popconfirm>
                  )}
                </div>
              </div>
            );
          })
        )}
      </Spin>
    </section>
  );
}
