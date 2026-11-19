import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { octopThreadsApi } from "../../../../api/modules/octopThreads";
import * as chatStore from "../../../Chat/hooks/chatStore";
import CloudAiPanel from "./CloudAiPanel";

vi.mock("../../../../context/AgentContext", () => ({
  useAgent: () => ({ agents: [] }),
}));
vi.mock("../../../../components/AssistantFrame/AssistantFrame", () => ({
  default: ({
    children,
    headerExtra,
  }: {
    children: ReactNode;
    headerExtra: ReactNode;
  }) => (
    <section>
      {headerExtra}
      {children}
    </section>
  ),
  readAssistantPlacement: () => "right",
}));
vi.mock("../../../../components/Markdown/LazyMarkdown", () => ({
  default: ({ content }: { content: string }) => <span>{content}</span>,
}));

const AGENT = "cloud-agent";
const OLD_THREAD = "thr_existing";
const NEW_THREAD = "thr_created";
const PIN_KEY = "octop:cloud-ai-thread";
const oldRow = {
  thread_id: OLD_THREAD,
  title: "Old conversation",
  channel_type: "dashboard",
  session_key: "dashboard",
  last_active: 10,
  created_at: 1,
  has_messages: true,
};

beforeEach(() => {
  localStorage.setItem(PIN_KEY, JSON.stringify({ [AGENT]: OLD_THREAD }));
  vi.spyOn(octopThreadsApi, "list").mockResolvedValue([oldRow]);
  vi.spyOn(octopThreadsApi, "history").mockImplementation(
    async (_agent, thread) => ({
      thread_id: thread,
      messages:
        thread === OLD_THREAD
          ? [
              {
                id: "old-message",
                role: "user",
                content: "Old transcript",
                timestamp: 1,
              },
            ]
          : [],
      has_more: false,
    }),
  );
  vi.spyOn(chatStore, "attachThread").mockResolvedValue(undefined);
  vi.spyOn(chatStore, "sendTurn").mockResolvedValue(undefined);
});

afterEach(() => {
  cleanup();
  for (const id of [OLD_THREAD, NEW_THREAD, "__empty__"])
    chatStore.removeSession(id);
  localStorage.removeItem(PIN_KEY);
  vi.restoreAllMocks();
});

async function renderPanel() {
  render(
    <CloudAiPanel
      instance={null}
      onClose={() => {}}
      preferredAgentId={AGENT}
    />,
  );
  await screen.findByText("Old transcript");
}

it("blocks click, Enter and quick prompts until the new conversation is active", async () => {
  let complete!: (value: { thread_id: string; session_key: string }) => void;
  const createThread = vi.spyOn(octopThreadsApi, "create").mockReturnValueOnce(
    new Promise((resolve) => {
      complete = resolve;
    }),
  );
  await renderPanel();

  fireEvent.change(screen.getByRole("textbox"), {
    target: { value: "My draft" },
  });
  const newChat = screen.getByRole("button", { name: "新建对话" });
  fireEvent.click(newChat);

  const send = screen.getByRole("button", { name: "发送" });
  const quickPrompt = screen.getByRole("button", { name: "诊断报告" });
  expect(send).toBeDisabled();
  expect(quickPrompt).toBeDisabled();
  expect(newChat).toBeDisabled();
  fireEvent.click(newChat);
  fireEvent.click(send);
  fireEvent.click(quickPrompt);
  fireEvent.keyDown(screen.getByRole("textbox"), {
    key: "Enter",
    code: "Enter",
  });
  expect(createThread).toHaveBeenCalledTimes(1);
  expect(createThread).toHaveBeenCalledWith(AGENT, { rebind: false });
  expect(chatStore.sendTurn).not.toHaveBeenCalled();

  await act(async () => {
    complete({ thread_id: NEW_THREAD, session_key: "dashboard" });
  });

  expect(screen.getByRole("textbox")).toHaveValue("My draft");
  expect(send).toBeEnabled();
  fireEvent.click(send);
  expect(
    vi
      .mocked(chatStore.sendTurn)
      .mock.calls.map((args) => [args[0], args[1], args[7]]),
  ).toEqual([[NEW_THREAD, "My draft", NEW_THREAD]]);
});

it("keeps sending blocked on creation failure and retries creation", async () => {
  const createThread = vi
    .spyOn(octopThreadsApi, "create")
    .mockRejectedValueOnce(new Error("Connection interrupted"))
    .mockResolvedValueOnce({ thread_id: NEW_THREAD, session_key: "dashboard" });
  await renderPanel();
  fireEvent.change(screen.getByRole("textbox"), {
    target: { value: "My draft" },
  });
  fireEvent.click(screen.getByRole("button", { name: "新建对话" }));

  const alert = await screen.findByRole("alert");
  expect(alert).toHaveTextContent("Connection interrupted");
  expect(screen.getByRole("button", { name: "发送" })).toBeDisabled();
  expect(chatStore.sendTurn).not.toHaveBeenCalled();

  fireEvent.click(screen.getByRole("button", { name: "重试" }));
  const send = screen.getByRole("button", { name: "发送" });
  await waitFor(() => expect(send).toBeEnabled());
  expect(createThread).toHaveBeenCalledTimes(2);
  fireEvent.click(send);
  expect(vi.mocked(chatStore.sendTurn).mock.calls[0][7]).toBe(NEW_THREAD);
});
