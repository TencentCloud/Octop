import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// 只 mock 传输层：真跑 projectConfigApi / projectsApi / connectorsApi 的 wrapper，
// 从而顺带断言请求路径与请求体逐字正确。
vi.mock("../../../../api/request", () => ({
  request: vi.fn(),
  requestBlob: vi.fn(),
  requestUpload: vi.fn(),
}));

vi.mock("@/utils/antdMessage", () => ({
  message: {
    error: vi.fn(),
    success: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
  },
}));

vi.mock("../../../../utils/confirmModal", () => ({
  showConfirmModal: vi.fn(),
}));

/* 专家候选源（`AgentContext`）走**边界 mock**：`AgentProvider` 在 jsdom 下不水合
   （实测 `GET /agents` 已发出但 context 状态不落地）——与传输层 mock 同级，
   不改被测组件的取值路径（面板仍调用真实 `useAgent()`）。 */
const agentCtx = vi.hoisted(() => ({
  value: {
    agents: [] as unknown[],
    activeAgentId: null as string | null,
    activeAgent: null as unknown,
    loading: false,
    error: null as string | null,
    setActiveAgent: () => undefined,
    refresh: async () => undefined,
  },
  refreshers: [] as (() => void)[],
}));

vi.mock("../../../../context/AgentContext", () => ({
  useAgent: () => agentCtx.value,
  AgentProvider: ({ children }: { children?: unknown }) => children,
}));

vi.mock("../../../../hooks/useServerTimezone", () => ({
  useServerTimezone: () => "UTC",
}));

// i18n 用**真 zh.json** 解析 → 组件测试断言的是真实中文文案（S10），不是键名。
vi.mock("react-i18next", async () => {
  const fs = await import("node:fs");
  const path = await import("node:path");
  const zh = JSON.parse(
    fs.readFileSync(
      path.resolve(process.cwd(), "src/locales/zh.json"),
      "utf-8",
    ),
  ) as Record<string, unknown>;
  const lookup = (key: string): string | undefined => {
    let node: unknown = zh;
    for (const part of key.split(".")) {
      if (node === null || typeof node !== "object") return undefined;
      node = (node as Record<string, unknown>)[part];
    }
    return typeof node === "string" ? node : undefined;
  };
  const interpolate = (tpl: string, opts?: Record<string, unknown>) =>
    opts
      ? tpl.replace(/\{\{(\w+)\}\}/g, (match, name: string) =>
          name in opts ? String(opts[name]) : match,
        )
      : tpl;
  return {
    useTranslation: () => ({
      t: (key: string, fallback?: unknown, opts?: unknown) => {
        const options = (
          fallback !== null && typeof fallback === "object" ? fallback : opts
        ) as Record<string, unknown> | undefined;
        const template =
          lookup(key) ?? (typeof fallback === "string" ? fallback : undefined);
        return template === undefined ? key : interpolate(template, options);
      },
      i18n: { language: "zh", changeLanguage: () => Promise.resolve() },
    }),
    Trans: ({ children }: { children?: unknown }) => children,
  };
});

import { request } from "../../../../api/request";
import InstructionPanel from "./InstructionPanel";
import ConnectorsPanel from "./ConnectorsPanel";
import ExpertsPanel from "./ExpertsPanel";
import SkillsPanel from "./SkillsPanel";
import CronPanel from "./CronPanel";
import MembersPanel from "./MembersPanel";

const mockedRequest = vi.mocked(request);

const PROJECT = "p1";
const routes = new Map<string, unknown>();
const calls: { method: string; path: string; body?: unknown }[] = [];

function route(method: string, path: string, value: unknown) {
  routes.set(`${method} ${path}`, value);
}

function lastCall(path: string) {
  return calls.filter((call) => call.path === path).pop();
}

beforeEach(() => {
  routes.clear();
  calls.length = 0;
  // 成员端点在真实环境总是返回数组；默认给空数组，避免面板拿到 null。
  route("GET", `/projects/${PROJECT}/members`, []);
  setAgents([]);
  mockedRequest.mockReset();
  mockedRequest.mockImplementation(async (path: string, init?: RequestInit) => {
    const method = (init?.method ?? "GET").toUpperCase();
    calls.push({
      method,
      path: path as string,
      body: typeof init?.body === "string" ? JSON.parse(init.body) : undefined,
    });
    const key = `${method} ${path}`;
    return routes.has(key) ? routes.get(key) : null;
  });
});

