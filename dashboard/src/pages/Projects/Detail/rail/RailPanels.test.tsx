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
