import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Only the transport is mocked: the component must read the project's members
// and its task list through the real API modules.
vi.mock("../../../api/request", () => ({
  request: vi.fn(),
  requestBlob: vi.fn(),
  requestUpload: vi.fn(),
  // ``wsChat.buildDashboardChatWsUrl`` reads the token through this export.
  getAuthToken: () => null,
}));

vi.mock("../../../hooks/useCurrentUser", () => ({
  useCurrentUser: () => ({ id: 7, role: "user" }),
}));

import { request } from "../../../api/request";
import type { ProjectMember } from "../../../api/modules/projects";
import QuickInput, { composeMessage } from "./QuickInput";

const mockedRequest = vi.mocked(request);

/** Minimal WebSocket double: records frames, replays scripts, tracks close(). */
class MockWebSocket {
  static instances: MockWebSocket[] = [];

  url: string;
  sent: string[] = [];
  closed = false;
  onopen: (() => void) | null = null;
  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }

  send(payload: string): void {
    this.sent.push(payload);
  }

  close(): void {
    this.closed = true;
  }

  /** Server → client frame. */
  emit(frame: unknown): void {
    this.onmessage?.({ data: JSON.stringify(frame) } as MessageEvent<string>);
  }

  emitRaw(data: string): void {
    this.onmessage?.({ data } as MessageEvent<string>);
  }

  open(): void {
    this.onopen?.();
  }

  serverClose(code = 1000): void {
    this.onclose?.({ code } as CloseEvent);
  }

  lastSent(): Record<string, unknown> {
    return JSON.parse(this.sent[this.sent.length - 1]) as Record<
      string,
      unknown
    >;
  }
}

const PROJECT = "p1";

function member(overrides: Partial<ProjectMember> = {}): ProjectMember {
  return {
    subject_type: "agent",
    subject_id: "agent-a",
    user_id: null,
    role: "member",
    created_at: 100,
    ...overrides,
  };
}

/** The caller's own membership row — it is what the write gate reads. */
function userMember(role = "member"): ProjectMember {
  return {
    subject_type: "user",
    subject_id: "7",
    user_id: 7,
    role: role as ProjectMember["role"],
    created_at: 1,
  };
}

function task(task_id: string, title: string) {
  return {
    task_id,
    project_id: PROJECT,
    parent_id: null,
    title,
    description: "",
    status: "todo" as const,
    assignee_type: null,
    assignee_id: null,
    priority: 0,
    deps: [],
    thread_id: null,
    origin_node_id: null,
    due_at: null,
    start_at: null,
    tags: [],
    custom_fields: [],
    attachments: [],
    sort_order: 0,
    created_by: 1,
    created_at: 1,
    updated_at: 1,
  };
}

type Handler = () => unknown;

let routes: Record<string, Handler>;

/** Mounts the component; the controls may legitimately be absent (UX gate). */
async function open() {
  render(<QuickInput projectId={PROJECT} />);
  await waitFor(() => {
    expect(mockedRequest).toHaveBeenCalled();
  });
  return {
    input: screen.queryByLabelText("projects.quickInputPlaceholder"),
    send: screen.queryByRole("button", {
      name: /projects\.quickInputSend|projects\.quickInputSending/,
    }),
  };
}

/** Types text and submits, then returns the socket the component opened. */
async function submit(text: string) {
  const { input, send } = await open();
  fireEvent.change(input, { target: { value: text } });
  fireEvent.click(send);
  await waitFor(() => expect(MockWebSocket.instances.length).toBe(1));
  const socket = MockWebSocket.instances[0];
  act(() => socket.open());
  return { socket, input };
}

