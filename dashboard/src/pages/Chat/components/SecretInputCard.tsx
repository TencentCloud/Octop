import { useState } from "react";
import { Input } from "antd";
import { KeyRound, ShieldCheck } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { SecretInputRequest } from "../../../api/types/hitl";
import styles from "./SecretInputCard.module.less";

export interface SecretInputCardProps {
  request: SecretInputRequest;
  status: "pending" | "approved" | "rejected";
  /**
   * Submit the masked value. Resolves `null` on success — the card clears the
   * input immediately; a non-null string is a displayable error and the draft
   * is kept so the user can retry without retyping.
   */
  onSubmit?: (value: string) => Promise<string | null>;
  /** Dismiss the card without storing anything. */
  onCancel?: () => void;
}

function SecretInputCard({
  request,
  status,
  onSubmit,
  onCancel,
}: SecretInputCardProps) {
  const { t } = useTranslation();
  const interactive = status === "pending" && Boolean(onSubmit);
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const title = request.title?.trim() || t("chat.secretInput.title");
  const trimmed = value.trim();
  // Models often echo the slot as the title; showing both reads as a glitch.
  const showTitle = title.toLowerCase() !== request.slot.toLowerCase();

  if (!interactive) {
    return (
      <details className={styles.completedCard}>
        <summary className={styles.completedSummary}>
          <span className={styles.completedStatus}>
            {status === "approved"
              ? t("chat.secretInput.filledSummary", { slot: request.slot })
              : t("chat.secretInput.dismissedSummary", { slot: request.slot })}
          </span>
          <span className={styles.expandHint}>{t("chat.ask.expand")}</span>
        </summary>
        <div className={styles.completedBody}>
          <div className={styles.slotRow}>
            <span className={styles.slotLabel}>
              {t("chat.secretInput.slotLabel")}
            </span>
            <code className={styles.slotName}>{request.slot}</code>
          </div>
          {request.prompt ? (
            <div className={styles.completedPrompt}>{request.prompt}</div>
          ) : null}
        </div>
      </details>
    );
  }

  const submit = async () => {
    if (!onSubmit || !trimmed || busy) return;
    setBusy(true);
    setError(null);
    const failure = await onSubmit(value);
    setBusy(false);
    if (failure === null) {
      // Success: drop the secret from component state and the DOM right away.
      setValue("");
      return;
    }
    setError(failure);
  };

  return (
    <div className={styles.card}>
      <div className={styles.header}>
        <span className={styles.iconBadge}>
          <KeyRound size={12} />
        </span>
        {showTitle ? <span className={styles.title}>{title}</span> : null}
        <code className={styles.slotName} title={request.slot}>
          {request.slot}
        </code>
      </div>
      {request.prompt ? (
        <div className={styles.prompt}>{request.prompt}</div>
      ) : null}
      <div className={styles.inputRow}>
        <Input.Password
          className={styles.input}
          value={value}
          placeholder={t("chat.secretInput.placeholder")}
          autoComplete="new-password"
          disabled={busy}
          onChange={(e) => setValue(e.target.value)}
          onPressEnter={submit}
        />
        <button
          type="button"
          className={styles.submitButton}
          disabled={!trimmed || busy}
          onClick={submit}
        >
          {t("chat.secretInput.submit")}
        </button>
      </div>
      {error ? (
        <div className={styles.error} role="alert">
          {error}
        </div>
      ) : null}
      <div className={styles.footer}>
        <span className={styles.hint}>
          <ShieldCheck size={12} className={styles.hintIcon} />
          {t("chat.secretInput.secureHint")}
        </span>
        <button
          type="button"
          className={styles.cancelButton}
          disabled={busy}
          onClick={onCancel}
        >
          {t("chat.secretInput.cancel")}
        </button>
      </div>
    </div>
  );
}

export default SecretInputCard;
