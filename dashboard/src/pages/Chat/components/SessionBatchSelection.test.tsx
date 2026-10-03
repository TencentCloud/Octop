import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import type { ModalFuncProps } from "antd";
import type { OctopAgent } from "../../../context/AgentContext";
import en from "../../../locales/en.json";
import { showConfirmModal } from "../../../utils/confirmModal";
import { message } from "../../../utils/antdMessage";
import {
  deleteSessions,
  resetSessionStoreForTests,
  useSessions,
} from "../hooks/useSessions";
import SessionList from "./SessionList";
import MinimalAgentSessionNav from "./MinimalAgentSessionNav";

const listMock = vi.fn();
const deleteMock = vi.fn();
const selectMock = vi.fn();

vi.mock("../../../api/modules/octopThreads", async (importOriginal) => ({
  ...(await importOriginal<
    typeof import("../../../api/modules/octopThreads")
  >()),
  octopThreadsApi: {
    list: (...args: unknown[]) => listMock(...args),
    delete: (...args: unknown[]) => deleteMock(...args),
  },
}));
vi.mock("../../../utils/confirmModal", () => ({ showConfirmModal: vi.fn() }));
vi.mock("../../../utils/antdMessage", () => ({
  message: { success: vi.fn(), error: vi.fn() },
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown> | string) => {
      const value = key
        .split(".")
        .reduce<unknown>(
          (obj, part) => (obj as Record<string, unknown>)?.[part],
          en,
        );
      return (typeof value === "string" ? value : key).replace(
        /\{\{(\w+)\}\}/g,
        (_, name: string) =>
          String(typeof options === "object" ? options[name] : ""),
      );
    },
  }),
}));

function agent(id: number): OctopAgent {
  return {
    id,
    agent_id: `agent-${id}`,
    name: `Expert ${id}`,
    state: "running",
    description: null,
    persona_mbti: null,
    default_model: null,
    system_prompt: null,
    template_name: null,
    last_error: null,
    icon: null,
    icon_name: null,
    icon_url: null,
    color: null,
    config: {},
  };
}
const agents = [agent(1), agent(2)];
function row(id: string) {
  return { thread_id: id, title: id, last_active: 1, has_messages: true };
}
let rows: Record<string, ReturnType<typeof row>[]>;

function Classic({ agentId = "agent-1" }: { agentId?: string }) {
  const { sessions, hasMore, loadingMore, loadMoreSessions, fetchAllSessions } =
    useSessions(agentId);
  return (
    <SessionList
      agents={agents}
      activeAgentId={agentId}
      activeId={null}
      sessions={sessions}
      hasMore={hasMore}
      loadingMore={loadingMore}
      onLoadMore={loadMoreSessions}
      onFetchAllSessions={fetchAllSessions}
      onSelect={selectMock}
      onAgentSelect={vi.fn()}
      onNewChat={vi.fn()}
      onDelete={vi.fn()}
      onBatchDelete={deleteSessions}
      onRename={vi.fn()}
      onPin={vi.fn()}
      onFork={vi.fn()}
    />
  );
}

function Minimal() {
  return (
    <MinimalAgentSessionNav
      agents={agents}
      activeAgentId="agent-1"
      activeId={null}
      activeSessions={[]}
      onSelect={selectMock}
      onAgentSelect={vi.fn()}
      onNewChat={vi.fn()}
      onDeleteActive={vi.fn()}
      onBatchDelete={deleteSessions}
      onRenameActive={vi.fn()}
      onPinActive={vi.fn()}
      onFork={vi.fn()}
    />
  );
}

function confirmation(): ModalFuncProps {
  return vi.mocked(showConfirmModal).mock.lastCall![0];
}

beforeEach(() => {
  vi.clearAllMocks();
  resetSessionStoreForTests();
  localStorage.clear();
  rows = {
    "agent-1": [row("Alpha"), row("Beta"), row("Gamma")],
    "agent-2": [row("Other")],
  };
  listMock.mockImplementation(async (id: string, limit: number) =>
    rows[id].slice(0, limit),
  );
  deleteMock.mockImplementation(async (agentId: string, id: string) => {
    rows[agentId] = rows[agentId].filter((item) => item.thread_id !== id);
  });
});
afterEach(() => resetSessionStoreForTests());

