// dashboard/src/pages/Agent/Skills/components/AgentPickerModal.tsx
import { Modal, List, Avatar, Empty } from "antd";
import { useTranslation } from "react-i18next";
import { useAgent } from "../../../../context/AgentContext";
import type { OctopAgent } from "../../../../context/AgentContext";
import { ownedExperts } from "../../../../utils/sharedExpert";

interface AgentPickerModalProps {
  open: boolean;
  onClose: () => void;
  onPick: (agent: OctopAgent) => void;
}

export default function AgentPickerModal({
  open,
  onClose,
  onPick,
}: AgentPickerModalProps) {
  const { t } = useTranslation();
  const { agents } = useAgent();
  const selectable = ownedExperts(agents);

  return (
    <Modal
      open={open}
      title={t("skills.pickAgent", "Choose an agent to install into")}
      onCancel={onClose}
      footer={null}
      width={480}
      destroyOnHidden
    >
      {selectable.length === 0 ? (
        <Empty description={t("skills.noAgents", "No agents available")} />
      ) : (
        <List
          dataSource={selectable}
          renderItem={(agent) => (
            <List.Item
              key={agent.agent_id}
              style={{
                cursor: "pointer",
                borderRadius: 6,
                padding: "8px 12px",
              }}
              onClick={() => {
                onPick(agent);
                onClose();
              }}
            >
              <List.Item.Meta
                avatar={
                  <Avatar
                    style={{
                      background: "var(--fn-color-brand, #6366f1)",
                      fontSize: 14,
                    }}
                  >
                    {(agent.name || "?").charAt(0).toUpperCase()}
                  </Avatar>
                }
                title={agent.name}
                description={agent.description ?? undefined}
              />
            </List.Item>
          )}
        />
      )}
    </Modal>
  );
}
