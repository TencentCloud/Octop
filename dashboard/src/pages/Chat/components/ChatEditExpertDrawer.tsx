import { useMemo } from "react";
import { useAgent, type OctopAgent } from "../../../context/AgentContext";
import { isOwnedExpert } from "../../../utils/sharedExpert";
import { isTeamAgent } from "../../../utils/teamAgent";
import EditAgentDrawer from "../../Experts/components/EditAgentDrawer";
import TeamDrawer from "../../Experts/components/TeamDrawer";

/** Local experts and teams the current user can edit. Remote agents stay read-only. */
export function canEditExpertFromChat(agent: OctopAgent): boolean {
  return isOwnedExpert(agent) && !agent.bridge;
}

export default function ChatEditExpertDrawer({
  agent,
  onClose,
}: {
  agent: OctopAgent | null;
  onClose: () => void;
}) {
  const { agents, refresh } = useAgent();
  const team = agent && isTeamAgent(agent) ? agent : null;
  const expert = agent && !isTeamAgent(agent) ? agent : null;
  const memberExperts = useMemo(
    () =>
      agents.filter(
        (item) =>
          item.kind !== "team" && (isOwnedExpert(item) || item.is_shared),
      ),
    [agents],
  );
  const finish = () => {
    onClose();
    void refresh({ silent: true });
  };
  return (
    <>
      <EditAgentDrawer
        open={expert != null}
        agent={expert}
        onClose={onClose}
        onSaved={finish}
      />
      <TeamDrawer
        open={team != null}
        mode="edit"
        team={team}
        experts={memberExperts}
        onClose={onClose}
        onSaved={finish}
        onIconUrlChange={() => {
          void refresh({ silent: true });
        }}
      />
    </>
  );
}
