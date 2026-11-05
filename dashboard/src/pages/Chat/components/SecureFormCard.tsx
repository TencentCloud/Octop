import { useCallback, useEffect, useMemo, useState } from "react";
import { Checkbox, Input, Modal, Spin } from "antd";
import { FileCheck2, ShieldCheck, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { agentChatApi } from "../../../api/modules/agentChat";
import { parseApiError } from "../../../utils/apiError";
import type {
  SecureFormField,
  SecureFormLauncherRequest,
  SecureFormPendingRecord,
} from "../../../api/types/hitl";
import type {
  SecureFormSubmitOutcome,
  SecureFormSubmitPayload,
} from "../hooks/chatStore";
import styles from "./SecureFormCard.module.less";

export interface SecureFormCardProps {
  agentId: string;
  pendingId: string;
  /** Launcher display data from the pause args — never a destination fact. */
  request: SecureFormLauncherRequest;
  /**
   * ``expired`` marks a pause the server can no longer resume (evicted by a
   * newer form / TTL) — it renders the same terminal summary a 410 on open
   * produces, instead of a fresh-looking launcher.
   */
  status: "pending" | "approved" | "rejected" | "expired";
  /**
   * Submit or cancel through the dedicated SSE endpoint. `kind: "success"`
   * clears the drafts; error outcomes carry the Octop error code so the
   * modal can re-fetch the record, keep drafts, or go terminal.
   */
  onSubmit?: (
    payload: SecureFormSubmitPayload,
  ) => Promise<SecureFormSubmitOutcome>;
}

/** Terminal launcher states that no longer offer an Open button. */
type TerminalState = "expired" | "handled";

function isMaskedFieldType(type: SecureFormField["type"]): boolean {
  return type !== "text" && type !== "card_exp";
}

/**
 * Client mirror of the backend submit-time shapes. Returns an i18n error key
 * suffix or null. Trim is only used for the required check — the value itself
 * is stored byte-exact server-side.
 */
function fieldErrorKey(field: SecureFormField, value: string): string | null {
  if (!value.trim()) {
    return field.required ? "required" : null;
  }
  if (field.max_length != null && value.length > field.max_length) {
    return "maxLength";
  }
  switch (field.type) {
    case "otp":
      if (!/^\d{4,8}$/.test(value)) return "otp";
      break;
    case "card_cvv":
      if (!/^\d{3,4}$/.test(value)) return "cardCvv";
      break;
    case "card_number":
      if (!/^\d{12,19}$/.test(value.replace(/ /g, ""))) return "cardNumber";
      break;
    case "card_exp": {
      const match = /^(\d{2})\/(\d{2})$/.exec(value);
      if (!match) return "cardExp";
      const month = Number(match[1]);
      if (month < 1 || month > 12) return "cardExp";
      break;
    }
  }
  return null;
}

function SecureFormCard({
  agentId,
  pendingId,
  request,
  status,
  onSubmit,
}: SecureFormCardProps) {
  const { t } = useTranslation();
  const interactive = status === "pending" && Boolean(onSubmit);
  const [modalOpen, setModalOpen] = useState(false);
  const [terminal, setTerminal] = useState<TerminalState | null>(null);
  const [record, setRecord] = useState<SecureFormPendingRecord | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [submitAttempted, setSubmitAttempted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [bannerError, setBannerError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [replaceConfirmed, setReplaceConfirmed] = useState(false);
  const [saveToVault, setSaveToVault] = useState(false);

  // No `t` in the deps: the loader must stay referentially stable so the
  // open-effect fetches exactly once (i18next returns a fresh t per render
  // under test mocks). Localization happens at render time instead.
  const fetchRecord = useCallback(async (): Promise<
    "ok" | "expired" | "handled" | "error"
  > => {
    setLoading(true);
    setLoadError(null);
    try {
      const fetched = await agentChatApi.secureForm(agentId, pendingId);
      if (fetched.status && fetched.status !== "pending") {
        // Resolved elsewhere (other tab / racing submit): the endpoint still
        // returns 200 with the terminal status — never render an editable
        // form over a settled pause.
        setRecord(fetched);
        return "handled";
      }
      setRecord(fetched);
      return "ok";
    } catch (err) {
      if (parseApiError(err)?.code === "SECURE_FORM_PENDING_EXPIRED") {
        return "expired";
      }
      setLoadError(err);
      return "error";
    } finally {
      setLoading(false);
    }
  }, [agentId, pendingId]);

  useEffect(() => {
    if (!modalOpen) return;
    void fetchRecord().then((outcome) => {
      if (outcome === "expired" || outcome === "handled") {
        setValues({});
        setModalOpen(false);
        setTerminal(outcome);
      }
    });
  }, [modalOpen, fetchRecord]);

  const fields = useMemo(() => record?.fields ?? [], [record]);
  const routing = record?.routing;
  const existingVaultItem = Boolean(record?.existing_vault_item_id);
  const offersSaveToVault =
    routing?.kind === "env" && Boolean(routing.vault_meta);

  const storableTypeLabels = useMemo(() => {
    const storable = new Set(record?.vault_storable_field_ids ?? []);
    const types = new Set<string>();
    for (const field of fields) {
      if (storable.has(field.id)) types.add(field.type);
    }
    return [...types].map((type) => t(`chat.secureForm.fieldType.${type}`));
  }, [record, fields, t]);

  const valid = useMemo(() => {
    if (!record) return false;
    for (const field of fields) {
      if (fieldErrorKey(field, values[field.id] ?? "")) return false;
    }
    if (existingVaultItem && !replaceConfirmed) return false;
    return true;
  }, [record, fields, values, existingVaultItem, replaceConfirmed]);

  const openModal = () => {
    setBannerError(null);
    setFieldErrors({});
    setModalOpen(true);
  };

  const closeModal = () => {
    if (busy) return;
    setModalOpen(false);
  };

  const applyOutcome = async (outcome: SecureFormSubmitOutcome) => {
    if (outcome.kind === "success") {
      // Drop the values from component state and the DOM right away.
      setValues({});
      setFieldErrors({});
      setReplaceConfirmed(false);
      setModalOpen(false);
      return;
    }
    switch (outcome.code) {
      case "SECURE_FORM_PENDING_EXPIRED":
      case "SECURE_FORM_ALREADY_HANDLED":
        setValues({});
        setReplaceConfirmed(false);
        setModalOpen(false);
        setTerminal(
          outcome.code === "SECURE_FORM_PENDING_EXPIRED"
            ? "expired"
            : "handled",
        );
        return;
      case "VAULT_REPLACE_REQUIRED":
        // Collision facts re-derive on the refreshed record; drafts stay
        // unless the re-fetch itself turns terminal.
        await fetchRecord().then((refetch) => {
          if (refetch === "expired" || refetch === "handled") {
            setValues({});
            setReplaceConfirmed(false);
            setModalOpen(false);
            setTerminal(refetch);
          }
        });
        setBannerError(
          outcome.message
            ? `${t("chat.secureForm.replaceRequired")} — ${outcome.message}`
            : t("chat.secureForm.replaceRequired"),
        );
        return;
      case "SECURE_FORM_FIELD_INVALID": {
        const fieldId =
          outcome.details && typeof outcome.details.field === "string"
            ? outcome.details.field
            : null;
        if (fieldId) {
          setFieldErrors((prev) => ({ ...prev, [fieldId]: outcome.message }));
        } else {
          setBannerError(outcome.message);
        }
        return;
      }
      default:
        // WRITE_FAILED / SLOT_INVALID / CAP_EXCEEDED — banner, drafts kept.
        setBannerError(outcome.message);
        return;
    }
  };

  const submit = async () => {
    if (!onSubmit || busy) return;
    setSubmitAttempted(true);
    if (!valid) return;
    setBusy(true);
    setBannerError(null);
    setFieldErrors({});
    const submitted: Record<string, string> = {};
    for (const field of fields) {
      const value = values[field.id] ?? "";
      if (value.trim()) submitted[field.id] = value;
    }
    const outcome = await onSubmit({
      action: "submit",
      values: submitted,
      ...(existingVaultItem && replaceConfirmed
        ? { replaceConfirmed: true }
        : {}),
      ...(offersSaveToVault && saveToVault ? { saveToVault: true } : {}),
    });
    setBusy(false);
    await applyOutcome(outcome);
  };

  const cancel = async () => {
    if (!onSubmit || busy) return;
    setBusy(true);
    const outcome = await onSubmit({ action: "cancel" });
    setBusy(false);
    if (outcome.kind === "success") {
      setValues({});
      setModalOpen(false);
      return;
    }
    await applyOutcome(outcome);
  };

  const title = request.title?.trim() || t("chat.secureForm.title");

  const terminalState: TerminalState | null =
    terminal ?? (status === "expired" ? "expired" : null);
  if (terminalState) {
    return (
      <details className={styles.completedCard}>
        <summary className={styles.completedSummary}>
          <span className={styles.completedStatus}>
            {terminalState === "expired"
              ? t("chat.secureForm.expiredSummary")
              : t("chat.secureForm.handledSummary")}
          </span>
          <span className={styles.expandHint}>{t("chat.ask.expand")}</span>
        </summary>
        <div className={styles.completedBody}>
          <div className={styles.completedPrompt}>{request.prompt}</div>
        </div>
      </details>
    );
  }

  if (!interactive) {
    return (
      <details className={styles.completedCard}>
        <summary className={styles.completedSummary}>
          <span className={styles.completedStatus}>
            {status === "approved"
              ? t("chat.secureForm.filledSummary", {
                  count: request.fieldCount,
                })
              : t("chat.secureForm.dismissedSummary", {
                  count: request.fieldCount,
                })}
          </span>
          <span className={styles.expandHint}>{t("chat.ask.expand")}</span>
        </summary>
        <div className={styles.completedBody}>
          <div className={styles.completedPrompt}>{request.prompt}</div>
        </div>
      </details>
    );
  }

  return (
    <div className={styles.card}>
      <div className={styles.header}>
        <span className={styles.iconBadge}>
          <ShieldCheck size={12} />
        </span>
        <span className={styles.title}>{title}</span>
        <button
          type="button"
          className={styles.closeButton}
          aria-label={t("chat.secureForm.cancel")}
          disabled={busy}
          onClick={() => void cancel()}
        >
          <X size={14} />
        </button>
      </div>
      <div className={styles.subtitle}>{t("chat.secureForm.subtitle")}</div>
      {request.prompt ? (
        <div className={styles.prompt}>{request.prompt}</div>
      ) : null}
      <div className={styles.footer}>
        <button
          type="button"
          className={styles.submitButton}
          disabled={busy}
          onClick={openModal}
        >
          <FileCheck2 size={13} className={styles.openIcon} />
          {t("chat.secureForm.open")}
        </button>
        <span className={styles.hint}>
          <ShieldCheck size={12} className={styles.hintIcon} />
          {t("chat.secureForm.secureHint")}
        </span>
      </div>

      <Modal
        open={modalOpen}
        title={t("chat.secureForm.modalTitle")}
        onCancel={closeModal}
        width={520}
        destroyOnClose
        footer={
          <div className={styles.modalFooter}>
            <button
              type="button"
              className={styles.secondaryButton}
              disabled={busy}
              onClick={() => void cancel()}
            >
              {t("chat.secureForm.cancel")}
            </button>
            <button
              type="button"
              className={styles.submitButton}
              disabled={!valid || busy}
              onClick={() => void submit()}
            >
              {t("chat.secureForm.submit")}
            </button>
          </div>
        }
      >
        {loading ? (
          <div className={styles.loading}>
            <Spin size="small" />
          </div>
        ) : loadError ? (
          <div className={styles.error} role="alert">
            {parseApiError(loadError)?.message ||
              (loadError instanceof Error && loadError.message.trim()
                ? loadError.message
                : t("chat.secureForm.loadFailed"))}
          </div>
        ) : record ? (
          <div className={styles.formBody}>
            <div
              className={styles.trustBanner}
              data-testid="secure-form-banner"
            >
              <div className={styles.bannerTitle}>
                <ShieldCheck size={13} className={styles.bannerIcon} />
                {t("chat.secureForm.banner.title")}
              </div>
              {routing?.kind === "env" ? (
                <div className={styles.bannerLine}>
                  {t("chat.secureForm.banner.envPersist")}
                </div>
              ) : null}
              {routing?.kind === "env" && routing.slots
                ? Object.entries(routing.slots).map(([fieldId, slot]) => (
                    <div key={fieldId} className={styles.slotRow}>
                      <code className={styles.slotName} title={slot}>
                        {slot}
                      </code>
                      {(record.existing_slot_names ?? []).includes(slot) ? (
                        <span className={styles.replaceTag}>
                          {t("chat.secureForm.banner.replacesSlot")}
                        </span>
                      ) : null}
                    </div>
                  ))
                : null}
              {routing?.vault_meta ? (
                <div className={styles.bannerLine}>
                  {t("chat.secureForm.banner.vaultItem", {
                    itemType: t(
                      `chat.secureForm.itemType.${routing.vault_meta.item_type}`,
                    ),
                  })}
                </div>
              ) : null}
              {routing?.vault_meta?.origin ? (
                <div className={styles.bannerLine}>
                  <code className={styles.slotName}>
                    {routing.vault_meta.origin}
                  </code>
                  <span className={styles.unverifiedTag}>
                    {t("chat.secureForm.banner.originUnverified")}
                  </span>
                </div>
              ) : null}
              {offersSaveToVault ? (
                <div className={styles.bannerLine}>
                  {t("chat.secureForm.banner.saveScope", {
                    types: storableTypeLabels.join(", "),
                  })}
                </div>
              ) : null}
            </div>

            {record.title || record.prompt ? (
              <div className={styles.modelCopy}>
                {record.title ? (
                  <div className={styles.modelTitle}>{record.title}</div>
                ) : null}
                {record.prompt ? (
                  <div className={styles.modelPrompt}>{record.prompt}</div>
                ) : null}
              </div>
            ) : null}

            {fields.map((field) => {
              const clientError = fieldErrorKey(field, values[field.id] ?? "");
              const showError =
                Boolean(clientError) &&
                (submitAttempted || Boolean(values[field.id]?.trim()));
              const errorText = fieldErrors[field.id]
                ? fieldErrors[field.id]
                : showError && clientError
                ? t(`chat.secureForm.errors.${clientError}`)
                : null;
              const masked = isMaskedFieldType(field.type);
              const ariaLabel = masked
                ? t("chat.secureForm.maskedFieldAria", { label: field.label })
                : field.label;
              return (
                <div key={field.id} className={styles.fieldRow}>
                  <label
                    className={styles.fieldLabel}
                    htmlFor={`secure-form-${field.id}`}
                  >
                    {field.label}
                    {field.required ? (
                      <span className={styles.requiredMark}> *</span>
                    ) : null}
                  </label>
                  {masked ? (
                    <Input.Password
                      id={`secure-form-${field.id}`}
                      className={styles.input}
                      value={values[field.id] ?? ""}
                      autoComplete="new-password"
                      aria-label={ariaLabel}
                      disabled={busy}
                      onChange={(e) =>
                        setValues((prev) => ({
                          ...prev,
                          [field.id]: e.target.value,
                        }))
                      }
                    />
                  ) : (
                    <Input
                      id={`secure-form-${field.id}`}
                      className={styles.input}
                      value={values[field.id] ?? ""}
                      placeholder={
                        field.type === "card_exp"
                          ? t("chat.secureForm.cardExpPlaceholder")
                          : undefined
                      }
                      aria-label={ariaLabel}
                      disabled={busy}
                      onChange={(e) =>
                        setValues((prev) => ({
                          ...prev,
                          [field.id]: e.target.value,
                        }))
                      }
                    />
                  )}
                  {errorText ? (
                    <div className={styles.fieldError} role="alert">
                      {errorText}
                    </div>
                  ) : null}
                </div>
              );
            })}

            {existingVaultItem ? (
              <Checkbox
                className={styles.confirmCheckbox}
                checked={replaceConfirmed}
                disabled={busy}
                onChange={(e) => setReplaceConfirmed(e.target.checked)}
              >
                {t("chat.secureForm.replaceConfirm")}
              </Checkbox>
            ) : null}
            {offersSaveToVault ? (
              <Checkbox
                className={styles.confirmCheckbox}
                checked={saveToVault}
                disabled={busy}
                onChange={(e) => setSaveToVault(e.target.checked)}
              >
                {t("chat.secureForm.saveToVault")}
              </Checkbox>
            ) : null}
            {bannerError ? (
              <div className={styles.error} role="alert">
                {bannerError}
              </div>
            ) : null}
          </div>
        ) : null}
      </Modal>
    </div>
  );
}

export default SecureFormCard;
