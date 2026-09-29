/**
 * T-41 — the **write half** of the memory scope layer (T-38 was the read half).
 *
 * Judged against SPEC **B38** (项目记忆读写权限分离): 读按 ``project_members``
 * （``viewer`` 也算成员）、写按团队 owner / 项目角色，**两者不合并**。 So every case
 * below is really one question: *can the UI let "this row was readable" turn into
 * "this write went through"?*
 *
 * The five criteria this file pins:
 *
 * ① 归属可显式选择 —— 默认 ``agent``（行为与 T-41 之前逐字一致），选 ``project``
 *    时目标由宿主回调收到，且**绝不**回落到 agent 命名空间；
 * ② 「记到项目」入口存在（``ProjectMemoryPanel`` 可选 props），**缺省不渲染任何写动作**
 *    —— T-38 的只读契约与既有调用点因此不受影响；
 * ③ **零写请求的反向断言**：能力缺失时点「采纳」→ 一条请求都不发（尤其是**不得**
 *    退化成"写进 agent ns 却声称归到项目"）；
 * ④ 写能力**不由"读得到"推导** —— 面板能渲染项目层数据，同时写入口是禁用的；
 * ⑤ 依赖表：新增的写路径不引入任何 effect（``ProjectMemoryPanel`` 依然零 fetch，
 *    由 ④ 那条静态断言兜住）。
 */

import { readFileSync } from "node:fs";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  listCandidatesResp,
  makeCandidate,
  promoteResp,
} from "../../../test/memoryFixtures";

vi.mock("../../../api/modules/memoryDashboard", () => ({
  memoryDashboardApi: {
    listCandidates: vi.fn(),
    promoteCandidate: vi.fn(),
    rejectCandidate: vi.fn(),
  },
}));

import {
  memoryDashboardApi,
  type CandidateItem,
} from "../../../api/modules/memoryDashboard";
import ProjectMemoryPanel, {
  type ScopePanelGroup,
} from "../../../components/ProjectMemoryPanel";
import CandidatesReview from "./CandidatesReview";

const api = vi.mocked(memoryDashboardApi, true);

const PROJECTS = [
  { id: "P1", name: "阿波罗" },
  { id: "P2", name: "贝尔" },
];

function oneCandidate(id = "cand-1", title = "咖啡偏好") {
  api.listCandidates.mockResolvedValue(
    listCandidatesResp([makeCandidate({ id, title })]),
  );
}

/** Confirm the promote Popconfirm (the row button and the ok button share a label). */
async function confirmPromote(user: ReturnType<typeof userEvent.setup>) {
  const rowBtns = await screen.findAllByRole("button", { name: /采\s*纳/ });
  await user.click(rowBtns[rowBtns.length - 1]);
}

