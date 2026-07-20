/**
 * Skills page — three tabs:
 *   1. Customized Skills  (workspace kind, editable + deletable)
 *   2. Built-in Skills    (builtin kind, toggle only)
 *   3. Skill Market       (SkillHub marketplace)
 */

import { useTranslation } from "react-i18next";
import { useAgent } from "../../../context/AgentContext";
import PageShell from "../../../layouts/PageShell";
import SkillsTabs from "./components/SkillsTabs";

function SkillsPage() {
  const { t } = useTranslation();
  const { activeAgentId } = useAgent();

  return (
    <PageShell
      title={t("pageShell.skills.title")}
      subtitle={t("pageShell.skills.subtitle")}
      agentScoped
    >
      <SkillsTabs agentId={activeAgentId} />
    </PageShell>
  );
}

export default SkillsPage;
