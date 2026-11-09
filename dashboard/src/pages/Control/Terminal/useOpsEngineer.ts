/**
 * 终端页的运维工程师：进入页面即就绪，终端进程和右侧对话都用这一个 agent。
 */
import { useEffect, useRef, useState } from "react";
import type { TFunction } from "i18next";

import {
  OPS_ENGINEER_EXPERT_ID,
  terminalAiApi,
  type CreatedOpsEngineer,
} from "../../../api/modules/terminalAi";
import { useAgent, type OctopAgent } from "../../../context/AgentContext";
import { apiErrorMessage, isNotFoundApiError } from "../../../utils/apiError";

/** 创建失败时给用户看的句子，不带接口原始 JSON。 */
export function formatOpsEnsureError(error: string, t: TFunction): string {
  const wrapped = new Error(error);
  if (isNotFoundApiError(wrapped)) return t("terminal.ai.gateCreateFailed");
  return apiErrorMessage(wrapped, t("terminal.ai.gateCreateFailed"), t);
}

function expertIdOf(agent: OctopAgent): string {
  const configured = (agent.config as { expert_id?: string } | undefined)
    ?.expert_id;
  return agent.template_name || configured || "";
}

export function findOpsEngineer(agents: OctopAgent[]): OctopAgent | null {
  return (
    agents.find((agent) => expertIdOf(agent) === OPS_ENGINEER_EXPERT_ID) ?? null
  );
}

function agentFromCreate(result: CreatedOpsEngineer): OctopAgent {
  return {
    id: result.id,
    agent_id: result.agent_id,
    name: result.name,
    description: result.description,
    persona_mbti: null,
    default_model: null,
    system_prompt: null,
    template_name: OPS_ENGINEER_EXPERT_ID,
    state: result.state,
    last_error: null,
    icon: null,
    icon_name: "terminal",
    icon_url: null,
    color: "#16a34a",
    config: { expert_id: OPS_ENGINEER_EXPERT_ID },
  };
}

export function useOpsEngineer(enabled: boolean) {
  const { agents, loading, refresh } = useAgent();
  const [agent, setAgent] = useState<OctopAgent | null>(null);
  const [ensuring, setEnsuring] = useState(false);
  const [ensureError, setEnsureError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const startedAttempt = useRef(-1);

  useEffect(() => {
    if (loading) return;
    const existing = findOpsEngineer(agents);
    if (existing) {
      setAgent(existing);
      setEnsureError(null);
      return;
    }
    if (!enabled || startedAttempt.current === attempt) return;
    startedAttempt.current = attempt;

    setEnsuring(true);
    void terminalAiApi
      .createOpsEngineer()
      .then((result) => {
        setAgent(agentFromCreate(result));
        setEnsureError(null);
        void refresh();
      })
      .catch((err: unknown) => {
        setEnsureError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        setEnsuring(false);
      });
  }, [enabled, loading, agents, refresh, attempt]);

  return {
    agent,
    ensuring,
    ensureError,
    retry: () => setAttempt((n) => n + 1),
  };
}
