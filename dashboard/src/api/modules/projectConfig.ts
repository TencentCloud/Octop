import { request } from "../request";

/**
 * 项目级配置四组接口的 typed wrapper（第二批 · PLAN.md §1.4 / §2.3 / §3.3 / §5）。
 *
 * 字段名**逐字**取自 PLAN，不得自造；一律只写项目域端点，**不引用**全局用户目录。
 */

function projectPath(projectId: string): string {
  return `/projects/${encodeURIComponent(projectId)}`;
}

// ---------- ① 指令（PLAN §5）：纯展示，零注入面，上限 2000 ----------

export interface ProjectInstruction {
  /** 空串 = 未填写（S12：合法的「清空」语义，不是错误）。 */
  instruction: string;
}

// ---------- ② 连接器（PLAN §1.2/§1.4）：只存 kind，解析结果按当前用户 ----------

export interface ProjectConnectorResolution {
  kind: string;
  /** 当前用户是否有该 kind 的可用实例；`false` 是**非错误面**（S1/S2）。 */
  available: boolean;
  /** 命中的**本人**实例 id；未命中为 `null`（绝不回传他人实例）。 */
  resolved_instance_id: string | null;
  /** 命中实例的展示名，供 UI 显示「将使用你的 <display_name>」。 */
  display_name: string | null;
}

// ---------- ③ 技能（PLAN §2.3）：项目声明 = agent 技能集的投影 ----------

export interface ProjectSkillEffective {
  agent_id: string;
  skill_slug: string;
  display_name: string;
  kind: string;
}

/** 已声明但当前不在 `list_installed` 中（计算得出，不落库）。 */
export interface ProjectSkillStale {
  agent_id: string;
  skill_slug: string;
  reason: string;
}

export interface ProjectSkillsState {
  effective: ProjectSkillEffective[];
  stale: ProjectSkillStale[];
}

/** PUT 的写入项（全量替换，`{items:[{agent_id, skill_slug}]}`）。 */
export interface ProjectSkillWriteItem {
  agent_id: string;
  skill_slug: string;
}

// ---------- ④ cron（PLAN §3.3 + S4）：归属本项目，可见性与可写性都限本人 ----------

export interface ProjectCronJob {
  cron_id: string;
  name: string;
  agent_id: string;
  schedule_spec: string;
  enabled: boolean;
  last_run_at: number | null;
  /** 最近一次执行结果；Unix 秒与状态字符串由后端给定。 */
  last_status: string | null;
  /** 防御性不变式：非本人 job 的 `owned_by_me=false`。 */
  owned_by_me: boolean;
  /** 非本人 job 一律 `null`（`prompt_hidden=true`），永不跨用户下发。 */
  prompt: string | null;
  prompt_hidden: boolean;
  /** S4：执行者 agent 未运行时为 `false` —— 列表仍正常展示，不禁用不隐藏。 */
  agent_running: boolean;
}

export interface ProjectCronCreateBody {
  name: string;
  agent_id: string;
  schedule_spec: string;
  prompt: string;
  enabled?: boolean;
}

export interface ProjectCronUpdateBody {
  name?: string;
  schedule_spec?: string;
  prompt?: string;
  /** 启停 = 既有 `enabled` 列的布尔切换（不新增列）。 */
  enabled?: boolean;
}

export interface ProjectCronDeleteResult {
  deleted: boolean;
}

export const projectConfigApi = {
  // ① 指令
  getInstruction: (projectId: string) =>
    request<ProjectInstruction>(`${projectPath(projectId)}/instruction`),

  putInstruction: (projectId: string, instruction: string) =>
    request<ProjectInstruction>(`${projectPath(projectId)}/instruction`, {
      method: "PUT",
      body: JSON.stringify({ instruction }),
    }),

  // ② 连接器
  getConnectors: (projectId: string) =>
    request<ProjectConnectorResolution[]>(
      `${projectPath(projectId)}/connectors`,
    ),

  /** 全量替换声明的 kind；返回每项对**当前用户**的解析结果。 */
  putConnectors: (projectId: string, kinds: string[]) =>
    request<ProjectConnectorResolution[]>(
      `${projectPath(projectId)}/connectors`,
      { method: "PUT", body: JSON.stringify({ kinds }) },
    ),

  // ③ 技能
  getSkills: (projectId: string) =>
    request<ProjectSkillsState>(`${projectPath(projectId)}/skills`),

  /** 全量替换；任一脱节项（∉ `list_installed`）会被后端以 409 拒绝。 */
  putSkills: (projectId: string, items: ProjectSkillWriteItem[]) =>
    request<ProjectSkillsState>(`${projectPath(projectId)}/skills`, {
      method: "PUT",
      body: JSON.stringify({ items }),
    }),

  // ④ cron
  listCron: (projectId: string) =>
    request<ProjectCronJob[]>(`${projectPath(projectId)}/cron`),

  createCron: (projectId: string, body: ProjectCronCreateBody) =>
    request<ProjectCronJob>(`${projectPath(projectId)}/cron`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  /** 编辑（name/schedule_spec/prompt）+ 启停（enabled）；仅限本人 job。 */
  patchCron: (projectId: string, cronId: string, body: ProjectCronUpdateBody) =>
    request<ProjectCronJob>(
      `${projectPath(projectId)}/cron/${encodeURIComponent(cronId)}`,
      { method: "PATCH", body: JSON.stringify(body) },
    ),

  deleteCron: (projectId: string, cronId: string) =>
    request<ProjectCronDeleteResult>(
      `${projectPath(projectId)}/cron/${encodeURIComponent(cronId)}`,
      { method: "DELETE" },
    ),
};
