/**
 * 腾讯云云服务器运维专家：授权后自动就绪，无需用户去专家市场手动添加。
 *
 * 行为：
 * 1. 已存在该专家的 agent 实例 → 直接返回它的 id
 * 2. 不存在 → 静默创建一次（绑定运维相关知识库），失败则退回 null
 *
 * 创建是幂等的：同一页面生命周期内只会尝试一次。
 */
import { useEffect, useRef, useState } from "react";

import { knowledgeBasesApi } from "../api/modules/knowledgeBases";
import { request } from "../api/request";
import { useAgent, type OctopAgent } from "../context/AgentContext";

/** 内置专家模板 id，对应 src/octop/infra/agents/experts/library/tencent-cvm-ops。 */
export const CVM_OPS_EXPERT_ID = "tencent-cvm-ops";

/** 自动挑选用作运维知识库的命名特征。 */
const OPS_KB_PATTERN = /运维|巡检|sre|ops|runbook|规范|手册|基线|sop/i;

export function findCvmOpsAgent(rows: OctopAgent[]): OctopAgent | null {
  return (
    rows.find((agent) => {
      if (agent.template_name === CVM_OPS_EXPERT_ID) return true;
      const expertId = (agent.config as { expert_id?: string } | undefined)
        ?.expert_id;
      return expertId === CVM_OPS_EXPERT_ID;
    }) ?? null
  );
}

export function useCvmOpsExpert(enabled: boolean) {
  const { agents, refresh } = useAgent();
  const [agentId, setAgentId] = useState<string | null>(null);
  const [ensuring, setEnsuring] = useState(false);
  const [ensureError, setEnsureError] = useState<string | null>(null);
  const createdRef = useRef(false);
  /** 409 冲突后最多再尝试一次创建，防止旧后端下形成刷新循环。 */
  const conflictRetriedRef = useRef(false);

  useEffect(() => {
    if (!enabled) {
      setAgentId(null);
      return;
    }

    const existing = findCvmOpsAgent(agents);
    if (existing) {
      setAgentId(existing.agent_id);
      setEnsureError(null);
      return;
    }

    if (createdRef.current) return;
    createdRef.current = true;
    setEnsuring(true);

    void (async () => {
      try {
        let knowledgeBaseIds: string[] = [];
        try {
          const bases = await knowledgeBasesApi.list();
          knowledgeBaseIds = bases
            .filter((base) => OPS_KB_PATTERN.test(base.name))
            .map((base) => base.id);
        } catch {
          // 知识库不可用不应阻塞专家创建
        }

        const created = await request<{ agent_id: string; name: string }>(
          `/agents/from-expert/${CVM_OPS_EXPERT_ID}`,
          {
            method: "POST",
            body: JSON.stringify({
              knowledge_base_ids: knowledgeBaseIds.length
                ? knowledgeBaseIds
                : undefined,
            }),
          },
        );
        setAgentId(created.agent_id);
        setEnsureError(null);
        await refresh();
      } catch (error) {
        const message =
          error instanceof Error ? error.message : String(error ?? "");
        // 名称冲突说明同名专家已经存在（旧接口不幂等，或并发触发）。
        // 刷新列表后优先交给 existing 分支接管；若列表里仍找不到（后端尚未
        // 幂等），允许再走一次创建——最多一次，避免旧后端下 409 → refresh
        // → 再创建的死循环。
        if (message.includes("AGENT_NAME_TAKEN") || message.includes("409")) {
          if (!conflictRetriedRef.current) {
            conflictRetriedRef.current = true;
            createdRef.current = false;
            void refresh();
          }
          return;
        }
        // 允许下次进入页面重试，并把原因暴露给面板，避免静默失败
        createdRef.current = false;
        setEnsureError(
          message.includes("404")
            ? "服务端未加载该专家模板，请重启后端服务"
            : message || "专家初始化失败",
        );
      } finally {
        setEnsuring(false);
      }
    })();
  }, [enabled, agents, refresh]);

  return { agentId, ensuring, ensureError };
}
