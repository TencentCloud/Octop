import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Pin, PanelLeftOpen, X } from "lucide-react";
import type { OctopAgent } from "../context/AgentContext";
import { ExpertIcon } from "../pages/Experts/components/iconForName";
import SharedExpertHint from "../pages/Chat/components/SharedExpertHint";
import RemoteExpertHint from "../pages/Chat/components/RemoteExpertHint";
import TeamChatBadge from "../pages/Chat/components/TeamChatBadge";
import { useIsMobile } from "../hooks/useIsMobile";
import { useAssistantPanelPreference } from "./preferences";

export default function Assistants({
  agents,
  activeAgentId,
  onSelect,
}: {
  agents: OctopAgent[];
  activeAgentId?: string | null;
  onSelect: (id: string) => void;
}) {
  const { t } = useTranslation();
  const isMobile = useIsMobile();
  const [pinned, setPinned] = useAssistantPanelPreference();
  const [open, setOpen] = useState(false);
  const visible = (!isMobile && pinned) || open;
  return (
    <div
      className={`claw-secondary-sidebar ${
        !isMobile && pinned
          ? "claw-secondary-sidebar--pinned"
          : "claw-secondary-sidebar--floating"
      }`}
    >
      {(!pinned || isMobile) && (
        <button
          className="wb-assistants-trigger"
          type="button"
          onClick={() => setOpen((value) => !value)}
          aria-expanded={visible}
          aria-label={t("workbuddy.assistants")}
        >
          <PanelLeftOpen size={16} />
        </button>
      )}
      {visible && (
        <aside
          className={`wb-assistants${
            !pinned || isMobile ? " wb-assistants--floating" : ""
          }`}
          aria-label={t("workbuddy.assistants")}
        >
          <header>
            <h2>{t("workbuddy.assistants")}</h2>
            <button
              type="button"
              aria-pressed={pinned}
              onClick={() => {
                setPinned(!pinned);
                setOpen(false);
              }}
              aria-label={t("workbuddy.pinAssistants")}
            >
              <Pin size={16} />
            </button>
            {open && (
              <button
                type="button"
                onClick={() => setOpen(false)}
                aria-label={t("common.close")}
              >
                <X size={16} />
              </button>
            )}
          </header>
          <div className="wb-assistants__list">
            {agents.map((agent) => (
              <button
                key={agent.agent_id}
                type="button"
                onClick={() => {
                  onSelect(agent.agent_id);
                  setOpen(false);
                }}
                className={`claw-assistant-list-item${
                  agent.agent_id === activeAgentId
                    ? " claw-assistant-list-item--active"
                    : ""
                }`}
                aria-current={
                  agent.agent_id === activeAgentId ? "true" : undefined
                }
              >
                <span className="wb-assistants__avatar">
                  <ExpertIcon
                    iconUrl={agent.icon_url}
                    iconName={agent.icon_name}
                    size={28}
                  />
                </span>
                <span className="wb-assistants__name">
                  {agent.name}
                  <span>
                    <TeamChatBadge agent={agent} />
                    <SharedExpertHint agent={agent} />
                    <RemoteExpertHint agent={agent} />
                  </span>
                </span>
                {!!agent.unread_count && <small>{agent.unread_count}</small>}
              </button>
            ))}
          </div>
        </aside>
      )}
    </div>
  );
}
