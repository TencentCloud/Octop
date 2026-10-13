import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  octopThreadsApi,
  type OctopThread,
  type OctopThreadHistory,
} from "../../../api/modules/octopThreads";
import ConversationRecords from "./ConversationRecords";

const toast = vi.hoisted(() => ({ error: vi.fn() }));
vi.mock("@/utils/antdMessage", () => ({ message: toast }));
vi.mock("../../../api/modules/octopThreads", () => ({
  CHAT_HISTORY_PAGE_SIZE: 25,
  octopThreadsApi: { list: vi.fn(), history: vi.fn() },
}));
vi.mock("../../../hooks/useServerTimezone", () => ({
  useServerTimezone: () => "UTC",
}));
vi.mock("../../../components/Markdown/LazyMarkdown", () => ({
  default: ({ content }: { content: string }) => <p>{content}</p>,
}));
vi.mock("react-i18next", () => {
  const t = (key: string) => key;
  return { useTranslation: () => ({ t }) };
});

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function thread(id: string): OctopThread {
  return {
    thread_id: id,
    title: `Conversation ${id}`,
    channel_type: "dashboard",
    session_key: id,
    created_at: 100,
    last_active: 100,
  };
}

function history(
  id: string,
  text: string,
  hasMore = false,
): OctopThreadHistory {
  return {
    thread_id: id,
    messages: [{ id: text, role: "assistant", content: text }],
    has_more: hasMore,
  };
}

const api = vi.mocked(octopThreadsApi);

async function openConversation(
  user: ReturnType<typeof userEvent.setup>,
  id: string,
) {
  const row = await screen.findByRole("row", {
    name: new RegExp(`Conversation ${id}`),
  });
  await user.click(within(row).getByRole("button", { name: "common.view" }));
  await waitFor(() =>
    expect(api.history).toHaveBeenCalledWith("agent-1", id, {
      limit: 25,
      offset: 0,
    }),
  );
}

async function closeConversation(user: ReturnType<typeof userEvent.setup>) {
  await user.click(
    within(screen.getByRole("dialog")).getByRole("button", { name: "Close" }),
  );
  await waitFor(() =>
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  api.history.mockReset();
  api.list.mockResolvedValue([thread("A"), thread("B")]);
  const getComputedStyle = window.getComputedStyle.bind(window);
  vi.spyOn(window, "getComputedStyle").mockImplementation((element) =>
    getComputedStyle(element),
  );
});

afterEach(() => vi.mocked(window.getComputedStyle).mockRestore());

