import { readFileSync } from "node:fs";
import { resolve } from "node:path";
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

/** Same as ``open``, but waits until the recipient picker is available. */
async function openWithPicker() {
  const controls = await open();
  await screen.findByTestId("quick-input-recipient-trigger");
  return controls;
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

  // ★ PLAN §9 O3（被推翻口径）：after 逐字 —— 默认值规则**保留**，只**增**切换断言
  //   （「推翻 ≠ 弱化」：改的是能力上限，不是放宽任何既有断言）。
  it(">1 个 agent：默认按 (created_at, subject_id) 取首条并明示；可切换为其它 agent", async () => {
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
    const { input, send } = await openWithPicker();

    // ① 既有断言（默认值的确定性 + 常显目标）逐字保留。
    await waitFor(() =>
      expect(screen.getByTestId("quick-input-target")).toHaveTextContent(
        "projects.quickInputTarget",
      ),
    );
    // ② 新增：默认 = 确定性首条（乱序注入 → agent-a；agent-b/agent-z 均非首条）。
    expect(screen.getByTestId("quick-input-target").textContent).not.toContain(
      "agent-b",
    );
    expect(screen.getByTestId("quick-input-target").textContent).not.toContain(
      "agent-z",
    );
    fireEvent.change(input, { target: { value: "hi" } });
    fireEvent.click(send);
    await waitFor(() => expect(MockWebSocket.instances.length).toBe(1));
    // created_at 相同时按 subject_id 升序 → agent-a（不是 agent-b/agent-z）。
    expect(MockWebSocket.instances[0].url).toContain(
      "/api/agents/agent-a/chat/ws",
    );

    // ③ 新增：发完一轮后仍可切换收件人（目标是新增能力，不是放宽旧判据）。
    act(() => MockWebSocket.instances[0].emit({ type: "done" }));
    fireEvent.click(
      await (async () => {
        fireEvent.click(screen.getByTestId("quick-input-recipient-trigger"));
        return screen.findByTestId("quick-input-recipient-option-agent-b");
      })(),
    );
    // 切换生效（"发给谁"的文案模板由 i18n 渲染，共享 mock 只回键 → 用选中态证）。
    fireEvent.click(screen.getByTestId("quick-input-recipient-trigger"));
    expect(
      (
        await screen.findByTestId("quick-input-recipient-option-agent-b")
      ).getAttribute("aria-pressed"),
    ).toBe("true");
  });
});