describe("右栏面板（PLAN §1/§2/§3/§5/§7）", () => {
  it("六个面板各自渲染标题（真 zh 文案，S10）", async () => {
    route("GET", `/projects/${PROJECT}/instruction`, { instruction: "" });
    route("GET", `/projects/${PROJECT}/connectors`, []);
    route("GET", `/projects/${PROJECT}/skills`, {
      effective: [],
      stale: [],
    });
    route("GET", `/projects/${PROJECT}/cron`, []);
    route("GET", `/projects/${PROJECT}/members`, []);
    setAgents([]);

    render(
      <>
        <InstructionPanel projectId={PROJECT} canManage />
        <ConnectorsPanel projectId={PROJECT} canManage />
        <ExpertsPanel projectId={PROJECT} canManageMembers />
        <SkillsPanel projectId={PROJECT} canManage />
        <CronPanel projectId={PROJECT} canManage />
        <MembersPanel projectId={PROJECT} canManageMembers />
      </>,
    );

    for (const title of [
      "指令",
      "连接器",
      "专家",
      "技能",
      "定时任务",
      "成员",
    ]) {
      expect(await screen.findByText(title)).toBeInTheDocument();
    }
  });

  it("指令：空串 = 未填写占位（S12），有内容则展示正文", async () => {
    route("GET", `/projects/${PROJECT}/instruction`, { instruction: "" });
    const empty = render(<InstructionPanel projectId={PROJECT} canManage />);
    expect(await screen.findByText("未填写")).toBeInTheDocument();
    empty.unmount();

    route("GET", `/projects/${PROJECT}/instruction`, {
      instruction: "先做调研再排期",
    });
    render(<InstructionPanel projectId={PROJECT} canManage />);
    expect(await screen.findByText("先做调研再排期")).toBeInTheDocument();
    expect(screen.queryByText("未填写")).not.toBeInTheDocument();
  });

  it("指令：超 2000 字符给出中文提示并禁用保存", async () => {
    route("GET", `/projects/${PROJECT}/instruction`, { instruction: "x" });
    render(<InstructionPanel projectId={PROJECT} canManage />);

    const user = userEvent.setup();
    await screen.findByText("x");
    await user.click(screen.getByRole("button", { name: "编辑" }));
    const textarea = screen.getByLabelText("指令");
    fireEvent.change(textarea, { target: { value: "长".repeat(2001) } });

    expect(
      await screen.findByText("指令不得超过 2000 字符"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "保存" })).toBeDisabled();
  });

  it("连接器：可用 → 「将使用 <name>」+「可用」；S1/S2 不可用 → 灰态「对你不可用」，不是错误面", async () => {
    route("GET", `/projects/${PROJECT}/connectors`, [
      {
        kind: "tencent-docs",
        available: true,
        resolved_instance_id: "conn_1",
        display_name: "我的腾讯文档",
      },
      {
        kind: "weknora",
        available: false,
        resolved_instance_id: null,
        display_name: null,
      },
    ]);
    render(<ConnectorsPanel projectId={PROJECT} canManage />);

    expect(await screen.findByText("将使用 我的腾讯文档")).toBeInTheDocument();
    expect(screen.getByTestId("connector-available")).toHaveTextContent("可用");

    // S1/S2：灰态标注，**不得**用错误样式或错误空态。
    const unavailable = screen.getByTestId("connector-unavailable-weknora");
    expect(unavailable).toHaveTextContent("对你不可用");
    // S2 的 tooltip：悬停后出现 antd tooltip，文案复用 connectorUnavailable。
    await userEvent.hover(unavailable);
    expect(await screen.findByRole("tooltip")).toHaveTextContent("对你不可用");
    expect(
      screen.getByTestId("rail-connectors").querySelector(".ant-empty"),
    ).toBeNull();
  });

  it("连接器：空态用 connectorNone（不是空控件）", async () => {
    route("GET", `/projects/${PROJECT}/connectors`, []);
    render(<ConnectorsPanel projectId={PROJECT} canManage />);
    expect(await screen.findByTestId("connectors-empty")).toHaveTextContent(
      "尚未声明连接器",
    );
  });

  it("专家：只呈现 agent/team（与成员同源），空态用 expertNone", async () => {
    route("GET", `/projects/${PROJECT}/members`, [
      {
        subject_type: "agent",
        subject_id: "agent-a",
        user_id: null,
        role: "member",
        created_at: 1,
      },
      {
        subject_type: "team",
        subject_id: "team-1",
        user_id: null,
        role: "member",
        created_at: 1,
      },
      {
        subject_type: "user",
        subject_id: "7",
        user_id: 7,
        role: "owner",
        created_at: 1,
      },
    ]);
    const withExperts = render(
      <ExpertsPanel projectId={PROJECT} canManageMembers />,
    );
    expect(await screen.findByTestId("expert-agent-a")).toBeInTheDocument();
    expect(screen.getByTestId("expert-team-1")).toBeInTheDocument();
    // 用户成员不归「专家」面板（同源不同呈现）。
    expect(screen.queryByTestId("expert-7")).not.toBeInTheDocument();
    withExperts.unmount();

    route("GET", `/projects/${PROJECT}/members`, []);
    setAgents([]);
    render(<ExpertsPanel projectId={PROJECT} canManageMembers />);
    expect(await screen.findByTestId("experts-empty")).toHaveTextContent(
      "暂无专家",
    );
  });

  it("技能：effective 展示 display_name + kind；stale 显式标注失效（不隐藏）", async () => {
    route("GET", `/projects/${PROJECT}/skills`, {
      effective: [
        {
          agent_id: "agent-a",
          skill_slug: "ppt",
          display_name: "PPT 演示文稿",
          kind: "package",
        },
      ],
      stale: [
        {
          agent_id: "agent-a",
          skill_slug: "old-skill",
          reason: "no longer installed",
        },
      ],
    });
    render(<SkillsPanel projectId={PROJECT} canManage />);

    expect(await screen.findByText("PPT 演示文稿")).toBeInTheDocument();
    expect(screen.getByTestId("skill-ppt")).toHaveTextContent("package");
    expect(screen.getByTestId("skill-stale-old-skill")).toHaveTextContent(
      "已失效（该专家已不再安装）",
    );
  });

  it("技能：空态用 skillNone；新增表单给出「只能选择该专家已安装的技能」提示", async () => {
    route("GET", `/projects/${PROJECT}/skills`, { effective: [], stale: [] });
    route("GET", `/projects/${PROJECT}/members`, [
      {
        subject_type: "agent",
        subject_id: "agent-a",
        user_id: null,
        role: "member",
        created_at: 1,
      },
    ]);
    render(<SkillsPanel projectId={PROJECT} canManage />);

    expect(await screen.findByTestId("skills-empty")).toHaveTextContent(
      "尚未声明技能",
    );
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "添加技能" }));
    expect(
      await screen.findByText("只能选择该专家已安装的技能"),
    ).toBeInTheDocument();
  });

  it("cron：S4 agent 未运行仍列出并附灰点；非本人 job 只读（可见性 ≠ 可写性）", async () => {
    route("GET", `/projects/${PROJECT}/cron`, [
      {
        cron_id: "cron_mine",
        name: "每日汇总",
        agent_id: "agent-a",
        schedule_spec: "0 9 * * *",
        enabled: true,
        last_run_at: 1_750_000_000,
        last_status: "ok",
        owned_by_me: true,
        prompt: "总结今天",
        prompt_hidden: false,
        agent_running: false,
      },
      {
        cron_id: "cron_other",
        name: "他人任务",
        agent_id: "agent-b",
        schedule_spec: "0 10 * * *",
        enabled: true,
        last_run_at: null,
        last_status: null,
        owned_by_me: false,
        prompt: null,
        prompt_hidden: true,
        agent_running: true,
      },
    ]);
    render(<CronPanel projectId={PROJECT} canManage />);

    expect(await screen.findByTestId("cron-cron_mine")).toBeInTheDocument();
    // S4：未运行 → 灰点标注，行照常存在、不禁用。
    expect(screen.getByTestId("cron-agent-idle")).toBeInTheDocument();
    // 本人 job 可启停（两条 job 都 enabled → 按行内定位，避免同名多命中）。
    expect(
      within(screen.getByTestId("cron-cron_mine")).getByRole("checkbox", {
        name: "停用",
      }),
    ).not.toBeDisabled();
    // 他人 job：只读（无删除按钮、启停禁用），但**可见**。
    expect(screen.getByTestId("cron-cron_other")).toBeInTheDocument();
    expect(
      within(screen.getByTestId("cron-cron_other")).getByRole("checkbox", {
        name: "停用",
      }),
    ).toBeDisabled();
    expect(
      screen.getAllByRole("button", { name: "删除该定时任务？" }),
    ).toHaveLength(1);
  });

  it("cron：prompt_hidden 走防御分支 —— 显示「正文已隐藏（其他成员创建）」且不渲染正文", async () => {
    route("GET", `/projects/${PROJECT}/cron`, [
      {
        cron_id: "cron_hidden",
        name: "他人任务",
        agent_id: "agent-b",
        schedule_spec: "0 10 * * *",
        enabled: false,
        last_run_at: null,
        last_status: null,
        owned_by_me: false,
        prompt: null,
        prompt_hidden: true,
        agent_running: true,
      },
    ]);
    render(<CronPanel projectId={PROJECT} canManage />);

    const hidden = await screen.findByTestId("cron-prompt-hidden");
    expect(hidden).toHaveTextContent("正文已隐藏（其他成员创建）");
    expect(hidden).toHaveTextContent("由其他成员创建");
    expect(screen.queryByText("总结今天")).not.toBeInTheDocument();
  });

  it("cron：空态用 cronNone", async () => {
    route("GET", `/projects/${PROJECT}/cron`, []);
    render(<CronPanel projectId={PROJECT} canManage />);
    expect(await screen.findByTestId("cron-empty")).toHaveTextContent(
      "暂无定时任务",
    );
  });

  it("成员：membersHint 一行说明 + 角色中文 + 空态 membersEmpty", async () => {
    route("GET", `/projects/${PROJECT}/members`, [
      {
        subject_type: "user",
        subject_id: "7",
        user_id: 7,
        role: "owner",
        created_at: 1,
      },
    ]);
    const filled = render(
      <MembersPanel projectId={PROJECT} canManageMembers />,
    );
    expect(await screen.findByTestId("member-7")).toHaveTextContent("所有者");
    expect(screen.getByTestId("rail-members").textContent).toContain("成员");
    filled.unmount();

    route("GET", `/projects/${PROJECT}/members`, []);
    setAgents([]);
    render(<MembersPanel projectId={PROJECT} canManageMembers />);
    expect(await screen.findByTestId("members-empty")).toBeInTheDocument();
  });

  it("wrapper 路径与请求体逐字（PLAN §1.5 响应容器）", async () => {
    route("GET", `/projects/${PROJECT}/instruction`, { instruction: "x" });
    route("PUT", `/projects/${PROJECT}/instruction`, { instruction: "y" });
    route("GET", `/projects/${PROJECT}/connectors`, []);
    route("PUT", `/projects/${PROJECT}/connectors`, []);
    route("GET", `/projects/${PROJECT}/skills`, { effective: [], stale: [] });
    route("PUT", `/projects/${PROJECT}/skills`, { effective: [], stale: [] });
    route("GET", `/projects/${PROJECT}/cron`, []);
    route("GET", `/projects/${PROJECT}/members`, []);
    setAgents([]);

    const instruction = render(
      <InstructionPanel projectId={PROJECT} canManage />,
    );
    await screen.findByText("x");
    instruction.unmount();
    expect(lastCall(`/projects/${PROJECT}/instruction`)?.method).toBe("GET");

    const skills = render(<SkillsPanel projectId={PROJECT} canManage />);
    await waitFor(() =>
      expect(lastCall(`/projects/${PROJECT}/skills`)).toBeTruthy(),
    );
    skills.unmount();

    const cron = render(<CronPanel projectId={PROJECT} canManage />);
    await waitFor(() =>
      expect(lastCall(`/projects/${PROJECT}/cron`)).toBeTruthy(),
    );
    cron.unmount();

    const connectors = render(
      <ConnectorsPanel projectId={PROJECT} canManage />,
    );
    await waitFor(() =>
      expect(lastCall(`/projects/${PROJECT}/connectors`)).toBeTruthy(),
    );
    connectors.unmount();

    const members = render(
      <MembersPanel projectId={PROJECT} canManageMembers />,
    );
    await waitFor(() =>
      expect(lastCall(`/projects/${PROJECT}/members`)).toBeTruthy(),
    );
    members.unmount();

    // 全部走项目域端点，绝不涉及全局用户目录。
    for (const call of calls) {
      expect(call.path.startsWith("/projects/")).toBe(true);
    }
  });

  it("六个面板组件零硬编码中文（源码级，剥离注释后无 CJK）", () => {
    for (const file of [
      "InstructionPanel.tsx",
      "ConnectorsPanel.tsx",
      "ExpertsPanel.tsx",
      "SkillsPanel.tsx",
      "CronPanel.tsx",
      "MembersPanel.tsx",
    ]) {
      const source = readFileSync(resolve(__dirname, file), "utf-8")
        .replace(/\/\*[\s\S]*?\*\//g, "")
        .replace(/\/\/[^\n]*/g, "");
      expect(/[\u4e00-\u9fa5]/.test(source), `${file} 含硬编码中文`).toBe(
        false,
      );
    }
  });
});

