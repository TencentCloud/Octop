import { useTranslation } from "react-i18next";
import { CheckCircle } from "lucide-react";
import { ExpertIcon } from "../pages/Experts/components/iconForName";

export default function ExpertTemplate({
  label,
  description,
  iconUrl,
  iconName,
  installed,
  onCreate,
}: {
  label: string;
  description: string;
  iconUrl?: string | null;
  iconName?: string | null;
  installed: boolean;
  onCreate: () => void;
}) {
  const { t } = useTranslation();
  return (
    <div
      className="ec-expert-card"
      role="button"
      tabIndex={0}
      aria-label={label}
      onClick={onCreate}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onCreate();
        }
      }}
      data-entity-kind="expert-template"
    >
      <div className="ec-card-main">
        <div className="ec-card-head">
          <div className="ec-card-avatar-sq">
            <ExpertIcon iconUrl={iconUrl} iconName={iconName} size={36} />
          </div>
          <div className="ec-card-body">
            <div className="ec-card-title-row">
              <span className="ec-card-role">{label}</span>
            </div>
          </div>
        </div>
        <div className="ec-card-desc">{description}</div>
      </div>
      <div className="ec-card-footer">
        <span className="ec-card-usage">
          {installed ? (
            <>
              <CheckCircle size={12} aria-hidden="true" />{" "}
              {t("experts.installedBadge")}
            </>
          ) : (
            t("experts.createFromTemplate")
          )}
        </span>
      </div>
    </div>
  );
}