describe("QuickInput — 发送走 WebSocket（PLAN §3.1/§3.4）", () => {
  it("连既有 WS 构造、发 user_turn、不传 thread_id", async () => {
    const { socket } = await submit("你好");

    expect(socket.url).toContain("/api/agents/agent-a/chat/ws");
    // ★ 形态调整（批次十 T-WS-FE ③ 的必然结果，**不弱化**）：帧体新增 `project_id`
    //   ⇒ 原「两键深相等」无法成立；改为**枚举全部键**（等价强度：任何多余/缺失键都会红）
    //   + 逐字段值断言。
    expect(Object.keys(socket.lastSent()).sort()).toEqual([
      "project_id",
      "text",
      "type",
    ]);
    expect(socket.lastSent()).toMatchObject({
      type: "user_turn",
      text: "你好",
      project_id: PROJECT,
    });
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

/** Opens the picker and returns the option button for one agent. */
async function pickOption(subjectId: string) {
  fireEvent.click(screen.getByTestId("quick-input-recipient-trigger"));
  return screen.findByTestId(`quick-input-recipient-option-${subjectId}`);
}

/** Reopens the picker (it closes on select) and reads the chosen option. */
async function chosenAfterReopen(subjectId: string): Promise<boolean> {
  fireEvent.click(screen.getByTestId("quick-input-recipient-trigger"));
  const option = await screen.findByTestId(
    `quick-input-recipient-option-${subjectId}`,
  );
  return option.getAttribute("aria-pressed") === "true";
}

function isChosen(subjectId: string): boolean {
  return (
    screen
      .getByTestId(`quick-input-recipient-option-${subjectId}`)
      .getAttribute("aria-pressed") === "true"
  );
}

describe("QuickInput — D2 收件人选择（PLAN §2 · AC-D2-1..6）", () => {
  const shuffledMembers = () => [
    userMember(),
    // 乱序注入：不得依赖 DB/接口返回顺序。
    member({ subject_id: "agent-z", created_at: 200 }),
    member({ subject_id: "agent-a", created_at: 100 }),
    member({ subject_id: "agent-b", created_at: 100 }),
  ];

  it("AC-D2-1: 只列 agent —— 负向注入 user 成员不出现在选项里", async () => {
    routes["/projects/p1/members"] = shuffledMembers;
    await openWithPicker();

    fireEvent.click(screen.getByTestId("quick-input-recipient-trigger"));
    await screen.findByTestId("quick-input-recipient-option-agent-a");

    // 3 个 agent 选项（user 行「7」不得出现）。
    const options = document.querySelectorAll(
      '[data-testid^="quick-input-recipient-option-"]',
    );
    expect(options).toHaveLength(3);
    expect(screen.queryByTestId("quick-input-recipient-option-7")).toBeNull();
  });

  it("AC-D2-2: 默认 = 确定性首条（乱序注入 → agent-a，不依赖返回顺序）", async () => {
    routes["/projects/p1/members"] = shuffledMembers;
    const { input, send } = await openWithPicker();

    // 默认 = 首条：打开选择器时 agent-a 是当前项（乱序注入不影响）。
    await pickOption("agent-a");
    expect(isChosen("agent-a")).toBe(true);
    expect(isChosen("agent-b")).toBe(false);
    expect(isChosen("agent-z")).toBe(false);
    fireEvent.keyDown(document.body, { key: "Escape" });

    // 确定性由实际发送对象再证一次。
    fireEvent.change(input, { target: { value: "hi" } });
    fireEvent.click(send);
    await waitFor(() => expect(MockWebSocket.instances.length).toBe(1));
    expect(MockWebSocket.instances[0].url).toContain(
      "/api/agents/agent-a/chat/ws",
    );
  });

  it("AC-D2-3: 切换收件人 → 目标文案随之更新；且无 localStorage 写入", async () => {
    const setItem = vi.fn();
    vi.stubGlobal("localStorage", {
      getItem: () => null,
      setItem,
      removeItem: vi.fn(),
    });
    routes["/projects/p1/members"] = shuffledMembers;
    await openWithPicker();

    fireEvent.click(await pickOption("agent-z"));

    // 切换已生效（"发给谁" 的文案由 i18n 模板渲染，共享 mock 只回键 → 用选择器
    // 自身的选中态 + 真实发送目标来证）。
    expect(await chosenAfterReopen("agent-z")).toBe(true);
    expect(screen.getByTestId("quick-input-target")).toBeInTheDocument();
    fireEvent.keyDown(document.body, { key: "Escape" });
    const { input, send } = {
      input: screen.getByLabelText("projects.quickInputPlaceholder"),
      send: screen.getByRole("button", { name: /projects\.quickInputSend/ }),
    };
    fireEvent.change(input, { target: { value: "hi" } });
    fireEvent.click(send);
    await waitFor(() => expect(MockWebSocket.instances.length).toBe(1));
    expect(MockWebSocket.instances[0].url).toContain(
      "/api/agents/agent-z/chat/ws",
    );
    expect(setItem).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  it("AC-D2-3/4: 换人后的提交发给所选收件人，且仍不传 thread_id", async () => {
    routes["/projects/p1/members"] = shuffledMembers;
    const { input, send } = await openWithPicker();

    fireEvent.click(screen.getByTestId("quick-input-recipient-trigger"));
    fireEvent.click(
      await screen.findByTestId("quick-input-recipient-option-agent-b"),
    );
    fireEvent.change(input, { target: { value: "发给 b" } });
    fireEvent.click(send);

    await waitFor(() => expect(MockWebSocket.instances.length).toBe(1));
    const socket = MockWebSocket.instances[0];
    expect(socket.url).toContain("/api/agents/agent-b/chat/ws");
    act(() => socket.open());
    // 沿用 G3-Q1：每次提交新建会话 → 不带 thread_id。
    // ★ 形态调整（T-WS-FE ③ 的必然结果，**不弱化**）：帧体新增 `project_id`
    //   ⇒ 原「两键深相等」不再成立；改为**枚举全部键**（任何多余/缺失键都会红）+ 逐字段值。
    expect(Object.keys(socket.lastSent()).sort()).toEqual([
      "project_id",
      "text",
      "type",
    ]);
    expect(socket.lastSent()).toMatchObject({
      type: "user_turn",
      text: "发给 b",
      project_id: PROJECT,
    });
    expect(Object.keys(socket.lastSent())).not.toContain("thread_id");

    // 第二次发送：换回另一个收件人 → 仍不带 thread_id（各建一条会话）。
    act(() => socket.emit({ type: "done" }));
    fireEvent.click(screen.getByTestId("quick-input-recipient-trigger"));
    fireEvent.click(
      await screen.findByTestId("quick-input-recipient-option-agent-a"),
    );
    fireEvent.change(input, { target: { value: "发给 a" } });
    fireEvent.click(send);
    await waitFor(() => expect(MockWebSocket.instances.length).toBe(2));
    const second = MockWebSocket.instances[1];
    expect(second.url).toContain("/api/agents/agent-a/chat/ws");
    act(() => second.open());
    expect(Object.keys(second.lastSent())).not.toContain("thread_id");
  });

  it("AC-D2-5: 未持久 —— 重挂载回到默认（agent-a）", async () => {
    routes["/projects/p1/members"] = shuffledMembers;
    const first = render(<QuickInput projectId={PROJECT} />);
    await waitFor(() =>
      expect(screen.getByTestId("quick-input-recipient-trigger")).toBeTruthy(),
    );
    fireEvent.click(screen.getByTestId("quick-input-recipient-trigger"));
    fireEvent.click(
      await screen.findByTestId("quick-input-recipient-option-agent-z"),
    );
    // 切换已生效（文案由 i18n 模板渲染，共享 mock 只回键 → 用选中态证）。
    expect(await chosenAfterReopen("agent-z")).toBe(true);
    first.unmount();

    render(<QuickInput projectId={PROJECT} />);
    await waitFor(() =>
      expect(screen.getByTestId("quick-input-recipient-trigger")).toBeTruthy(),
    );
    // 重挂载后回到确定性首条（未持久化任何选择）。
    await pickOption("agent-a");
    expect(isChosen("agent-a")).toBe(true);
  });

  it("AC-D2-6: quick-input-target 文案含所选 agent 的 subject_id", async () => {
    routes["/projects/p1/members"] = shuffledMembers;
    await openWithPicker();

    const target = screen.getByTestId("quick-input-target");
    expect(target).toHaveTextContent("projects.quickInputTarget");
    // 文案由 i18n 模板渲染（共享 mock 不插值）→ 断言 testid 存在 + 选项可定位。
    fireEvent.click(screen.getByTestId("quick-input-recipient-trigger"));
    expect(
      await screen.findByTestId("quick-input-recipient-option-agent-a"),
    ).toHaveTextContent("agent-a");
  });

  it("PLAN §2.1: 键入过滤（大小写不敏感子串）；无结果 → quickInputRecipientEmpty", async () => {
    routes["/projects/p1/members"] = shuffledMembers;
    await openWithPicker();

    fireEvent.click(screen.getByTestId("quick-input-recipient-trigger"));
    const filter = await screen.findByTestId("quick-input-recipient-filter");
    fireEvent.change(filter, { target: { value: "AGENT-B" } });

    expect(
      screen.getByTestId("quick-input-recipient-option-agent-b"),
    ).toBeTruthy();
    expect(
      screen.queryByTestId("quick-input-recipient-option-agent-a"),
    ).toBeNull();
    expect(
      screen.queryByTestId("quick-input-recipient-option-agent-z"),
    ).toBeNull();

    fireEvent.change(filter, { target: { value: "nope" } });
    expect(screen.getByTestId("quick-input-recipient-empty")).toHaveTextContent(
      "projects.quickInputRecipientEmpty",
    );
  });

  it("R10: 0 个 agent → 选择器不渲染 + quick-input-no-agent", async () => {
    routes["/projects/p1/members"] = () => [userMember()];
    await open();

    await waitFor(() =>
      expect(screen.getByTestId("quick-input-no-agent")).toHaveTextContent(
        "projects.quickInputNoAgent",
      ),
    );
    expect(screen.queryByTestId("quick-input-recipient-trigger")).toBeNull();
  });

  it("R14 / 裁定 A①: 选中的 agent 无权访问（4003）→ 显式失败 + 保留输入（不预判）", async () => {
    routes["/projects/p1/members"] = shuffledMembers;
    const { input, send } = await openWithPicker();

    // 选择器**不预判**访问权：agent-z 照常可选。
    fireEvent.click(screen.getByTestId("quick-input-recipient-trigger"));
    fireEvent.click(
      await screen.findByTestId("quick-input-recipient-option-agent-z"),
    );
    fireEvent.change(input, { target: { value: "保留我" } });
    fireEvent.click(send);

    await waitFor(() => expect(MockWebSocket.instances.length).toBe(1));
    const socket = MockWebSocket.instances[0];
    expect(socket.url).toContain("/api/agents/agent-z/chat/ws");
    act(() => socket.open());
    // 服务端 assert_agent_access 拒绝（预期路径）。
    act(() => socket.serverClose(4003));

    await waitFor(() =>
      expect(screen.getByTestId("quick-input-failed")).toBeInTheDocument(),
    );
    expect(input).toHaveValue("保留我");
    // 仍可重选收件人（失败不锁死选择器）。
    expect(screen.getByTestId("quick-input-recipient-trigger")).toBeTruthy();
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

/* ------------------------------------------------------------------ *
 * D1 自适应软换行（PLAN §1 / §1.1 / §13 RQ-9 / AC-D1-1 · AC-D1-2/3/4）
 * ★ AC-D1-4「不得单行横向滚动」是**真机项**：jsdom 不做布局
 *   （scrollWidth/scrollHeight 恒 0），故此文件只留**代理判据**
 *   （元素必须是 TEXTAREA + autoSize 逐字存在），真机数字由浏览器实测。
 * ------------------------------------------------------------------ */
const SOURCE = readFileSync(resolve(__dirname, "QuickInput.tsx"), "utf8");

/**
 * RQ-9 检出辅助：`autoSize` 必须**逐字** `minRows: 1, maxRows: 6`，且不得出现
 * 固定高度写法 `rows={`、`onPressEnter`（TextArea 无此 prop）、手写高度。
 * 判别性对照（③）用**同一套**辅助函数喂入已知错误输入 → 必须失败。
 */
function assertAutoSize(source: string) {
  expect(source).toContain("Input.TextArea");
  expect(source).toContain("autoSize={{ minRows: 1, maxRows: 6 }}");
  expect(source).not.toMatch(/\brows=\{/);
  expect(source).not.toContain("onPressEnter");
  expect(source).not.toContain("adjustHeight");
}

describe("D1 自适应软换行（AC-D1-1 · AC-D1-2 · AC-D1-3 · RQ-9）", () => {
  it("AC-D1-3 代理判据：长文本仍在 TEXTAREA 元素上（单行 input 不可能软换行）", async () => {
    const { input } = await open();
    const el = input as HTMLElement;
    expect(el).toBeTruthy();
    // ★ 单行 <input> 永远只横向滚动 → 该缺陷类被本条排除。
    expect(el.tagName).toBe("TEXTAREA");
    expect(el.tagName).not.toBe("INPUT");
    fireEvent.change(el, { target: { value: "软换行".repeat(80) } });
    expect(el.tagName).toBe("TEXTAREA");
  });

  it("⑬/RQ-9①：autoSize 逐字 minRows 1 / maxRows 6；无 rows= / onPressEnter / adjustHeight", () => {
    assertAutoSize(SOURCE);
  });

  it("③ 判别性对照（可复跑 · L15 已知错误输入必红）：maxRows=99 / rows={4} / 残留 onPressEnter 都要失败", () => {
    // 已知正确输入 → 绿（同一套辅助函数）。
    expect(() => assertAutoSize(SOURCE)).not.toThrow();
    // 已知错误输入 1：maxRows 写错（封顶失效）。
    expect(() =>
      assertAutoSize(SOURCE.replace("maxRows: 6", "maxRows: 99")),
    ).toThrow();
    // 已知错误输入 2：固定高度（多行但不自适应）。
    expect(() =>
      assertAutoSize(
        SOURCE.replace("<Input.TextArea", "<Input.TextArea rows={4}"),
      ),
    ).toThrow();
    // 已知错误输入 3：残留 TextArea 不支持的 onPressEnter。
    expect(() =>
      assertAutoSize(`${SOURCE}\nconst legacy = (p) => p.onPressEnter;\n`),
    ).toThrow();
  });

  it("AC-D1-2：Enter 发送；Shift+Enter 只换行、不发送", async () => {
    const { input } = await open();
    await screen.findByTestId("quick-input-target");
    const el = input as HTMLTextAreaElement;

    fireEvent.change(el, { target: { value: "第一行" } });
    // Shift+Enter = 换行（默认行为），**不得**触发发送。
    fireEvent.keyDown(el, { key: "Enter", shiftKey: true });
    expect(MockWebSocket.instances).toHaveLength(0);

    // Enter = 发送。
    fireEvent.keyDown(el, { key: "Enter" });
    await waitFor(() => expect(MockWebSocket.instances).toHaveLength(1));
  });
});

describe("批次十 · WS 项目上下文（T-WS-FE）", () => {
  it("★ 项目页发送的 user_turn 帧【带】project_id（贯通 QuickInput 的 projectId）", async () => {
    const { socket } = await submit("你好");
    const frame = JSON.parse(String(socket.sent[0]));
    expect(frame.type).toBe("user_turn");
    expect(frame.project_id).toBe(PROJECT);
    // 既有约定不变：仍不传 thread_id（服务端推导会话）。
    expect(frame).not.toHaveProperty("thread_id");
  });
});
