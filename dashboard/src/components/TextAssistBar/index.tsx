import { useCallback, useState } from "react";
import { Button } from "antd";
import { Wand2 } from "lucide-react";
import { useTranslation } from "react-i18next";

import {
  textAssistApi,
  type TextAssistKind,
} from "../../api/modules/textAssist";
import { apiErrorMessage } from "../../utils/apiError";
import { message } from "@/utils/antdMessage";
import styles from "./TextAssistBar.module.less";

export type TextAssistBarProps = {
  kind: TextAssistKind;
  /** Current field draft (may be empty → generate from name). */
  getText: () => string;
  /** Entity name used as generation context (required by backend). */
  getName: () => string;
  onApply: (text: string) => void;
  disabled?: boolean;
  className?: string;
};

export function TextAssistBar({
  kind,
  getText,
  getName,
  onApply,
  disabled = false,
  className,
}: TextAssistBarProps) {
  const { t, i18n } = useTranslation();
  const [loading, setLoading] = useState(false);

  const handleClick = useCallback(async () => {
    if (loading || disabled) return;
    const name = (getName() || "").trim();
    if (!name) {
      message.warning(t("textAssist.nameRequired"));
      return;
    }
    const text = (getText() || "").trim();
    setLoading(true);
    try {
      const result = await textAssistApi.assist({
        kind,
        text,
        context: { name },
        locale: i18n.language?.startsWith("zh") ? "zh" : "en",
      });
      const next = (result.text || "").trim();
      if (!next) {
        message.error(t("textAssist.emptyResult"));
        return;
      }
      onApply(next);
    } catch (err: unknown) {
      message.error(apiErrorMessage(err, t("textAssist.failed"), t));
    } finally {
      setLoading(false);
    }
  }, [disabled, getName, getText, i18n.language, kind, loading, onApply, t]);

  return (
    <div className={[styles.bar, className].filter(Boolean).join(" ")}>
      <span className={styles.hint}>{t("textAssist.hint")}</span>
      <Button
        type="link"
        size="small"
        className={styles.button}
        icon={<Wand2 size={14} />}
        loading={loading}
        disabled={disabled || loading}
        onClick={() => void handleClick()}
      >
        {t("textAssist.action")}
      </Button>
    </div>
  );
}

export default TextAssistBar;
