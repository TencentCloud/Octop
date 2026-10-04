import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import ProjectUnavailable from "../../workbuddy/ProjectUnavailable";
import WorkBuddyTopbar from "../../workbuddy/Topbar";
import { Cloud, Mail, Library, Layers, ArrowRight } from "lucide-react";
import {
  DEFERRED_FEATURES,
  type DeferredFeatureId,
} from "../../workbuddy/capabilities";

export default function DeferredFeature({
  feature,
}: {
  feature: DeferredFeatureId;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const entry = DEFERRED_FEATURES.find((item) => item.id === feature)!;
  if (feature === "projects")
    return <ProjectUnavailable onBack={() => navigate("/home")} />;
  const Icon =
    feature === "cloud"
      ? Cloud
      : feature === "agent-mail"
      ? Mail
      : feature === "space" || feature === "genie"
      ? Layers
      : Library;
  return (
    <section
      className="wb-deferred-page"
      aria-labelledby="deferred-title"
      data-capability="unsupported"
    >
      <WorkBuddyTopbar title="Octop" />
      <header className="wb-deferred-page__heading">
        <h1 id="deferred-title">{t(entry.labelKey)}</h1>
        <span className="wb-capability-badge">
          {t("workbuddy.notConnected")}
        </span>
      </header>
      <div className="wb-deferred-page__empty">
        <div className="wb-deferred-icon">
          <Icon size={32} aria-hidden="true" />
        </div>
        <h2>{t("workbuddy.capability.unsupported")}</h2>
        <p>{t(entry.descriptionKey)}</p>
        <p className="wb-deferred-note">{t("workbuddy.deferredNote")}</p>
        <button
          type="button"
          className="wb-primary-button"
          onClick={() => navigate("/home")}
        >
          {t("workbuddy.backHome")}
          <ArrowRight size={16} aria-hidden="true" />
        </button>
      </div>
    </section>
  );
}
