import { Suspense, useEffect, useRef, useState, type ReactNode } from "react";
import { ArrowLeft } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  Route,
  Routes,
  useLocation,
  useNavigate,
  type Location,
} from "react-router-dom";
import type { OctopUser } from "../api/modules/auth";
import { useAgent } from "../context/AgentContext";
import AgentSelector from "../components/AgentSelector";
import ForbiddenPage from "../components/ForbiddenPage";
import PageLoading from "../components/PageLoading";
import RetainedSurface from "./RetainedSurface";
import { EmbeddedPageContext } from "../layouts/PageShell";
import {
  AgentPanels,
  allowedSettingsSections,
  type SettingsGroup,
} from "./settingsRegistry";
const groups: SettingsGroup[] = [
  "general",
  "features",
  "security",
  "management",
  "about",
];
export default function SettingsFrame({
  children,
  user,
  onCustomizeNav,
}: {
  children: ReactNode;
  user: OctopUser | null;
  onCustomizeNav?: () => void;
}) {
  const { t } = useTranslation();
  const location = useLocation();
  const navigate = useNavigate();
  const { activeAgentId } = useAgent();
  const sections = allowedSettingsSections(user);
  const sectionId = location.pathname.split("/")[2] ?? "general";
  const section = sections.find((item) => item.id === sectionId);
  const [visited, setVisited] = useState<string[]>([sectionId]);
  const snapshots = useRef<Record<string, Location>>({});
  snapshots.current[sectionId] = location;
  useEffect(() => {
    setVisited((prev) =>
      prev.includes(sectionId) ? prev : [...prev, sectionId],
    );
  }, [sectionId]);
  const select = (id: string) =>
    navigate(snapshots.current[id] ?? `/settings/${id}`, {
      state: location.state,
    });
  const showMenu = sectionId === "";
  return (
    <div
      className="settings-modal wb-settings-frame wb-settings-center"
      data-settings-panel={sectionId}
      data-settings-mobile-view={showMenu ? "categories" : "content"}
    >
      <aside className="settings-modal__nav">
        <nav
          className="settings-navigation"
          aria-label={t("workbuddy.settings.title")}
        >
          {groups.map((group) => {
            const items = sections.filter((item) => item.group === group);
            return items.length ? (
              <div key={group} className="wb-settings-group">
                <h3>{t(`workbuddy.settings.groups.${group}`)}</h3>
                {items.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    aria-pressed={sectionId === item.id}
                    className={`settings-navigation__item${
                      sectionId === item.id
                        ? " settings-navigation__item--active"
                        : ""
                    }`}
                    onClick={() => select(item.id)}
                  >
                    <span className="settings-navigation__label">
                      {t(item.label)}
                    </span>
                  </button>
                ))}
              </div>
            ) : null;
          })}
        </nav>
      </aside>
      <div className="settings-modal__content">
        <header className="settings-modal__header">
          <button
            type="button"
            className="wb-settings-back"
            aria-label={t("common.back")}
            onClick={() => navigate("/settings/", { state: location.state })}
          >
            <ArrowLeft size={18} />
          </button>
          <h2 className="settings-modal__title">
            {section ? t(section.label) : t("workbuddy.settings.title")}
          </h2>
        </header>
        <div className="settings-modal__panel wb-settings-frame__content">
          {!section && !showMenu ? <ForbiddenPage /> : null}
          <div
            hidden={
              !section ||
              !["general", "account", "appearance"].includes(sectionId)
            }
            className="wb-settings-preferences"
          >
            {children}
            {sectionId === "general" && onCustomizeNav && (
              <button
                className="settings-navigation__item"
                type="button"
                onClick={onCustomizeNav}
              >
                {t("nav.customize")}
              </button>
            )}
          </div>
          <EmbeddedPageContext.Provider value={true}>
            {visited.map((id) => {
              const item = sections.find((entry) => entry.id === id);
              if (!item || (!item.Component && !item.agentPanel)) return null;
              const Component = item.Component;
              return (
                <div
                  key={id}
                  hidden={id !== sectionId}
                  className="wb-settings-panel"
                >
                  {item.agentPanel && (
                    <div className="wb-settings-agent">
                      <span>{t("workbuddy.settings.scope")}</span>
                      <AgentSelector showLabel={false} />
                    </div>
                  )}
                  <div
                    key={item.agentScoped ? activeAgentId : id}
                    className="wb-settings-panel-body"
                  >
                    <RetainedSurface active={id === sectionId}>
                      <Routes location={snapshots.current[id]}>
                        <Route
                          path="/settings/*"
                          element={
                            <Suspense fallback={<PageLoading />}>
                              {Component ? (
                                <Component />
                              ) : (
                                <AgentPanels panel={item.agentPanel!} />
                              )}
                            </Suspense>
                          }
                        />
                      </Routes>
                    </RetainedSurface>
                  </div>
                </div>
              );
            })}
          </EmbeddedPageContext.Provider>
        </div>
      </div>
    </div>
  );
}
