import MarketTopbarActions from "../../../workbuddy/MarketTopbarActions";
import { Button, Empty } from "antd";
import { ArrowLeft } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";
import { useAgent } from "../../../context/AgentContext";
import AgentSelector from "../../../components/AgentSelector";
import SkillsTabs from "./components/SkillsTabs";
import SkillHubTab from "./components/SkillHubTab";
export default function SkillsPage() {
  const { t } = useTranslation();
  const { activeAgentId } = useAgent();
  const [params, setParams] = useSearchParams();
  const installed = params.get("tab") === "installed";
  const select = (value: string) => {
    const next = new URLSearchParams(params);
    if (value === "installed") next.set("tab", value);
    else next.delete("tab");
    setParams(next);
  };
  return (
    <div className="wb-skills-page">
      <MarketTopbarActions tab="skills">
        {installed ? (
          <Button
            type="text"
            icon={<ArrowLeft size={14} />}
            onClick={() => select("discover")}
          >
            {t("workbuddy.market.discover")}
          </Button>
        ) : (
          <Button onClick={() => select("installed")}>
            {t("workbuddy.market.installed")}
          </Button>
        )}
      </MarketTopbarActions>
      <div className="wb-market-agent">
        <span>{t("workbuddy.market.installTarget")}</span>
        <AgentSelector showLabel={false} />
      </div>
      <div className="wb-skills-content">
        <div hidden={installed}>
          <SkillHubTab
            key={activeAgentId ?? "browse"}
            target={
              activeAgentId
                ? { type: "agent", agentId: activeAgentId }
                : { type: "browse" }
            }
          />
        </div>
        <div hidden={!installed}>
          {activeAgentId ? (
            <SkillsTabs
              key={activeAgentId}
              agentId={activeAgentId}
              installedOnly
            />
          ) : (
            <Empty description={t("skills.noAgentSelected")} />
          )}
        </div>
      </div>
    </div>
  );
}