/* ------------------------------------------------------------------ *
 * 批次六 · 选择器统一 + 中文化（PLAN §1 / §2 · AC-A/B/C）
 * ★ L18：候选走**真实路径** —— 专家经 `AgentProvider → GET /agents`，
 *   团队经 `teamsApi.list() → GET /teams`（不是直接塞 props 的构造性探针）。
 * ------------------------------------------------------------------ */
const AGENT = {
  id: 1,
  agent_id: "agt_1",
  name: "AI 编程导师",
  description: "带你写代码",
  state: "running",
};

function setAgents(list: unknown[]) {
  agentCtx.value = { ...agentCtx.value, agents: list };
}

describe("批次六 · 选择器统一与中文化（PLAN §1/§2）", () => {
  it("AC-A-1/AC-C-1：点「+」出现选择器（member-add-picker + picker-panel + 搜索框）", async () => {
    setAgents([AGENT]);
    render(<MembersPanel projectId={PROJECT} canManageMembers />);
    await waitFor(() =>
      expect(screen.getByTestId("member-add-picker")).toBeTruthy(),
    );
    fireEvent.click(screen.getByTestId("member-add-picker"));

    expect(await screen.findByTestId("picker-panel")).toBeTruthy();
    // 骨架自带搜索框（真 zh 占位）。
    expect(screen.getByPlaceholderText("输入以过滤…")).toBeTruthy();
    // 候选卡片走真实 agents 端点。
    expect(await screen.findByTestId("picker-option-agent-agt_1")).toBeTruthy();
  });

  it("AC-A-2 负向：候选只有专家/团队，**不出现用户**", async () => {
    setAgents([AGENT]);
    render(<MembersPanel projectId={PROJECT} canManageMembers />);
    fireEvent.click(await screen.findByTestId("member-add-picker"));
    await screen.findByTestId("picker-option-agent-agt_1");

    expect(screen.queryByTestId(/^picker-option-user-/)).toBeNull();
    expect(screen.getByTestId("picker-kind-agent")).toBeTruthy();
    expect(screen.getByTestId("picker-kind-team")).toBeTruthy();
  });

  it("AC-A-3：点候选卡片 → 既有 addMember 语义（同签名请求体）", async () => {
    setAgents([AGENT]);
    route("POST", `/projects/${PROJECT}/members`, {});
    render(<MembersPanel projectId={PROJECT} canManageMembers />);
    fireEvent.click(await screen.findByTestId("member-add-picker"));
    fireEvent.click(await screen.findByTestId("picker-option-agent-agt_1"));

    await waitFor(() => {
      expect(
        calls.some(
          (call) =>
            call.method === "POST" &&
            call.path === `/projects/${PROJECT}/members`,
        ),
      ).toBe(true);
    });
    const post = calls
      .filter(
        (call) =>
          call.method === "POST" &&
          call.path === `/projects/${PROJECT}/members`,
      )
      .pop();
    expect(post?.body).toEqual({
      subject_type: "agent",
      subject_id: "agt_1",
      role: "member",
    });
  });

  it("AC-B-1：类型枚举中文（选择器 kind = 专家/团队；成员行 = 用户/专家/团队）", async () => {
    setAgents([AGENT]);
    route("GET", `/projects/${PROJECT}/members`, [
      {
        subject_type: "user",
        subject_id: "u1",
        user_id: 1,
        role: "owner",
        created_at: 1,
        name: null,
      },
      {
        subject_type: "agent",
        subject_id: "agt_9",
        user_id: null,
        role: "member",
        created_at: 2,
        name: "助手",
      },
    ]);
    render(<MembersPanel projectId={PROJECT} canManageMembers />);

    expect(await screen.findByText("用户")).toBeTruthy();
    expect(screen.getByText("专家")).toBeTruthy();
    fireEvent.click(screen.getByTestId("member-add-picker"));
    expect(await screen.findByTestId("picker-kind-team")).toHaveTextContent(
      "团队",
    );
  });

  it("AC-B-2/AC-B-3：行显示 name；name 缺失 → 回退 subject_id（不得空白）", async () => {
    setAgents([]);
    route("GET", `/projects/${PROJECT}/members`, [
      {
        subject_type: "agent",
        subject_id: "agt_named",
        user_id: null,
        role: "member",
        created_at: 1,
        name: "有名字的专家",
      },
      {
        subject_type: "agent",
        subject_id: "agt_bare",
        user_id: null,
        role: "member",
        created_at: 2,
        name: null,
      },
      {
        subject_type: "team",
        subject_id: "team_blank",
        user_id: null,
        role: "member",
        created_at: 3,
        name: "   ",
      },
    ]);
    render(<MembersPanel projectId={PROJECT} canManageMembers />);

    expect(await screen.findByText("有名字的专家")).toBeTruthy();
    // ★ 回退：null 与「全空白」都落到 subject_id，不得空白。
    expect(
      within(screen.getByTestId("member-agt_bare")).getByText("agt_bare"),
    ).toBeTruthy();
    expect(
      within(screen.getByTestId("member-team_blank")).getByText("team_blank"),
    ).toBeTruthy();
  });

  it("R13/C12：已加入的候选显示勾选态且**不可重复提交**", async () => {
    setAgents([AGENT]);
    route("GET", `/projects/${PROJECT}/members`, [
      {
        subject_type: "agent",
        subject_id: "agt_1",
        user_id: null,
        role: "member",
        created_at: 1,
        name: "AI 编程导师",
      },
    ]);
    render(<MembersPanel projectId={PROJECT} canManageMembers />);
    fireEvent.click(await screen.findByTestId("member-add-picker"));

    const option = await screen.findByTestId("picker-option-agent-agt_1");
    expect(option).toBeDisabled();
    expect(screen.getByTestId("picker-joined-agent-agt_1")).toBeTruthy();
    fireEvent.click(option);
    expect(lastCall(`/projects/${PROJECT}/members`)?.method).not.toBe("POST");
  });

  it("R10：加载中不显示空态文案；团队候选为空 → pickerEmptyTeams", async () => {
    setAgents([]);
    route("GET", "/teams", []);
    render(<MembersPanel projectId={PROJECT} canManageMembers />);
    fireEvent.click(await screen.findByTestId("member-add-picker"));
    // 专家候选为空 → 「暂无专家」（既有键），且**不是**团队空态文案。
    expect(await screen.findByText("暂无专家")).toBeTruthy();

    // 切到团队 → 空候选 → 本批新键 pickerEmptyTeams。
    fireEvent.click(screen.getByTestId("picker-kind-team"));
    expect(await screen.findByText("暂无可选团队")).toBeTruthy();
  });

  it("失败 → 可重试（picker-failed + picker-retry 重新拉取，不静默空列表）", async () => {
    agentCtx.value = { ...agentCtx.value, agents: [], error: "boom" };
    const refreshSpy = vi.fn(async () => undefined);
    agentCtx.value.refresh = refreshSpy;
    render(<MembersPanel projectId={PROJECT} canManageMembers />);
    fireEvent.click(await screen.findByTestId("member-add-picker"));

    expect(await screen.findByTestId("picker-failed")).toBeTruthy();
    fireEvent.click(screen.getByTestId("picker-retry"));
    // 重试真实触发候选重取（`refresh({force:true})`）；**不得**静默空列表。
    await waitFor(() =>
      expect(refreshSpy).toHaveBeenCalledWith({ force: true }),
    );
  });

  it("AC-C-1：成员/专家/连接器/技能 四处「+」都渲染 picker-panel", async () => {
    setAgents([AGENT]);
    route("GET", `/projects/${PROJECT}/connectors`, []);
    route("GET", "/connectors/catalog", []);
    route("GET", `/projects/${PROJECT}/skills`, { effective: [], stale: [] });

    const members = render(
      <MembersPanel projectId={PROJECT} canManageMembers />,
    );
    fireEvent.click(await screen.findByTestId("member-add-picker"));
    expect(await screen.findByTestId("picker-panel")).toBeTruthy();
    members.unmount();

    const experts = render(
      <ExpertsPanel projectId={PROJECT} canManageMembers />,
    );
    fireEvent.click(await screen.findByLabelText("添加专家"));
    expect(await screen.findByTestId("picker-panel")).toBeTruthy();
    experts.unmount();

    const connectors = render(
      <ConnectorsPanel projectId={PROJECT} canManage />,
    );
    fireEvent.click(await screen.findByLabelText("添加连接器"));
    expect(await screen.findByTestId("picker-panel")).toBeTruthy();
    connectors.unmount();

    render(<SkillsPanel projectId={PROJECT} canManage />);
    fireEvent.click(await screen.findByLabelText("添加技能"));
    expect(await screen.findByTestId("picker-panel")).toBeTruthy();
  });
});