/** Pick the 归属 project scope in the antd Select (open, then click the option). */
async function chooseProjectScope(user: ReturnType<typeof userEvent.setup>) {
  const combo = screen
    .getByTestId("memory-candidates-target")
    .querySelector(".ant-select-selector");
  if (!combo) throw new Error("归属 Select 未渲染");
  await user.click(combo);
  const option = await screen.findByTitle("归属项目");
  await user.click(option);
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("T-41 ①③ CandidatesReview — 采纳归属", () => {
  it("默认归属 = 本 agent 私有：仍是不带 namespace 的两参调用，且不碰项目回调", async () => {
    oneCandidate();
    api.promoteCandidate.mockResolvedValue(promoteResp());
    const onPromoteToProject = vi.fn();
    const user = userEvent.setup();

    render(
      <CandidatesReview
        agentId="ZYWZTD"
        projects={PROJECTS}
        onPromoteToProject={onPromoteToProject}
      />,
    );
    await waitFor(() =>
      expect(screen.getByText("咖啡偏好")).toBeInTheDocument(),
    );

    await user.click(screen.getByRole("button", { name: /采\s*纳/ }));
    await confirmPromote(user);

    await waitFor(() =>
      expect(api.promoteCandidate).toHaveBeenCalledWith("ZYWZTD", "cand-1"),
    );
    expect(onPromoteToProject).not.toHaveBeenCalled();
  });

  it("选「归属项目」⇒ 目标项目交给写回调，且【绝不】调用 agent 的采纳端点", async () => {
    oneCandidate();
    api.promoteCandidate.mockResolvedValue(promoteResp());
    const onPromoteToProject = vi.fn().mockResolvedValue(undefined);
    const user = userEvent.setup();

    render(
      <CandidatesReview
        agentId="ZYWZTD"
        projects={PROJECTS}
        onPromoteToProject={onPromoteToProject}
      />,
    );
    await waitFor(() =>
      expect(screen.getByText("咖啡偏好")).toBeInTheDocument(),
    );

    await chooseProjectScope(user);
    const projectCombo = screen
      .getByTestId("memory-candidates-target")
      .querySelectorAll(".ant-select-selector")[1];
    if (!projectCombo) throw new Error("项目 Select 未渲染");
    await user.click(projectCombo);
    await user.click(await screen.findByTitle("阿波罗"));

    await user.click(screen.getByRole("button", { name: /采\s*纳/ }));
    await confirmPromote(user);

    await waitFor(() => expect(onPromoteToProject).toHaveBeenCalledTimes(1));
    const [candidate, projectId] = onPromoteToProject.mock.calls[0] as [
      CandidateItem,
      string,
    ];
    expect(candidate.id).toBe("cand-1");
    expect(projectId).toBe("P1");
    // 关键：写到了项目，就**不能**再写一遍 agent ns。
    expect(api.promoteCandidate).not.toHaveBeenCalled();
  });

  it("③ 能力缺失（只有项目列表、没有写回调）⇒ 一条写请求都不发，也不退回 agent ns", async () => {
    oneCandidate();
    const user = userEvent.setup();

    render(<CandidatesReview agentId="ZYWZTD" projects={PROJECTS} />);
    await waitFor(() =>
      expect(screen.getByText("咖啡偏好")).toBeInTheDocument(),
    );

    // 入口存在，但**说明了**为什么不可写（不隐藏、不静默降级）。
    expect(
      screen.getByTestId("memory-candidates-project-unwritable"),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /采\s*纳/ }));
    await confirmPromote(user);

    // 默认归属仍是 agent ⇒ 走的仍是那条既有路径；项目写路径一次都没被触发。
    await waitFor(() =>
      expect(api.promoteCandidate).toHaveBeenCalledWith("ZYWZTD", "cand-1"),
    );
    expect(api.promoteCandidate).toHaveBeenCalledTimes(1);
  });

  it("③ 权限在选中之后被撤（重渲染丢掉回调）⇒ 采纳不发任何请求，尤其不退化成 agent ns", async () => {
    oneCandidate();
    api.promoteCandidate.mockResolvedValue(promoteResp());
    const onPromoteToProject = vi.fn().mockResolvedValue(undefined);
    const user = userEvent.setup();

    const { rerender } = render(
      <CandidatesReview
        agentId="ZYWZTD"
        projects={PROJECTS}
        onPromoteToProject={onPromoteToProject}
      />,
    );
    await waitFor(() =>
      expect(screen.getByText("咖啡偏好")).toBeInTheDocument(),
    );
    await chooseProjectScope(user);

    // 写能力被撤（例如权限变更 / 宿主撤回接线）。
    rerender(<CandidatesReview agentId="ZYWZTD" projects={PROJECTS} />);
    await waitFor(() =>
      expect(
        screen.getByTestId("memory-candidates-project-unwritable"),
      ).toBeInTheDocument(),
    );

    await user.click(screen.getByRole("button", { name: /采\s*纳/ }));
    await confirmPromote(user);

    await waitFor(() =>
      expect(screen.getByText(/本次未发出任何写入请求/)).toBeInTheDocument(),
    );
    expect(onPromoteToProject).not.toHaveBeenCalled();
    // 这一条是 B38 的核心：不允许"写不进项目"就悄悄改成"写进 agent"。
    expect(api.promoteCandidate).not.toHaveBeenCalled();
  });
});

