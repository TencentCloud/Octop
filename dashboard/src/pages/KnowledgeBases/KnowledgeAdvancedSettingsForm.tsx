import { Form, InputNumber } from "antd";
import { useTranslation } from "react-i18next";
import type { KnowledgeAdvancedSettings } from "../../api/modules/knowledgeBases";
import styles from "./index.module.less";

const fields = [
  { name: "chunk_size", label: "chunkSize", min: 100, max: 8000 },
  { name: "chunk_overlap", label: "chunkOverlap", min: 0, max: 7999 },
  { name: "retrieval_k", label: "retrievalK", min: 1, max: 20 },
  {
    name: "context_char_budget",
    label: "contextCharBudget",
    min: 500,
    max: 50000,
  },
] as const;

export function KnowledgeAdvancedSettingsForm({
  id,
  initialValues,
  saving,
  onSave,
}: {
  id: string;
  initialValues: KnowledgeAdvancedSettings;
  saving: boolean;
  onSave: (settings: KnowledgeAdvancedSettings) => Promise<void>;
}) {
  const { t } = useTranslation();
  const [form] = Form.useForm<KnowledgeAdvancedSettings>();

  return (
    <div className={styles.indexSettings}>
      <p className={styles.settingsHint}>
        {t("knowledgeBases.indexSettingsHint")}
      </p>
      <Form<KnowledgeAdvancedSettings>
        id={id}
        form={form}
        layout="vertical"
        className={styles.indexSettingsGrid}
        initialValues={initialValues}
        onFinish={onSave}
        disabled={saving}
      >
        {fields.map(({ name, label, min, max }) => (
          <Form.Item
            key={name}
            name={name}
            label={t(`knowledgeBases.${label}`)}
            dependencies={name === "chunk_overlap" ? ["chunk_size"] : []}
            rules={[
              {
                required: true,
                type: "integer",
                min,
                max,
                message: t("knowledgeBases.advancedSettingsRange", {
                  min,
                  max,
                }),
              },
              ...(name === "chunk_overlap"
                ? [
                    {
                      validator: async (_rule: unknown, overlap: number) => {
                        if (overlap >= form.getFieldValue("chunk_size")) {
                          throw new Error(
                            t("knowledgeBases.chunkOverlapLimit"),
                          );
                        }
                      },
                    },
                  ]
                : []),
            ]}
          >
            <InputNumber
              className={styles.indexSettingsInput}
              min={min}
              max={max}
              precision={0}
            />
          </Form.Item>
        ))}
      </Form>
    </div>
  );
}