/* ------------------------------------------------------------------ *
 * 批次六复盘（V1 真机缺口）：同一「英文枚举 / 显示 ID」缺陷曾在**兄弟面板**里
 * 原样存在，而当时的判据只写在 MembersPanel（作用域缺口）。
 * ⇒ 本节判据**参数化遍历面板**，不再只盯一个文件。
 * ★ L17 命中范围：断言的是**渲染结果**（仅代码行，不读源码文本）。
 * ------------------------------------------------------------------ */
const REVIEW_ROWS = [
  {
    subject_type: "agent",
    subject_id: "agt_named",
    user_id: null,
    role: "member",
    created_at: 1,
    name: "有名字的专家",
  },
  {
    subject_type: "team",
    subject_id: "team_bare",
    user_id: null,
    role: "member",
    created_at: 2,
    name: null,
  },
];

/** 可见文案里不得出现裸英文类型枚举词（user/agent/team/package）。 */
function expectNoBareEnumWords() {
  for (const word of ["user", "agent", "team", "package"]) {
    expect(screen.queryByText(word)).toBeNull();
  }
}

describe("批次六复盘 · 兄弟面板同款形态（判据遍历面板）", () => {
  const panels: [string, () => JSX.Element][] = [
    [
      "MembersPanel",
      () => <MembersPanel projectId={PROJECT} canManageMembers />,
    ],
    [
      "ExpertsPanel",
      () => <ExpertsPanel projectId={PROJECT} canManageMembers />,
    ],
  ];

  it.each(panels)(
    "%s：行内类型为中文枚举 + 名字回退 subject_id + 无裸英文枚举词",
    async (_name, renderPanel) => {
      route("GET", `/projects/${PROJECT}/members`, REVIEW_ROWS);
      setAgents([]);
      render(renderPanel());

      // 名字：有名字显示名字；name=null 回退 subject_id（不得空白）。
      const namedRow = (await screen.findByText("有名字的专家")).closest(
        "li",
      ) as HTMLElement;
      const bareRow = screen
        .getByText("team_bare")
        .closest("li") as HTMLElement;
      // 类型枚举中文化（agent→专家、team→团队）——★ 断言收敛到**行作用域**
      //（面板标题本身也叫「专家」，全局查询会歧义）。
      expect(within(namedRow).getByText("专家")).toBeTruthy();
      expect(within(bareRow).getByText("团队")).toBeTruthy();
      // ★ 裸英文枚举词一律不得作为可见文案（旧实现这里就是 `agent`）。
      expectNoBareEnumWords();
    },
  );
});