beforeEach(() => {
  vi.clearAllMocks();
  MockWebSocket.instances = [];
  vi.stubGlobal("WebSocket", MockWebSocket);
  vi.useRealTimers();
  routes = {
    "/settings/timezone": () => ({ timezone: "UTC" }),
    "/projects/p1/members": () => [userMember(), member()],
    "/projects/p1/tasks": () => [task("tsk_1", "First task")],
  };
  mockedRequest.mockImplementation(async (path: string): Promise<unknown> => {
    const handler = routes[path];
    if (!handler) throw new Error(`unexpected request: ${path}`);
    return handler();
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("QuickInput — 目标 agent（PLAN §3.2 / AC-G3-6）", () => {
  it("0 个 agent：输入框 disabled + 常显说明文案（非错误面）", async () => {
    routes["/projects/p1/members"] = () => [userMember()];
    const { input, send } = await open();

    await waitFor(() => expect(input).toBeDisabled());
    expect(screen.getByTestId("quick-input-no-agent")).toHaveTextContent(
      "projects.quickInputNoAgent",
    );
    fireEvent.change(input, { target: { value: "hello" } });
    fireEvent.click(send);
    expect(MockWebSocket.instances).toHaveLength(0);
  });

  it("1 个 agent：常显「发给 <name>」", async () => {
    await open();
    await waitFor(() =>
      expect(screen.getByTestId("quick-input-target")).toHaveTextContent(
        "projects.quickInputTarget",
      ),
    );
    expect(screen.queryByTestId("quick-input-no-agent")).toBeNull();
  });

  it(">1 个 agent：按 (created_at, subject_id) 确定性取首条并明示", async () => {
    routes["/projects/p1/members"] = () => [
      member({ subject_id: "agent-z", created_at: 200 }),
      member({ subject_id: "agent-b", created_at: 100 }),
      member({ subject_id: "agent-a", created_at: 100 }),
      member({
        subject_type: "user",
        subject_id: "7",
        user_id: 7,
        created_at: 1,
      }),
    ];
    const { input, send } = await open();

    // 常显目标（文案键）——确定性由实际发送对象证明。
    await waitFor(() =>
      expect(screen.getByTestId("quick-input-target")).toHaveTextContent(
        "projects.quickInputTarget",
      ),
    );
    fireEvent.change(input, { target: { value: "hi" } });
    fireEvent.click(send);
    await waitFor(() => expect(MockWebSocket.instances.length).toBe(1));
    // created_at 相同时按 subject_id 升序 → agent-a（不是 agent-b/agent-z）。
    expect(MockWebSocket.instances[0].url).toContain(
      "/api/agents/agent-a/chat/ws",
    );
  });
});

describe("QuickInput — 发送走 WebSocket（PLAN §3.1/§3.4）", () => {
  it("连既有 WS 构造、发 user_turn、不传 thread_id", async () => {
    const { socket } = await submit("你好");

    expect(socket.url).toContain("/api/agents/agent-a/chat/ws");
    expect(socket.lastSent()).toEqual({ type: "user_turn", text: "你好" });
    expect(Object.keys(socket.lastSent())).not.toContain("thread_id");
  });

  it("done 是成功：置「已发送」+ 清空输入 + 关闭 socket", async () => {
    const { socket, input } = await submit("你好");

    act(() => socket.emit({ type: "done" }));

    await waitFor(() =>
      expect(screen.getByTestId("quick-input-sent")).toHaveTextContent(
        "projects.quickInputSent",
      ),
    );
    expect(input).toHaveValue("");
    expect(socket.closed).toBe(true);
  });

  it("非白名单帧一律忽略：token / usage / hitl_required / 未来新帧都不结终态，且不渲染回复正文", async () => {
    const { socket, input } = await submit("你好");

    act(() => {
      socket.emit({ type: "token", content: "REPLY_BODY_MUST_NOT_RENDER" });
      socket.emit({ type: "reasoning", content: "thinking" });
      socket.emit({ type: "usage", total_tokens: 3 });
      socket.emit({ type: "tool_call_chunk", name: "t" });
      socket.emit({ type: "tool_result", ok: true });
      socket.emit({ type: "hitl_required", id: "h1" });
      socket.emit({ type: "attachment", name: "a.txt" });
      socket.emit({ type: "state_snapshot", value: 1 });
      socket.emit({ type: "custom", anything: true });
      socket.emit({ type: "turn_status", active: true });
      socket.emit({ type: "pong" });
      socket.emit({ type: "brand_new_frame_from_the_future" });
    });

    // 仍在发送中：没有任何白名单终态帧。
    expect(screen.queryByTestId("quick-input-sent")).toBeNull();
    expect(screen.queryByTestId("quick-input-failed")).toBeNull();
    expect(screen.queryByText(/REPLY_BODY_MUST_NOT_RENDER/)).toBeNull();
    expect(input).toHaveValue("你好");
    expect(socket.closed).toBe(false);

    // 之后到达的 done 仍然是成功。
    act(() => socket.emit({ type: "done" }));
    await waitFor(() =>
      expect(screen.getByTestId("quick-input-sent")).toBeInTheDocument(),
    );
  });

  it("非 JSON 帧不结终态", async () => {
    const { socket } = await submit("你好");
    act(() => socket.emitRaw("not json"));
    expect(screen.queryByTestId("quick-input-sent")).toBeNull();
    expect(screen.queryByTestId("quick-input-failed")).toBeNull();
  });
});

describe("QuickInput — 失败语义（G3-Q3 / PLAN §3.4）", () => {
  it("★ 判别性对照：先 error 后 done → 仍判失败（提示可见 + 输入仍在 + socket 已关闭）", async () => {
    const { socket, input } = await submit("保留我");

    act(() => socket.emit({ type: "error", message: "boom" }));
    // 后端实测有 6 处「先 error 再 done」——done 不得翻案。
    act(() => socket.emit({ type: "done" }));

    await waitFor(() =>
      expect(screen.getByTestId("quick-input-failed")).toHaveTextContent(
        "projects.quickInputFailed",
      ),
    );
    expect(input).toHaveValue("保留我");
    expect(screen.queryByTestId("quick-input-sent")).toBeNull();
    expect(socket.closed).toBe(true);
  });

  /**
   * PLAN §3.5: 4003 / 4404 是**预期会正常发生**的路径（agent 访问权不足、agent
   * 不存在），不是「异常 / 意外」；4001（token 缺失/无效）与 1011（网关未就绪）
   * 同理走失败路径。四者行为一致，故参数化 —— 但每一条都真的被覆盖。
   */
  it.each([
    { code: 4001, what: "token 缺失或无效" },
    { code: 4003, what: "agent 访问权不足" },
    { code: 4404, what: "agent 不存在" },
    { code: 1011, what: "网关未就绪" },
  ])(
    "权限/访问权不足（close $code · $what）：显式失败 + 保留输入（预期会发生的正常路径）",
    async ({ code }) => {
      const { socket, input } = await submit("保留我");

      act(() => socket.serverClose(code));

      await waitFor(() =>
        expect(screen.getByTestId("quick-input-failed")).toBeInTheDocument(),
      );
      expect(input).toHaveValue("保留我");
    },
  );

  it("没有终态帧就 close（发送已完成）→ 失败路径", async () => {
    const { socket, input } = await submit("保留我");

    // 已经发出去、也没有 error，但服务端一个终态帧都没给就关了。
    act(() => socket.serverClose(1005));

    await waitFor(() =>
      expect(screen.getByTestId("quick-input-failed")).toBeInTheDocument(),
    );
    expect(input).toHaveValue("保留我");
  });

  it("发送完成前的 close（未 open）→ 失败路径", async () => {
    const { input, send } = await open();
    fireEvent.change(input, { target: { value: "x" } });
    fireEvent.click(send);
    await waitFor(() => expect(MockWebSocket.instances.length).toBe(1));
    const socket = MockWebSocket.instances[0];

    // 未 open（未发送）即关闭。
    act(() => socket.serverClose(4001));

    await waitFor(() =>
      expect(screen.getByTestId("quick-input-failed")).toBeInTheDocument(),
    );
    expect(input).toHaveValue("x");
  });

  it("提交期间禁用按钮：连点只开一个 socket", async () => {
    const { input, send } = await open();
    fireEvent.change(input, { target: { value: "只发一次" } });
    fireEvent.click(send);
    fireEvent.click(send);
    await waitFor(() => expect(MockWebSocket.instances.length).toBe(1));
    expect(MockWebSocket.instances).toHaveLength(1);
  });

  it("10s 无终态：主动关闭 + 置「已发送」（token 未到 ≠ 未投递）", async () => {
    const { input, send } = await open();
    fireEvent.change(input, { target: { value: "你好" } });

    vi.useFakeTimers();
    fireEvent.click(send);
    expect(MockWebSocket.instances).toHaveLength(1);
    const socket = MockWebSocket.instances[0];
    act(() => {
      socket.open();
      vi.advanceTimersByTime(10_000);
    });

    expect(screen.getByTestId("quick-input-sent")).toHaveTextContent(
      "projects.quickInputSent",
    );
    expect(socket.closed).toBe(true);
    vi.useRealTimers();
  });
});

describe("QuickInput — 任务引用（PLAN §3.3 / AC-G3-5）", () => {
  it("选择任务 → chip 显示标题，正文按冻结模板含 task_id", async () => {
    routes["/projects/p1/tasks"] = () => [
      task("tsk_1", "First task"),
      task("tsk_2", "Second task"),
    ];
    const { input, send } = await open();
    fireEvent.change(input, { target: { value: "请看这两个" } });

    // 先选引用，再发送。
    fireEvent.click(
      screen.getByRole("button", { name: "projects.quickInputRefTask" }),
    );
    fireEvent.click(await screen.findByRole("button", { name: "First task" }));
    fireEvent.click(screen.getByRole("button", { name: "Second task" }));
    // 标签渲染为标题（不是 id）。
    expect(screen.getAllByText("First task").length).toBeGreaterThan(0);

    fireEvent.click(send);

    await waitFor(() => expect(MockWebSocket.instances.length).toBe(1));
    const socket = MockWebSocket.instances[0];
    act(() => socket.open());
    expect(socket.lastSent().text).toBe(
      "请看这两个\n\n> 引用任务：First task（task_id=tsk_1）\n> 引用任务：Second task（task_id=tsk_2）",
    );
  });

  it("引用任务在发送前被删除 → 剔除 + quickInputRefRemoved，其余照常发送", async () => {
    routes["/projects/p1/tasks"] = () => [
      task("tsk_1", "First task"),
      task("tsk_2", "Second task"),
    ];
    const { send } = await open();

    const input = screen.getByLabelText("projects.quickInputPlaceholder");
    fireEvent.change(input, { target: { value: "只留第二个" } });
    fireEvent.click(
      screen.getByRole("button", { name: "projects.quickInputRefTask" }),
    );
    fireEvent.click(await screen.findByRole("button", { name: "First task" }));
    fireEvent.click(screen.getByRole("button", { name: "Second task" }));

    // tsk_1 在提交前消失（提交时重读任务列表）。
    routes["/projects/p1/tasks"] = () => [task("tsk_2", "Second task")];
    fireEvent.click(send);

    await waitFor(() => expect(MockWebSocket.instances.length).toBe(1));
    const socket = MockWebSocket.instances[0];
    act(() => socket.open());

    expect(socket.lastSent().text).toBe(
      "只留第二个\n\n> 引用任务：Second task（task_id=tsk_2）",
    );
    expect(screen.getByTestId("quick-input-ref-removed")).toHaveTextContent(
      "projects.quickInputRefRemoved",
    );
  });
});

describe("QuickInput — 角色 UX 门（非安全控制）", () => {
  it("viewer（无 PROJECT_WRITE）：不提供输入框，只给一行说明", async () => {
    routes["/projects/p1/members"] = () => [userMember("viewer"), member()];
    await open();

    await waitFor(() =>
      expect(screen.getByTestId("quick-input-readonly")).toHaveTextContent(
        "common.noPermission",
      ),
    );
    // 区域仍在（PLAN §3.5：不得因角色隐藏整个区域），但没有任何可交互入口。
    expect(screen.getByTestId("project-quick-input")).toBeInTheDocument();
    expect(
      screen.queryByLabelText("projects.quickInputPlaceholder"),
    ).toBeNull();
    expect(
      screen.queryByRole("button", { name: /projects\.quickInputSend/ }),
    ).toBeNull();
    expect(screen.queryByTestId("quick-input-target")).toBeNull();
    expect(MockWebSocket.instances).toHaveLength(0);
  });

  it("member / owner / admin（有 PROJECT_WRITE）：输入框正常可用", async () => {
    for (const role of ["member", "owner", "admin"]) {
      MockWebSocket.instances = [];
      routes["/projects/p1/members"] = () => [userMember(role), member()];
      const { unmount } = render(<QuickInput projectId={PROJECT} />);
      await waitFor(() =>
        expect(
          screen.getByLabelText("projects.quickInputPlaceholder"),
        ).toBeInTheDocument(),
      );
      expect(screen.queryByTestId("quick-input-readonly")).toBeNull();
      unmount();
    }
  });

  it("归档项目：同样不提供输入框（父层传 archived）", async () => {
    render(<QuickInput projectId={PROJECT} archived />);

    await waitFor(() =>
      expect(screen.getByTestId("quick-input-readonly")).toHaveTextContent(
        "common.noPermission",
      ),
    );
    expect(
      screen.queryByLabelText("projects.quickInputPlaceholder"),
    ).toBeNull();
  });

  it("viewer + 0 个 agent：权限说明优先于 quickInputNoAgent", async () => {
    routes["/projects/p1/members"] = () => [userMember("viewer")];
    await open();

    await waitFor(() =>
      expect(screen.getByTestId("quick-input-readonly")).toBeInTheDocument(),
    );
    expect(screen.queryByTestId("quick-input-no-agent")).toBeNull();
  });
});

describe("composeMessage（纯函数：转义与顺序）", () => {
  it("\\r\\n 折叠为空格、`>` 开头前缀空格、顺序 = 选择顺序", () => {
    const body = composeMessage("正文", [
      task("tsk_1", "line1\r\nline2"),
      task("tsk_2", ">quoted"),
    ]);

    expect(body).toBe(
      "正文\n\n> 引用任务：line1 line2（task_id=tsk_1）\n> 引用任务： >quoted（task_id=tsk_2）",
    );
    // 每个引用行都必须带上 task_id（可被下游识别为纯文本上下文）。
    expect(body).toContain("（task_id=tsk_1）");
    expect(body).toContain("（task_id=tsk_2）");
  });

  it("无引用时正文原样（不加空行）", () => {
    expect(composeMessage("只有正文", [])).toBe("只有正文");
  });
});
