import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import type { OctopAgent } from "../../../context/AgentContext";
import {
  SharedAvatarMark,
  SharedResourceBadge,
} from "../../../components/SharedResourceBadge";
import { isSharedExpertViewer } from "../../../utils/sharedExpert";

/** Puts the shared pip on an expert avatar and names the owner on hover. */
export default function SharedExpertHint({
  agent,
  className,
  children,
}: {
  agent: OctopAgent;
  className?: string;
  children: ReactNode;
}) {
  const { t } = useTranslation();
  const shared = isSharedExpertViewer(agent);
  return (
    <SharedAvatarMark
      className={className}
      shared={shared}
      owned={!shared}
      ownerName={agent.owner_username}
      label={t("chat.sharedExpert.banner", {
        name: agent.owner_username || "—",
      })}
    >
      {children}
    </SharedAvatarMark>
  );
}

/** “已共享” pill beside an expert title the current user owns and has shared. */
export function ExpertOwnerShareFlag({ agent }: { agent: OctopAgent }) {
  return (
    <SharedResourceBadge
      shared={agent.is_shared === true && agent.is_owner !== false}
      owned
      ownerName={agent.owner_username}
    />
  );
}