describe("T-41 ②④ ProjectMemoryPanel — 记到项目入口（可选 props）", () => {
  function groups(): ScopePanelGroup[] {
    return [
      {
        source_layer: "project",
        namespace: "project_P1",
        total: 1,
        items: [
          {
            id: "p1",
            text: "项目层的一条",
            source_layer: "project",
            namespace: "project_P1",
          },
        ],
      },
      {
        source_layer: "agent",
        namespace: "agent_ZYWZTD",
        total: 1,
        items: [
          {
            id: "a1",
            text: "只在私有层的一条",
            source_layer: "agent",
            namespace: "agent_ZYWZTD",
          },
        ],
      },
    ];
  }

  it("缺省（不传写 props）⇒ 一个写动作都不渲染：T-38 的只读契约原样保留", () => {
    render(<ProjectMemoryPanel groups={groups()} />);
    expect(screen.getByTestId("memory-scope-panel")).toBeInTheDocument();
    expect(
      screen.queryByTestId("memory-scope-record-to-project"),
    ).not.toBeInTheDocument();
    expect(screen.queryByTestId("memory-scope-write")).not.toBeInTheDocument();
  });

  it("④ 能渲染项目层数据，同时写入口仍是禁用的 —— 读得出 ≠ 写得进", () => {
    render(
      <ProjectMemoryPanel
        groups={groups()}
        recordToProjectHint="只读：写权限按团队 owner / 项目角色判定"
      />,
    );
    // 读侧照常（项目层数据在）
    expect(
      screen.getByTestId("memory-scope-group-project"),
    ).toBeInTheDocument();
    // 写侧不存在，只给说明
    expect(
      screen.queryByTestId("memory-scope-record-to-project"),
    ).not.toBeInTheDocument();
    expect(screen.getByTestId("memory-scope-write-hint")).toHaveTextContent(
      "只读：写权限按团队 owner / 项目角色判定",
    );
  });

  it("给了写回调 ⇒ 「记到项目」只出现在仅私有层的行上，点击把它交回宿主", async () => {
    const onRecordToProject = vi.fn();
    const user = userEvent.setup();

    render(
      <ProjectMemoryPanel
        groups={groups()}
        onRecordToProject={onRecordToProject}
      />,
    );

    const buttons = screen.getAllByTestId("memory-scope-record-to-project");
    // 项目层与团队层不该有「记到项目」—— 它们本来就在项目里了。
    expect(buttons).toHaveLength(1);
    const agentGroup = screen.getByTestId("memory-scope-group-agent");
    expect(agentGroup).toContainElement(buttons[0]);

    await user.click(buttons[0]);
    expect(onRecordToProject).toHaveBeenCalledTimes(1);
    expect(onRecordToProject.mock.calls[0][0]).toMatchObject({
      id: "a1",
      namespace: "agent_ZYWZTD",
    });
  });

  it("⑤ 面板仍然是零 fetch 的纯展示件（源码里没有任何请求/写动词）", () => {
    // vitest 的 root 就是 ``dashboard/``（见 RUN 头），所以这里按 cwd 取源文件；
    // 不用 ``import.meta.url`` —— 在 jsdom 里它不保证是 file: scheme。
    const src = readFileSync("src/components/ProjectMemoryPanel.tsx", "utf8");
    // 不得引入任何 HTTP 客户端（面板只调宿主传进来的回调）。
    expect(src).not.toMatch(/from\s+["'][^"']*api\//);
    expect(src).not.toMatch(/\b(fetch|request)\s*\(/);
  });
});
