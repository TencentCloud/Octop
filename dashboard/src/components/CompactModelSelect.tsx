import { Alert, Button, Card, Form, Select } from "antd";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { providerApi } from "../api/modules/provider";
import {
  buildModelSelectOptions,
  type ModelPickerOption,
} from "../utils/modelOptions";

function useGlobalCompactModel(agentId?: string) {
  const [value, setValue] = useState<{
    model: string | null;
    restricted?: boolean;
  }>();
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    setValue(undefined);
    setError(false);
    providerApi
      .getCompactionModel(agentId)
      .then((data) => {
        if (active) setValue(data);
      })
      .catch(() => {
        if (active) setError(true);
      });
    return () => {
      active = false;
    };
  }, [agentId, attempt]);
  return { value, setValue, error, retry: () => setAttempt((n) => n + 1) };
}

export function GlobalCompactModel({
  models,
}: {
  models: ModelPickerOption[];
}) {
  const { t } = useTranslation();
  const { value, setValue, error, retry } = useGlobalCompactModel();
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(false);
  const title = t("compactModel.global");
  useEffect(() => {
    if (window.location.hash === "#compact-model")
      document
        .getElementById("compact-model")
        ?.scrollIntoView?.({ block: "center" });
  }, []);
  return (
    <Card id="compact-model" title={title}>
      {error ? (
        <Alert
          type="error"
          message={t("compactModel.loadError")}
          action={<Button onClick={retry}>{t("common.retry")}</Button>}
        />
      ) : (
        <Select
          aria-label={title}
          style={{ width: "100%", maxWidth: 440 }}
          loading={!value || saving}
          disabled={!value || saving}
          value={value?.restricted ? undefined : value?.model ?? ""}
          placeholder={
            value?.restricted ? t("compactModel.restricted") : undefined
          }
          showSearch
          optionFilterProp="label"
          options={buildModelSelectOptions(
            models,
            t("compactModel.session", "Follow the current conversation"),
          )}
          onChange={async (ref: string) => {
            setSaving(true);
            setSaveError(false);
            try {
              setValue(await providerApi.setCompactionModel(ref || null));
            } catch {
              setSaveError(true);
            } finally {
              setSaving(false);
            }
          }}
        />
      )}
      {saveError && (
        <Alert type="error" message={t("compactModel.saveError")} />
      )}
    </Card>
  );
}

export function ExpertCompactModel({
  models,
  agentId,
  focus,
}: {
  models: ModelPickerOption[];
  agentId?: string;
  focus?: boolean;
}) {
  const { t } = useTranslation();
  const { value, error, retry } = useGlobalCompactModel(agentId);
  const inherited = value?.restricted
    ? t("compactModel.restricted")
    : value?.model ||
      t("compactModel.session", "Follow the current conversation");
  const inheritLabel = value
    ? t("compactModel.inheritValue", {
        defaultValue: "Inherit global setting ({{model}})",
        model: inherited,
      })
    : t("compactModel.inherit");
  return (
    <Form.Item
      label={t("compactModel.expert")}
      extra={
        error && (
          <Button type="link" onClick={retry}>
            {t("compactModel.loadError")} · {t("common.retry")}
          </Button>
        )
      }
    >
      <Form.Item
        name={["compaction", "model"]}
        noStyle
        getValueProps={(v) => ({ value: v ?? "" })}
      >
        <Select
          aria-label={t("compactModel.expert")}
          autoFocus={focus}
          showSearch
          optionFilterProp="label"
          options={[
            { value: "", label: inheritLabel },
            {
              value: "session",
              label: t(
                "compactModel.session",
                "Follow the current conversation",
              ),
            },
            ...buildModelSelectOptions(models, "").slice(1),
          ]}
        />
      </Form.Item>
    </Form.Item>
  );
}
