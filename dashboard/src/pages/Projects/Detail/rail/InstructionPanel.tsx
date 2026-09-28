import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button, Empty, Input, Spin, Typography } from "antd";
import { Check, Pencil, X } from "lucide-react";

import { projectConfigApi } from "../../../../api/modules/projectConfig";
import { apiErrorMessage } from "../../../../utils/apiError";
import { message } from "../../../../utils/antdMessage";
import styles from "./InstructionPanel.module.less";

const { Text } = Typography;

/** PLAN §5：指令上限按**字符数**计（后端 400 是权威，这里只做前置提示）。 */
const INSTRUCTION_MAX_CHARS = 2000;

interface InstructionPanelProps {
  projectId: string;
  /** `PROJECT_MANAGE_CONFIG`（owner/admin）才可编辑；其余为只读展示。 */
  canManage: boolean;
}

/**
 * 右栏「指令」面板（PLAN §5 / S12）。
 *
 * 纯展示 + 编辑：`instruction` 不进任何 LLM 上下文（零注入面由后端保证）。
 * 空串 = 合法的「未填写」态（S12），显示占位而不是空控件。
 */
export default function InstructionPanel({
  projectId,
  canManage,
}: InstructionPanelProps) {
  const { t } = useTranslation();
  const [text, setText] = useState("");
  const [draft, setDraft] = useState("");
  const [editing, setEditing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setEditing(false);
    projectConfigApi
      .getInstruction(projectId)
      .then((data) => {
        if (cancelled) return;
        setText(data.instruction);
        setDraft(data.instruction);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  const tooLong = draft.length > INSTRUCTION_MAX_CHARS;

  const save = useCallback(async () => {
    if (saving || tooLong) return;
    setSaving(true);
    try {
      const saved = await projectConfigApi.putInstruction(projectId, draft);
      setText(saved.instruction);
      setDraft(saved.instruction);
      setEditing(false);
      message.success(t("projects.instructionSaved"));
    } catch (err) {
      message.error(apiErrorMessage(err, t("projects.instructionTooLong"), t));
    } finally {
      setSaving(false);
    }
  }, [draft, projectId, saving, t, tooLong]);

  return (
    <section className={styles.panel} data-testid="rail-instruction">
      <div className={styles.header}>
        <span className={styles.title}>{t("projects.instructionTitle")}</span>
        {canManage && !editing ? (
          <Button
            type="text"
            size="small"
            aria-label={t("common.edit")}
            icon={<Pencil size={14} />}
            onClick={() => {
              setDraft(text);
              setEditing(true);
            }}
          />
        ) : null}
      </div>

      {loading ? (
        <div className={styles.centered}>
          <Spin size="small" />
        </div>
      ) : error ? (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={apiErrorMessage(
            error,
            t("projects.instructionTitle"),
            t,
          )}
        />
      ) : editing ? (
        <div className={styles.editor}>
          <Input.TextArea
            value={draft}
            rows={5}
            aria-label={t("projects.instructionTitle")}
            placeholder={t("projects.instructionPlaceholder")}
            onChange={(event) => setDraft(event.target.value)}
          />
          <div className={styles.editorFooter}>
            {tooLong ? (
              <Text type="danger" className={styles.tooLong}>
                {t("projects.instructionTooLong")}
              </Text>
            ) : (
              <Text type="secondary" className={styles.counter}>
                {`${draft.length}/${INSTRUCTION_MAX_CHARS}`}
              </Text>
            )}
            <span className={styles.actions}>
              <Button
                type="text"
                size="small"
                aria-label={t("common.cancel")}
                icon={<X size={14} />}
                onClick={() => {
                  setDraft(text);
                  setEditing(false);
                }}
              />
              <Button
                type="primary"
                size="small"
                loading={saving}
                disabled={tooLong}
                aria-label={t("common.save")}
                icon={<Check size={14} />}
                onClick={() => void save()}
              />
            </span>
          </div>
        </div>
      ) : text.trim() === "" ? (
        // S12：空串 = 清空（合法），展示占位而不是空控件。
        <Text type="secondary" data-testid="instruction-empty">
          {t("projects.instructionEmpty")}
        </Text>
      ) : (
        <Text className={styles.text}>{text}</Text>
      )}
    </section>
  );
}
