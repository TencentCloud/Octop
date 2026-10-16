import { useState } from "react";
import { Input } from "antd";
import { Lock, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { SecretRequest } from "../../../api/types/hitl";
import styles from "./SecretFileCard.module.less";

export interface SecretFileCardProps {
  request: SecretRequest;
  status: "pending" | "approved" | "rejected";
  /**
   * Submit the typed secret. Resolves to `null` on success (the card clears
   * the input and the turn resumes) or an error message to show for retry.
   */
  onSubmit?: (content: string) => Promise<string | null>;
  /** Dismiss without writing anything. */
  onCancel?: () => void;
}

/**
 * Secure credential fill-in card (request_secret_file).
 *
 * The typed value goes straight to the dedicated API — never into chat
 * history, tool arguments, or the model context. `password` masking is UI
 * only; the transport guarantee comes from the submit path, not the field.
 */
function SecretFileCard({
  request,
  status,
  onSubmit,
  onCancel,
}: SecretFileCardProps) {
  const { t } = useTranslation();
  const interactive = status === "pending" && Boolean(onSubmit);
  const [value, setValue] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const displayPath = request.meta.path || request.path;
  const unsupported = request.meta.unsupported === true;
  const blocked = unsupported || request.meta.invalid === true;

  if (!interactive) {
    return (
      <div className={`${styles.card} ${styles.completedCard}`}>
        <span className={styles.completedStatus}>
          {status === "approved"
            ? t("chat.secretCard.filledSummary", { path: displayPath })
            : t("chat.secretCard.cancelledSummary")}
        </span>
      </div>
    );
  }

  const submit = async () => {
    const content = value;
    if (!content.trim() || submitting || !onSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      const failure = await onSubmit(content);
      if (failure === null) {
        // Accepted by the server — never keep the secret around.
        setValue("");
      } else {
        setError(failure);
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className={styles.card}>
      <div className={styles.titleRow}>
        <span className={styles.title}>
          <Lock size={14} aria-hidden />
          {request.title || t("chat.secretCard.title")}
        </span>
        {onCancel ? (
          <button
            type="button"
            className={styles.closeButton}
            onClick={onCancel}
            title={t("chat.secretCard.cancel")}
            aria-label={t("chat.secretCard.cancel")}
          >
            <X size={15} />
          </button>
        ) : null}
      </div>

      {request.prompt ? (
        <p className={styles.prompt}>{request.prompt}</p>
      ) : null}

      <div className={styles.pathRow}>
        <span className={styles.pathLabel}>
          {t("chat.secretCard.pathLabel")}
        </span>
        <span className={styles.pathValue}>{displayPath}</span>
      </div>

      {blocked ? (
        <div className={styles.invalidWarning}>
          {unsupported
            ? t("chat.secretCard.unsupported")
            : t("chat.secretCard.invalidPath")}
        </div>
      ) : request.meta.exists ? (
        <div className={styles.replaceWarning}>
          {t("chat.secretCard.replaceWarning")}
        </div>
      ) : null}

      {!blocked ? (
        <Input.Password
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder={t("chat.secretCard.placeholder")}
          autoComplete="off"
          disabled={submitting}
          onPressEnter={() => void submit()}
        />
      ) : null}

      <p className={styles.note}>{t("chat.secretCard.note")}</p>
      {error ? <p className={styles.errorText}>{error}</p> : null}

      <div className={styles.actions}>
        {!blocked ? (
          <button
            type="button"
            className={`${styles.actionButton} ${styles.primaryAction}`}
            disabled={!value.trim() || submitting}
            onClick={() => void submit()}
          >
            {submitting
              ? t("chat.secretCard.submitting")
              : t("chat.secretCard.submit")}
          </button>
        ) : null}
        {onCancel ? (
          <button
            type="button"
            className={styles.actionButton}
            disabled={submitting}
            onClick={onCancel}
          >
            {t("chat.secretCard.cancel")}
          </button>
        ) : null}
      </div>
    </div>
  );
}

export default SecretFileCard;
