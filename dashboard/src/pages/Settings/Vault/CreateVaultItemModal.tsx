import { useEffect, useMemo, useState, type ChangeEvent } from "react";
import { useTranslation } from "react-i18next";
import { Input, Modal } from "antd";
import { message } from "@/utils/antdMessage";
import { apiErrorMessage } from "../../../utils/apiError";
import {
  vaultApi,
  type VaultFieldInputType,
  type VaultItemType,
} from "../../../api/modules/vault";
import styles from "./Vault.module.less";

/** Mirrors SECURE_FORM_MAX_VAULT_TITLE / SECURE_FORM_MAX_FIELD_LENGTH. */
const MAX_TITLE = 120;
const MAX_FIELD_LENGTH = 256;

interface CreateFieldSpec {
  id: string;
  /** Label key suffix under ``vault.create.fields``. */
  labelKey: string;
  type: VaultFieldInputType;
  masked: boolean;
}

/**
 * Typed fields per item type — mirrors the backend pairing allow-list
 * (login: text + password, card: number + expiry, contact: one text value;
 * the envelope stores a single value per field type).
 */
const CREATE_FIELDS: Record<VaultItemType, CreateFieldSpec[]> = {
  login: [
    { id: "username", labelKey: "username", type: "text", masked: false },
    { id: "password", labelKey: "password", type: "password", masked: true },
  ],
  card: [
    {
      id: "card_number",
      labelKey: "card_number",
      type: "card_number",
      masked: true,
    },
    { id: "card_exp", labelKey: "card_exp", type: "card_exp", masked: false },
  ],
  contact: [{ id: "text", labelKey: "text", type: "text", masked: false }],
};

/** Client mirror of the backend per-type value shapes. */
function valueErrorKey(
  type: VaultFieldInputType,
  value: string,
): string | null {
  if (!value.trim()) return "required";
  if (value.length > MAX_FIELD_LENGTH) return "maxLength";
  switch (type) {
    case "card_number":
      if (!/^\d{12,19}$/.test(value.replace(/ /g, ""))) return "cardNumber";
      break;
    case "card_exp": {
      const match = /^(\d{2})\/(\d{2})$/.exec(value);
      if (!match || Number(match[1]) < 1 || Number(match[1]) > 12) {
        return "cardExp";
      }
      break;
    }
  }
  return null;
}

/** Client mirror of the backend origin grammar (scheme://host[:port]). */
function originErrorKey(origin: string): string | null {
  const trimmed = origin.trim();
  if (!trimmed) return null;
  try {
    const url = new URL(trimmed);
    if (url.protocol !== "http:" && url.protocol !== "https:") return "origin";
    if (url.username || url.password || url.search || url.hash) return "origin";
    if (url.pathname !== "" && url.pathname !== "/") return "origin";
    if (!url.hostname || url.hostname.endsWith(".")) return "origin";
    return null;
  } catch {
    return "origin";
  }
}

interface CreateVaultItemModalProps {
  /** The item type to create; ``null`` keeps the modal closed. */
  itemType: VaultItemType | null;
  onClose: () => void;
  onCreated: () => void | Promise<void>;
}

