import { useAgent, type OctopAgent } from "../../../context/AgentContext";
import { isOwnedExpert } from "../../../utils/sharedExpert";
import { isTeamAgent } from "../../../utils/teamAgent";
import EditAgentDrawer from "../../Experts/components/EditAgentDrawer";

/** Local experts the current user can edit. Teams and remote experts use other screens. */
export function canEditExpertFromChat(agent: OctopAgent): boolean {
  return isOwnedExpert(agent) && !agent.bridge && !isTeamAgent(agent);
}

export default function ChatEditExpertDrawer({
  agent,
  onClose,
}: {
  agent: OctopAgent | null;
  onClose: () => void;
}) {
  const { refresh } = useAgent();
  return (
    <EditAgentDrawer
      open={agent != null}
      agent={agent}
      onClose={onClose}
      onSaved={() => {
        onClose();
        void refresh({ silent: true });
      }}
    />
  );
}
