import { useState } from "react";
import {
  App,
  Button,
  Checkbox,
  Collapse,
  Drawer,
  Form,
  Input,
  Select,
} from "antd";
import { Activity } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  searchApi,
  type CustomSearchProvider,
  type CustomSearchProviderUpdate,
} from "../../../api/modules/search";
import { apiErrorMessage } from "../../../utils/apiError";
import styles from "./index.module.less";

interface CustomSearchDrawerProps {
  provider: CustomSearchProvider | null;
  onClose: () => void;
  onSave: (provider: CustomSearchProviderUpdate) => Promise<void>;
}

interface CustomSearchForm {
  name: string;
  url: string;
  method: "GET" | "POST";
  api_key?: string;
  clear_api_key?: boolean;
  headers: string;
  params: string;
  body: string;
  results_path: string;
  title_path: string;
  url_path: string;
  content_path: string;
}

export default function CustomSearchDrawer({
  provider,
  onClose,
  onSave,
}: CustomSearchDrawerProps) {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const [form] = Form.useForm<CustomSearchForm>();
  const [id] = useState(
    () =>
      provider?.id ??
      (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
        ? crypto.randomUUID()
        : `custom-${Date.now().toString(36)}-${Math.random()
            .toString(36)
            .slice(2)}`),
  );
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const method = Form.useWatch("method", form);
  const clearApiKey = Form.useWatch("clear_api_key", form);
  const prefix = "advancedSettings.search.custom";

  const jsonRules = (stringsOnly: boolean) => [
    {
      validator: async (_: unknown, value: string) => {
        try {
          const parsed: unknown = JSON.parse(value);
          if (
            !parsed ||
            typeof parsed !== "object" ||
            Array.isArray(parsed) ||
            (stringsOnly &&
              Object.values(parsed).some((item) => typeof item !== "string"))
          ) {
            throw new Error();
          }
        } catch {
          throw new Error(
            t(
              `${prefix}.${
                stringsOnly ? "stringObjectRequired" : "objectRequired"
              }`,
            ),
          );
        }
      },
    },
  ];

  const readProvider = async (): Promise<CustomSearchProviderUpdate> => {
    const values = await form.validateFields();
    return {
      id,
      name: values.name.trim(),
      url: values.url.trim(),
      method: values.method,
      headers: JSON.parse(values.headers),
      params: JSON.parse(values.params),
      body: JSON.parse(values.body),
      results_path: values.results_path.trim(),
      title_path: values.title_path.trim(),
      url_path: values.url_path.trim(),
      content_path: values.content_path.trim(),
      ...(values.clear_api_key
        ? { api_key: "" }
        : values.api_key
        ? { api_key: values.api_key }
        : {}),
    };
  };

  const handleSave = async () => {
    try {
      setSaving(true);
      await onSave(await readProvider());
      onClose();
    } catch (err) {
      if (err && typeof err === "object" && "errorFields" in err) return;
      message.error(
        apiErrorMessage(err, t("setupWizard.search.saveFailed"), t),
      );
    } finally {
      setSaving(false);
    }
  };

  const handleProbe = async () => {
    try {
      setTesting(true);
      const draft = await readProvider();
      const result = await searchApi.testCustom(draft);
      if (result.success) {
        message.success(
          t("setupWizard.search.testSuccess", { name: draft.name }),
        );
      } else {
        message.error(
          t("setupWizard.search.testFailed", {
            name: draft.name,
            error:
              result.error || result.error_type || t(`${prefix}.testError`),
          }),
        );
      }
    } catch (err) {
      if (err && typeof err === "object" && "errorFields" in err) return;
      message.error(apiErrorMessage(err, t(`${prefix}.testError`), t));
    } finally {
      setTesting(false);
    }
  };

  const requiredRules = [
    { required: true, whitespace: true, message: t(`${prefix}.required`) },
  ];

  return (
    <Drawer
      title={t(`${prefix}.${provider ? "edit" : "add"}`)}
      open
      onClose={onClose}
      width={560}
      destroyOnHidden
      footer={
        <div className={styles.drawerFooter}>
          <Button onClick={onClose}>{t("common.cancel")}</Button>
          <Button
            icon={<Activity size={14} />}
            loading={testing}
            disabled={saving}
            onClick={() => void handleProbe()}
          >
            {t("advancedSettings.search.probe")}
          </Button>
          <Button
            type="primary"
            loading={saving}
            disabled={testing}
            onClick={() => void handleSave()}
          >
            {t("common.save")}
          </Button>
        </div>
      }
    >
      <div className={styles.drawerHint}>{t(`${prefix}.hint`)}</div>
      <Form
        form={form}
        layout="vertical"
        requiredMark={false}
        initialValues={{
          name: provider?.name ?? "",
          url: provider?.url ?? "",
          method: provider?.method ?? "GET",
          headers: JSON.stringify(provider?.headers ?? {}, null, 2),
          params: JSON.stringify(
            provider?.params ?? { q: "{query}", format: "json" },
            null,
            2,
          ),
          body: JSON.stringify(
            provider?.body ?? {
              query: "{query}",
              max_results: "{max_results}",
            },
            null,
            2,
          ),
          results_path: provider?.results_path ?? "results",
          title_path: provider?.title_path ?? "title",
          url_path: provider?.url_path ?? "url",
          content_path: provider?.content_path ?? "content",
        }}
      >
        <Form.Item
          name="name"
          label={t(`${prefix}.name`)}
          rules={requiredRules}
        >
          <Input maxLength={100} />
        </Form.Item>
        <Form.Item
          name="url"
          label={t(`${prefix}.url`)}
          rules={[
            ...requiredRules,
            {
              validator: async (_: unknown, value: string) => {
                if (!value?.trim()) return;
                try {
                  const url = new URL(value.trim());
                  if (url.protocol !== "http:" && url.protocol !== "https:") {
                    throw new Error();
                  }
                } catch {
                  throw new Error(t(`${prefix}.urlRequired`));
                }
              },
            },
          ]}
          extra={t(`${prefix}.urlHint`)}
        >
          <Input placeholder="https://search.example.com/search" />
        </Form.Item>
        <Form.Item name="method" label={t(`${prefix}.method`)}>
          <Select
            options={[
              { value: "GET", label: "GET" },
              { value: "POST", label: "POST" },
            ]}
          />
        </Form.Item>
        <Form.Item
          name="api_key"
          label={t(`${prefix}.apiKey`)}
          extra={t(
            `${prefix}.${provider?.api_key_set ? "keyStoredHint" : "keyHint"}`,
          )}
        >
          <Input.Password autoComplete="off" disabled={clearApiKey} />
        </Form.Item>
        {provider?.api_key_set ? (
          <Form.Item name="clear_api_key" valuePropName="checked">
            <Checkbox>{t(`${prefix}.clearKey`)}</Checkbox>
          </Form.Item>
        ) : null}
        <Collapse
          items={[
            {
              key: "advanced",
              label: t(`${prefix}.advanced`),
              forceRender: true,
              children: (
                <>
                  <div className={styles.drawerHint}>
                    {t(`${prefix}.templateHint`)}
                  </div>
                  <Form.Item
                    name="headers"
                    label={t(`${prefix}.headers`)}
                    rules={jsonRules(true)}
                    extra={t(`${prefix}.headersHint`)}
                  >
                    <Input.TextArea rows={3} spellCheck={false} />
                  </Form.Item>
                  <Form.Item
                    name="params"
                    label={t(`${prefix}.params`)}
                    rules={jsonRules(true)}
                    extra={t(`${prefix}.paramsHint`)}
                  >
                    <Input.TextArea rows={3} spellCheck={false} />
                  </Form.Item>
                  <Form.Item
                    name="body"
                    label={t(`${prefix}.body`)}
                    rules={jsonRules(false)}
                    extra={t(`${prefix}.bodyHint`)}
                    hidden={method !== "POST"}
                  >
                    <Input.TextArea rows={4} spellCheck={false} />
                  </Form.Item>
                  <div className={styles.drawerHint}>
                    {t(`${prefix}.responseHint`)}
                  </div>
                  <Form.Item
                    name="results_path"
                    label={t(`${prefix}.resultsPath`)}
                    extra={t(`${prefix}.resultsPathHint`)}
                  >
                    <Input />
                  </Form.Item>
                  {(["title_path", "url_path", "content_path"] as const).map(
                    (path) => (
                      <Form.Item
                        key={path}
                        name={path}
                        label={t(`${prefix}.${path}`)}
                        rules={path === "url_path" ? requiredRules : undefined}
                      >
                        <Input />
                      </Form.Item>
                    ),
                  )}
                </>
              ),
            },
          ]}
        />
      </Form>
    </Drawer>
  );
}