/** Manual vault-item creation with typed, per-item-type fields. */
export default function CreateVaultItemModal({
  itemType,
  onClose,
  onCreated,
}: CreateVaultItemModalProps) {
  const { t } = useTranslation();
  const [title, setTitle] = useState("");
  const [origin, setOrigin] = useState("");
  const [values, setValues] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [submitAttempted, setSubmitAttempted] = useState(false);
  const [bannerError, setBannerError] = useState<string | null>(null);

  const open = itemType !== null;
  const fields = itemType !== null ? CREATE_FIELDS[itemType] : [];

  // Fresh drafts on every open, including switching the picked type while
  // open (the dropdown stays available behind the modal on desktop).
  useEffect(() => {
    if (itemType !== null) {
      setTitle("");
      setOrigin("");
      setValues({});
      setSubmitAttempted(false);
      setBannerError(null);
    }
  }, [itemType]);

  const titleError = useMemo(() => {
    const trimmed = title.trim();
    if (!trimmed) return "titleRequired";
    if (trimmed.length > MAX_TITLE) return "titleTooLong";
    return null;
  }, [title]);
  const originError = useMemo(() => originErrorKey(origin), [origin]);
  const valid =
    titleError === null &&
    originError === null &&
    fields.every(
      (field) => valueErrorKey(field.type, values[field.id] ?? "") === null,
    );

  const cancel = () => {
    if (busy) return;
    onClose();
  };

  const submit = async () => {
    if (itemType === null || busy) return;
    setSubmitAttempted(true);
    setBannerError(null);
    if (!valid) return;
    setBusy(true);
    try {
      const trimmedTitle = title.trim();
      await vaultApi.create({
        item_type: itemType,
        title: trimmedTitle,
        origin: origin.trim() || undefined,
        fields: fields.map((field) => ({
          id: field.id,
          type: field.type,
          value: values[field.id] ?? "",
        })),
      });
      message.success(t("vault.created", { title: trimmedTitle }));
      onClose();
      await onCreated();
    } catch (err) {
      // Drafts stay so the user can retry; the banner carries the localized
      // error (e.g. VAULT_REPLACE_REQUIRED on a title collision).
      setBannerError(apiErrorMessage(err, t("vault.create.failed"), t));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      open={open}
      title={t("vault.create.title", {
        type: t(`vault.itemType.${itemType ?? "login"}`),
      })}
      onCancel={cancel}
      onOk={() => void submit()}
      okText={t("vault.create.submit")}
      cancelText={t("vault.create.cancel")}
      confirmLoading={busy}
      width={480}
      destroyOnClose
    >
      <div className={styles.formBody}>
        <div className={styles.fieldRow}>
          <label className={styles.fieldLabel} htmlFor="vault-create-title">
            {t("vault.create.fields.title")}
          </label>
          <Input
            id="vault-create-title"
            value={title}
            disabled={busy}
            onChange={(e) => setTitle(e.target.value)}
          />
          {submitAttempted && titleError !== null ? (
            <div className={styles.fieldError} role="alert">
              {t(`vault.create.errors.${titleError}`)}
            </div>
          ) : null}
        </div>

        <div className={styles.fieldRow}>
          <label className={styles.fieldLabel} htmlFor="vault-create-origin">
            {t("vault.create.fields.origin")}
          </label>
          <Input
            id="vault-create-origin"
            placeholder="https://example.com"
            value={origin}
            disabled={busy}
            onChange={(e) => setOrigin(e.target.value)}
          />
          {submitAttempted && originError !== null ? (
            <div className={styles.fieldError} role="alert">
              {t(`vault.create.errors.${originError}`)}
            </div>
          ) : null}
        </div>

        {fields.map((field) => {
          const errorKey = valueErrorKey(field.type, values[field.id] ?? "");
          const showError =
            submitAttempted || Boolean((values[field.id] ?? "").trim());
          const label = t(`vault.create.fields.${field.labelKey}`);
          const inputProps = {
            id: `vault-create-${field.id}`,
            value: values[field.id] ?? "",
            disabled: busy,
            "aria-label": label,
            onChange: (e: ChangeEvent<HTMLInputElement>) =>
              setValues((prev) => ({ ...prev, [field.id]: e.target.value })),
          };
          return (
            <div className={styles.fieldRow} key={field.id}>
              <label className={styles.fieldLabel} htmlFor={inputProps.id}>
                {label}
              </label>
              {field.masked ? (
                <Input.Password {...inputProps} autoComplete="new-password" />
              ) : (
                <Input
                  {...inputProps}
                  placeholder={
                    field.type === "card_exp"
                      ? t("vault.create.cardExpPlaceholder")
                      : undefined
                  }
                />
              )}
              {showError && errorKey !== null ? (
                <div className={styles.fieldError} role="alert">
                  {t(`vault.create.errors.${errorKey}`)}
                </div>
              ) : null}
            </div>
          );
        })}

        {bannerError ? (
          <div className={styles.fieldError} role="alert">
            {bannerError}
          </div>
        ) : null}
      </div>
    </Modal>
  );
}