describe.each([
  ["classic", Classic],
  ["minimal", Minimal],
] as const)("%s conversation selection", (_name, Layout) => {
  async function startSelecting() {
    render(
      <MemoryRouter>
        <Layout />
      </MemoryRouter>,
    );
    await screen.findByText("Alpha");
    // Minimal has multiple expert folders; operate on Expert 1 only.
    const root = screen.getByText("Alpha").closest("section") ?? document.body;
    await userEvent.click(
      within(root as HTMLElement).getByRole("button", {
        name: "Select conversations",
      }),
    );
  }

  it("requires confirmation and supports checkbox, row and keyboard selection without opening chats", async () => {
    await startSelecting();
    expect(screen.getByRole("button", { name: "Delete (0)" })).toBeDisabled();
    await userEvent.click(
      screen.getByRole("checkbox", { name: "Select conversation Alpha" }),
    );
    await userEvent.click(screen.getByText("Beta"));
    const beta = screen.getByRole("checkbox", {
      name: "Select conversation Beta",
    });
    expect(beta).toBeChecked();
    beta.focus();
    await userEvent.keyboard(" ");
    expect(beta).not.toBeChecked();
    await userEvent.keyboard(" ");
    expect(selectMock).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Delete (2)" }));
    expect(confirmation().title).toBe(
      "Delete 2 selected conversations? This cannot be undone.",
    );
    expect(deleteMock).not.toHaveBeenCalled();
    await act(async () => {
      await confirmation().onOk?.();
    });
    expect(deleteMock.mock.calls).toEqual([
      ["agent-1", "Alpha"],
      ["agent-1", "Beta"],
    ]);
    expect(screen.queryByText("Alpha")).not.toBeInTheDocument();
    expect(screen.queryByText("Beta")).not.toBeInTheDocument();
    expect(screen.getByText("Gamma")).toBeInTheDocument();
    expect(rows["agent-2"]).toHaveLength(1);
    expect(message.success).toHaveBeenCalledWith("Deleted 2 conversations");
  });

  it("keeps failed conversations selected and retries only those failures", async () => {
    const remove = deleteMock.getMockImplementation()!;
    deleteMock.mockImplementation(async (agentId, id) => {
      if (id === "Beta") throw new Error("forbidden");
      return remove(agentId, id);
    });
    await startSelecting();
    await userEvent.click(
      screen.getByRole("checkbox", { name: "Select listed conversations" }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Delete (3)" }));
    await act(async () => {
      await confirmation().onOk?.();
    });
    expect(
      screen.getByRole("checkbox", { name: "Select conversation Beta" }),
    ).toBeChecked();
    expect(screen.queryByText("Alpha")).not.toBeInTheDocument();
    expect(message.error).toHaveBeenCalledWith(
      "Deleted 2 conversations; 1 failed. Failed conversations remain selected for retry.",
    );
    deleteMock.mockImplementation(remove);
    await userEvent.click(screen.getByRole("button", { name: "Delete (1)" }));
    await act(async () => {
      await confirmation().onOk?.();
    });
    expect(deleteMock.mock.calls.map((args) => args[1])).toEqual([
      "Gamma",
      "Beta",
      "Alpha",
      "Beta",
    ]);
    expect(rows["agent-1"]).toEqual([]);
  });

  it("can exit selection without deleting anything", async () => {
    await startSelecting();
    await userEvent.click(
      screen.getByRole("checkbox", { name: "Select listed conversations" }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(deleteMock).not.toHaveBeenCalled();
    expect(showConfirmModal).not.toHaveBeenCalled();
  });

  it("disables selection and prevents duplicate confirmation while deletion is pending", async () => {
    let finish!: () => void;
    deleteMock.mockImplementationOnce(
      () =>
        new Promise<void>((resolve) => {
          finish = resolve;
        }),
    );
    await startSelecting();
    await userEvent.click(
      screen.getByRole("checkbox", { name: "Select conversation Alpha" }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Delete (1)" }));
    let pending: Promise<unknown>;
    await act(async () => {
      pending = confirmation().onOk?.();
    });
    expect(
      screen.getByRole("checkbox", { name: "Select conversation Beta" }),
    ).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
    await act(async () => {
      await confirmation().onOk?.();
    });
    expect(deleteMock).toHaveBeenCalledTimes(1);
    await act(async () => {
      finish();
      await pending;
    });
  });
});

it("limits a classic search selection to matching, currently listed conversations", async () => {
  render(
    <MemoryRouter>
      <Classic />
    </MemoryRouter>,
  );
  await screen.findByText("Alpha");
  await userEvent.click(
    screen.getByRole("button", { name: "Select conversations" }),
  );
  await userEvent.click(
    screen.getByRole("checkbox", { name: "Select listed conversations" }),
  );
  fireEvent.change(screen.getByRole("searchbox"), {
    target: { value: "Beta" },
  });
  await userEvent.click(screen.getByRole("button", { name: "Delete (1)" }));
  await act(async () => {
    await confirmation().onOk?.();
  });
  expect(deleteMock.mock.calls).toEqual([["agent-1", "Beta"]]);
  expect(rows["agent-1"].map((r) => r.thread_id)).toEqual(["Alpha", "Gamma"]);
});

it("resets selection when switching the classic expert", async () => {
  const { rerender } = render(
    <MemoryRouter>
      <Classic />
    </MemoryRouter>,
  );
  await screen.findByText("Alpha");
  await userEvent.click(
    screen.getByRole("button", { name: "Select conversations" }),
  );
  await userEvent.click(
    screen.getByRole("checkbox", { name: "Select listed conversations" }),
  );
  rerender(
    <MemoryRouter>
      <Classic agentId="agent-2" />
    </MemoryRouter>,
  );
  await screen.findByText("Other");
  expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  expect(deleteMock).not.toHaveBeenCalled();
});

it("keeps Show more reachable after deleting a page when its refill failed", async () => {
  rows["agent-1"] = Array.from({ length: 11 }, (_, i) => row(`Thread ${i}`));
  render(
    <MemoryRouter>
      <Classic />
    </MemoryRouter>,
  );
  await screen.findByText("Thread 0");
  await userEvent.click(
    screen.getByRole("button", { name: "Select conversations" }),
  );
  await userEvent.click(
    screen.getByRole("checkbox", { name: "Select listed conversations" }),
  );
  listMock.mockRejectedValueOnce(new Error("network"));
  await userEvent.click(screen.getByRole("button", { name: "Delete (10)" }));
  await act(async () => {
    await confirmation().onOk?.();
  });
  await userEvent.click(screen.getByRole("button", { name: "Show more" }));
  await waitFor(() =>
    expect(screen.getByText("Thread 10")).toBeInTheDocument(),
  );
});