describe("conversation history request ownership", () => {
  it("keeps B's detail when a closed A request finishes later", async () => {
    const old = deferred<OctopThreadHistory>();
    api.history.mockImplementation(async (_agentId, id) =>
      id === "A" ? old.promise : history("B", "B current answer"),
    );
    const user = userEvent.setup();
    render(<ConversationRecords agentId="agent-1" />);
    await openConversation(user, "A");
    await closeConversation(user);
    await openConversation(user, "B");
    expect(await screen.findByText("B current answer")).toBeInTheDocument();
    await act(async () => old.resolve(history("A", "A stale answer")));
    expect(
      within(screen.getByRole("dialog")).getByText("B current answer"),
    ).toBeInTheDocument();
    expect(screen.queryByText("A stale answer")).not.toBeInTheDocument();
  });

  it("does not prepend A's pending older page to B", async () => {
    const oldPage = deferred<OctopThreadHistory>();
    api.history.mockImplementation(async (_agentId, id, options) => {
      if (id === "B") return history("B", "B current answer");
      return options?.offset
        ? oldPage.promise
        : history("A", "A recent answer", true);
    });
    const user = userEvent.setup();
    render(<ConversationRecords agentId="agent-1" />);
    await openConversation(user, "A");
    await user.click(
      await screen.findByRole("button", { name: "memory.loadEarlierMessages" }),
    );
    await waitFor(() =>
      expect(api.history).toHaveBeenCalledWith("agent-1", "A", {
        limit: 25,
        offset: 25,
      }),
    );
    await closeConversation(user);
    await openConversation(user, "B");
    expect(await screen.findByText("B current answer")).toBeInTheDocument();
    await act(async () => oldPage.resolve(history("A", "A old page")));
    expect(screen.queryByText("A old page")).not.toBeInTheDocument();
    expect(
      within(screen.getByRole("dialog")).getByText("B current answer"),
    ).toBeInTheDocument();
  });

  it("loads and prepends the current conversation's earlier messages", async () => {
    api.history.mockImplementation(async (_agentId, id, options) =>
      history(
        id,
        options?.offset ? "A earlier answer" : "A recent answer",
        !options?.offset,
      ),
    );
    const user = userEvent.setup();
    render(<ConversationRecords agentId="agent-1" />);
    await openConversation(user, "A");
    await user.click(
      await screen.findByRole("button", { name: "memory.loadEarlierMessages" }),
    );
    expect(await screen.findByText("A earlier answer")).toBeInTheDocument();
    expect(screen.getByText("A recent answer")).toBeInTheDocument();
  });

  it.each(["detail", "page"])(
    "ignores a closed conversation's %s failure",
    async (kind) => {
      const old = deferred<OctopThreadHistory>();
      api.history.mockImplementation(async (_agentId, id, options) => {
        if (id === "B") return history("B", "B current answer");
        if (kind === "detail" || options?.offset) return old.promise;
        return history("A", "A recent answer", true);
      });
      const user = userEvent.setup();
      render(<ConversationRecords agentId="agent-1" />);
      await openConversation(user, "A");
      if (kind === "page") {
        await user.click(
          await screen.findByRole("button", {
            name: "memory.loadEarlierMessages",
          }),
        );
      }
      await closeConversation(user);
      await openConversation(user, "B");
      expect(await screen.findByText("B current answer")).toBeInTheDocument();
      await act(async () => old.reject(new Error("old request failed")));
      expect(toast.error).not.toHaveBeenCalled();
      expect(screen.getByText("B current answer")).toBeInTheDocument();
    },
  );

  it("distinguishes reopening A from its previous pending request", async () => {
    const old = deferred<OctopThreadHistory>();
    api.history.mockResolvedValue(history("A", "A current answer"));
    api.history.mockReturnValueOnce(old.promise);
    const user = userEvent.setup();
    render(<ConversationRecords agentId="agent-1" />);
    await openConversation(user, "A");
    await closeConversation(user);
    await openConversation(user, "A");
    expect(await screen.findByText("A current answer")).toBeInTheDocument();
    await act(async () => old.resolve(history("A", "A stale answer")));
    expect(screen.getByText("A current answer")).toBeInTheDocument();
    expect(screen.queryByText("A stale answer")).not.toBeInTheDocument();
  });

  it.each(["resolve", "reject"])(
    "keeps B loading when stale A requests %s",
    async (outcome) => {
      const old = deferred<OctopThreadHistory>();
      const current = deferred<OctopThreadHistory>();
      api.history.mockImplementation(async (_agentId, id) =>
        id === "A" ? old.promise : current.promise,
      );
      const user = userEvent.setup();
      render(<ConversationRecords agentId="agent-1" />);
      await openConversation(user, "A");
      await closeConversation(user);
      await openConversation(user, "B");
      await act(async () => {
        if (outcome === "resolve") old.resolve(history("A", "A stale answer"));
        else old.reject(new Error("old request failed"));
      });
      expect(
        screen.getByRole("dialog").querySelector(".ant-spin-spinning"),
      ).not.toBeNull();
      expect(screen.queryByText("A stale answer")).not.toBeInTheDocument();
      expect(toast.error).not.toHaveBeenCalled();
      await act(async () => current.resolve(history("B", "B current answer")));
      expect(screen.getByText("B current answer")).toBeInTheDocument();
    },
  );

  it.each(["close", "unmount", "agent change"])(
    "ignores errors after %s",
    async (action) => {
      const pending = deferred<OctopThreadHistory>();
      api.history.mockReturnValue(pending.promise);
      const user = userEvent.setup();
      const view = render(<ConversationRecords agentId="agent-1" />);
      await openConversation(user, "A");
      if (action === "close") await closeConversation(user);
      else if (action === "unmount") view.unmount();
      else view.rerender(<ConversationRecords agentId="agent-2" />);
      await act(async () =>
        pending.reject(new Error("inactive request failed")),
      );
      expect(toast.error).not.toHaveBeenCalled();
    },
  );

  it("still reports a current request failure and leaves loading", async () => {
    api.history.mockRejectedValue(new Error("current request failed"));
    const user = userEvent.setup();
    render(<ConversationRecords agentId="agent-1" />);
    await openConversation(user, "A");
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("memory.conversationLoadFailed"),
    );
    expect(
      screen.getByRole("dialog").querySelector(".ant-spin-spinning"),
    ).toBeNull();
    expect(
      screen.getByText("memory.noConversationMessages"),
    ).toBeInTheDocument();
  });
});
