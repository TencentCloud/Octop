import { act, renderHook, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import type { TFunction } from "i18next";
import { useChatSend } from "./useChatSend";
import * as chatStore from "./chatStore";
import { EMPTY_CHAT_SESSION_KEY, PENDING_THREAD_ID } from "../constants";

const navigateMock = vi.fn();

vi.mock("react-router-dom", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-router-dom")>()),
  useNavigate: () => navigateMock,
}));

vi.mock("./chatStore", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./chatStore")>()),
  sendTurn: vi.fn(),
}));

function wrapper({ children }: { children: ReactNode }) {
  return (
    <MemoryRouter initialEntries={["/embed/chat/agent-a"]}>
      {children}
    </MemoryRouter>
  );
}

afterEach(() => {
  for (const id of [EMPTY_CHAT_SESSION_KEY, PENDING_THREAD_ID, "thr_created"]) {
    chatStore.removeSession(id);
  }
  vi.clearAllMocks();
});

it("creates the first thread and sends the first turn without leaving the embedded entry", async () => {
  const createSession = vi.fn(() => ({
    session: {
      id: PENDING_THREAD_ID,
      name: "New Chat",
      threadId: "",
      updatedAt: null,
      channelType: "dashboard",
    },
    resolvedId: Promise.resolve("thr_created"),
  }));
  const { result } = renderHook(
    () =>
      useChatSend({
        resolvedAgentId: "agent-a",
        activeThreadId: null,
        sessions: [],
        messagesLength: 0,
        selectedModel: null,
        selectedConnectors: [],
        selectedKnowledgeBaseIds: [],
        reasoningMode: "auto",
        reasoningEffort: null,
        sendMessage: vi.fn(),
        createSession,
        renameSession: vi.fn(),
        t: ((key: string) => key) as TFunction,
      }),
    { wrapper },
  );

  await act(async () => {
    expect(result.current.handleSend("First embedded message")).toBe(true);
  });
  expect(createSession).toHaveBeenCalledOnce();
  expect(navigateMock).toHaveBeenCalledWith(
    `/embed/chat/agent-a/${PENDING_THREAD_ID}`,
  );
  await waitFor(() => {
    expect(navigateMock).toHaveBeenLastCalledWith(
      "/embed/chat/agent-a/thr_created",
      { replace: true },
    );
  });
  expect(vi.mocked(chatStore.sendTurn).mock.calls[0].slice(0, 3)).toEqual([
    "thr_created",
    "First embedded message",
    "agent-a",
  ]);
});
