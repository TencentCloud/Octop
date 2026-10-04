import { Button, Input, Tooltip } from "antd";
import { FolderKanban, Plus } from "lucide-react";
import { useTranslation } from "react-i18next";
import WorkBuddyTopbar from "./Topbar";

/** Source project-list-page landing structure. No projects are created from threads. */
export default function ProjectUnavailable({ onBack }: { onBack: () => void }) {
  const { t } = useTranslation();
  return (
    <section
      className="workbuddy-collab wb-project-unavailable"
      data-capability="unsupported"
      aria-labelledby="project-landing-title"
    >
      <WorkBuddyTopbar title="Octop" />
      <div className="landing">
        <header className="landing-header">
          <div className="landing-header__content">
            <div className="landing-title-wrap">
              <h1 className="landing-title" id="project-landing-title">
                {t("workbuddy.projects")}{" "}
                <span className="wb-capability-badge">
                  {t("workbuddy.notConnected")}
                </span>
              </h1>
              <p className="landing-subtitle">
                {t("workbuddy.projectSubtitle")}
              </p>
            </div>
            <Tooltip title={t("workbuddy.capability.unsupported")}>
              <span>
                <Button
                  className="landing-new-btn"
                  icon={<Plus size={14} />}
                  disabled
                >
                  {t("workbuddy.newProject")}
                </Button>
              </span>
            </Tooltip>
          </div>
          <img
            className="landing-hero"
            src="/workbuddy/landing-hero-B6659kdy.png"
            alt=""
          />
        </header>
        <div className="landing-main">
          <div className="project-grid">
            <div className="project-grid__section-row">
              <h2 className="project-grid__section-title">
                {t("workbuddy.projects")}
              </h2>
              <Input
                className="project-grid__search"
                type="search"
                placeholder={t("workbuddy.projectSearch")}
                aria-label={t("workbuddy.projectSearch")}
                disabled
              />
            </div>
            <div className="project-grid__body">
              <div className="project-grid__empty">
                <span className="project-grid__empty-icon">
                  <FolderKanban size={24} aria-hidden="true" />
                </span>
                <div className="project-grid__empty-text-group">
                  <h2 className="project-grid__empty-title">
                    {t("workbuddy.capability.unsupported")}
                  </h2>
                  <p className="project-grid__empty-subtitle">
                    {t("workbuddy.projectsDescription")}
                  </p>
                  <p className="project-grid__empty-text">
                    {t("workbuddy.deferredNote")}
                  </p>
                </div>
                <Button onClick={onBack}>{t("workbuddy.backHome")}</Button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
