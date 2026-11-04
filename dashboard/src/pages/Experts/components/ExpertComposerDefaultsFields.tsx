import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Form, Select } from "antd";

import { connectorsApi } from "../../../api/modules/connectors";
import { knowledgeBasesApi } from "../../../api/modules/knowledgeBases";
import { useCurrentUser } from "../../../hooks/useCurrentUser";
import { ConnectorLogo } from "../../Agent/Connectors/connectorDefs";
import { KnowledgeBaseAvatar } from "../../KnowledgeBases/knowledgeIcons";

interface ExpertComposerDefaultsFieldsProps {
  /** Bridge shadow id so knowledge / connector pickers tunnel to the peer. */
  agentId?: string | null;
}

type KnowledgeOption = {
  id: string;
  name: string;
  icon_name: string;
  icon_url?: string;
};

type ConnectorOption = {
  value: string;
  label: string;
  kind: string;
};

function selectOptionLabel(icon: ReactNode, text: string): ReactNode {
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 8,
        minWidth: 0,
        maxWidth: "100%",
      }}
    >
      <span
        style={{
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          flexShrink: 0,
          width: 16,
          height: 16,
          color: "var(--fn-text-secondary)",
        }}
      >
        {icon}
      </span>
      <span
        style={{
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
        }}
      >
        {text}
      </span>
    </span>
  );
}

export default function ExpertComposerDefaultsFields({
  agentId,
}: ExpertComposerDefaultsFieldsProps) {
  const { t } = useTranslation();
  const currentUserId = useCurrentUser()?.id ?? null;
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeOption[]>([]);
  const [knowledgeLoading, setKnowledgeLoading] = useState(false);
  const [connectors, setConnectors] = useState<ConnectorOption[]>([]);
  const [connectorsLoading, setConnectorsLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setKnowledgeLoading(true);
    knowledgeBasesApi
      .list(agentId)
      .then((bases) => {
        if (!cancelled) {
          setKnowledgeBases(
            bases.map((base) => ({
              id: base.id,
              name: base.name,
              icon_name: base.icon_name,
              icon_url: base.icon_url,
            })),
          );
        }
      })
      .catch(() => {
        if (!cancelled) setKnowledgeBases([]);
      })
      .finally(() => {
        if (!cancelled) setKnowledgeLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [agentId]);

  useEffect(() => {
    let cancelled = false;
    setConnectorsLoading(true);
    connectorsApi
      .listInstances(agentId)
      .then((instances) => {
        if (cancelled) return;
        setConnectors(
          (instances ?? [])
            .filter(
              (item) =>
                item.status === "active" &&
                item.has_credentials &&
                item.usable !== false,
            )
            .map((item) => ({
              value: item.mcp_server_name,
              kind: item.kind,
              label:
                currentUserId !== null && item.owner_user_id !== currentUserId
                  ? `${item.display_name} · ${
                      item.owner_display_name ||
                      item.owner_username ||
                      item.owner_user_id
                    }`
                  : item.display_name || item.mcp_server_name,
            })),
        );
      })
      .catch(() => {
        if (!cancelled) setConnectors([]);
      })
      .finally(() => {
        if (!cancelled) setConnectorsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [agentId, currentUserId]);

  const knowledgeById = useMemo(
    () => new Map(knowledgeBases.map((base) => [base.id, base])),
    [knowledgeBases],
  );
  const connectorByValue = useMemo(
    () => new Map(connectors.map((item) => [item.value, item])),
    [connectors],
  );

  return (
    <>
      <Form.Item
        name="knowledge_base_ids"
        label={t("experts.knowledgeBasesLabel")}
        extra={t("experts.knowledgeBasesHint")}
      >
        <Select
          mode="multiple"
          allowClear
          showSearch
          optionFilterProp="label"
          loading={knowledgeLoading}
          options={knowledgeBases.map((base) => ({
            value: base.id,
            label: base.name,
          }))}
          optionRender={(option) => {
            const base = knowledgeById.get(String(option.value));
            if (!base) return option.label;
            return selectOptionLabel(
              <KnowledgeBaseAvatar
                iconUrl={base.icon_url}
                iconName={base.icon_name}
                size={14}
              />,
              base.name,
            );
          }}
          labelRender={(option) => {
            const base = knowledgeById.get(String(option.value));
            if (!base) return option.label;
            return selectOptionLabel(
              <KnowledgeBaseAvatar
                iconUrl={base.icon_url}
                iconName={base.icon_name}
                size={14}
              />,
              base.name,
            );
          }}
          placeholder={t("experts.knowledgeBasesPlaceholder")}
        />
      </Form.Item>
      <Form.Item
        name="mcp_servers"
        label={t("experts.connectorsLabel")}
        extra={t("experts.connectorsHint")}
      >
        <Select
          mode="multiple"
          allowClear
          showSearch
          optionFilterProp="label"
          loading={connectorsLoading}
          options={connectors.map((item) => ({
            value: item.value,
            label: item.label,
          }))}
          optionRender={(option) => {
            const item = connectorByValue.get(String(option.value));
            if (!item) return option.label;
            return selectOptionLabel(
              <ConnectorLogo kind={item.kind} size={14} />,
              item.label,
            );
          }}
          labelRender={(option) => {
            const item = connectorByValue.get(String(option.value));
            if (!item) return option.label;
            return selectOptionLabel(
              <ConnectorLogo kind={item.kind} size={14} />,
              item.label,
            );
          }}
          placeholder={t("experts.connectorsPlaceholder")}
        />
      </Form.Item>
    </>
  );
}
