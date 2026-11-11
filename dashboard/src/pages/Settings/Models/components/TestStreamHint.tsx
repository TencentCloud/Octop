import { useTranslation } from "react-i18next";

/** Reminder that provider "test" is non-streaming. */
export function TestStreamHint() {
  const { t } = useTranslation();
  return (
    <p
      style={{
        margin: "8px 0 0",
        color: "var(--fn-text-secondary)",
        fontSize: 12,
      }}
    >
      {t("models.testStreamHint")}
    </p>
  );
}
