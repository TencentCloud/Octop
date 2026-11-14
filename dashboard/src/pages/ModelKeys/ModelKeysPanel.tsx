/**
 * ModelKeys — per-user provider API keys (bring-your-own-key).
 *
 * Self-service page: any logged-in user manages their own keys here. A
 * personal key overrides the provider's global key for this user's calls;
 * keys are write-only and never echoed back.
 */
import { useCallback, useEffect, useState } from "react";
import { Button, Empty, Input, Popconfirm, Spin, Tag, Typography } from "antd";
import { KeyRound, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { message } from "@/utils/antdMessage";
import {
  userProviderKeysApi,
  type ProviderKeyStatus,
} from "../../api/modules/userProviderKeys";
import { apiErrorMessage } from "../../utils/apiError";
import { useServerTimezone } from "../../hooks/useServerTimezone";
import { formatServerDateTime } from "../../utils/formatMessageTime";

const { Text, Title } = Typography;

export function ModelKeysPanel() {
  const { t } = useTranslation();
  const timeZone = useServerTimezone();
  const [rows, setRows] = useState<ProviderKeyStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setRows(await userProviderKeysApi.list());
    } catch (error) {
      message.error(apiErrorMessage(error, t("models.myKeysSaveFailed"), t));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  const save = async (providerName: string) => {
    const key = (drafts[providerName] ?? "").trim();
    if (!key) return;
    setSaving(providerName);
    try {
      const status = await userProviderKeysApi.set(providerName, key);
      setRows((prev) =>
        prev.map((row) => (row.provider_name === providerName ? status : row)),
      );
      setDrafts((prev) => ({ ...prev, [providerName]: "" }));
      message.success(t("models.myKeysSaved"));
    } catch (error) {
      message.error(apiErrorMessage(error, t("models.myKeysSaveFailed"), t));
    } finally {
      setSaving(null);
    }
  };

  const remove = async (providerName: string) => {
    const required =
      rows.find((row) => row.provider_name === providerName)
        ?.user_key_required === true;
    setSaving(providerName);
    try {
      await userProviderKeysApi.remove(providerName);
      setRows((prev) =>
        prev.map((row) =>
          row.provider_name === providerName
            ? { ...row, has_own_key: false, updated_at: null }
            : row,
        ),
      );
      message.success(
        t(required ? "models.myKeysDeletedNoGlobal" : "models.myKeysDeleted"),
      );
    } catch (error) {
      message.error(apiErrorMessage(error, t("models.myKeysSaveFailed"), t));
    } finally {
      setSaving(null);
    }
  };

  return (
    <section>
      <Title level={5} style={{ marginBottom: 4 }}>
        <KeyRound size={14} style={{ marginRight: 6, verticalAlign: -2 }} />
        {t("models.myKeysTitle")}
      </Title>
      <Text type="secondary" style={{ display: "block", marginBottom: 12 }}>
        {t("models.myKeysHint")}
      </Text>
      <Spin spinning={loading}>
        {rows.length === 0 && !loading ? (
          <Empty description={t("models.myKeysEmpty")} />
        ) : (
          rows.map((row) => (
            <div
              key={row.provider_name}
              style={{
                display: "flex",
                flexWrap: "wrap",
                alignItems: "center",
                gap: 8,
                padding: "10px 0",
                borderTop: "1px solid rgba(128,128,128,0.15)",
              }}
            >
              <Text strong style={{ minWidth: 120 }}>
                {row.provider_name}
              </Text>
              {row.has_own_key ? (
                <Tag color="green">{t("models.myKeysHasOwn")}</Tag>
              ) : row.user_key_required ? (
                <Tag color="orange">{t("models.myKeysRequiredTag")}</Tag>
              ) : (
                <Tag>{t("models.myKeysUsingGlobal")}</Tag>
              )}
              {row.has_own_key && row.updated_at ? (
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {t("models.myKeysUpdated", {
                    time: formatServerDateTime(row.updated_at, timeZone),
                  })}
                </Text>
              ) : null}
              <Input.Password
                style={{ flex: "1 1 220px", maxWidth: 360 }}
                autoComplete="new-password"
                placeholder={t("models.myKeysInputPlaceholder")}
                value={drafts[row.provider_name] ?? ""}
                onChange={(e) =>
                  setDrafts((prev) => ({
                    ...prev,
                    [row.provider_name]: e.target.value,
                  }))
                }
                onPressEnter={() => void save(row.provider_name)}
              />
              <Button
                type="primary"
                size="small"
                loading={saving === row.provider_name}
                disabled={!(drafts[row.provider_name] ?? "").trim()}
                onClick={() => void save(row.provider_name)}
              >
                {t("models.myKeysSave")}
              </Button>
              {row.has_own_key && (
                <Popconfirm
                  title={t("models.myKeysDelete")}
                  description={
                    row.user_key_required
                      ? t("models.myKeysDeleteWarnNoGlobal")
                      : undefined
                  }
                  onConfirm={() => void remove(row.provider_name)}
                >
                  <Button
                    size="small"
                    danger
                    icon={<Trash2 size={13} />}
                    loading={saving === row.provider_name}
                  />
                </Popconfirm>
              )}
            </div>
          ))
        )}
      </Spin>
    </section>
  );
}
