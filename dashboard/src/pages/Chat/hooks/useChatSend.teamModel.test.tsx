import { act, renderHook } from "@testing-library/react";
import type { TFunction } from "i18next";
import { describe, expect, it, vi } from "vitest";
import { useChatSend } from "./useChatSend";
import { useChat } from "./useChat";
import * as chatStore from "./chatStore";

vi.mock("react-router-dom", () => ({ useNavigate: () => vi.fn() }));

describe("queued team model choices", () => {
  it("keeps the current team model and switch when editing and resending", () => {
    const send = vi.spyOn(chatStore, "sendTurn").mockResolvedValue();
    chatStore.appendUserMessage("edit-room", {
      id: "u",
      role: "user",
      content: "old",
      timestamp: 1,
    });
    const { result, unmount } = renderHook(() =>
      useChat("edit-room", null, true),
    );
    act(() => {
      result.current.editAndResend("u", "edited", "", "host", {
        model: "p/current",
        applyModelToTeam: true,
      });
    });
    expect(send.mock.calls[0][6]).toBe("p/current");
    expect(send.mock.calls[0][15]).toBe(true);
    expect(
      chatStore.getSnapshot("edit-room").messages[0].composerContext,
    ).toEqual({ model: "p/current", applyModelToTeam: true });
    unmount();
    chatStore.removeSession("edit-room");
    send.mockRestore();
  });
  it("uses the queued snapshot after the current switch changes", () => {
    const sendMessage = vi.fn();
    const { result, rerender } = renderHook(
      ({ enabled }) =>
        useChatSend({
          resolvedAgentId: "host",
          activeThreadId: "room",
          sessions: [],
          messagesLength: 1,
          selectedModel: "p/current",
          applyModelToTeam: enabled,
          selectedConnectors: [],
          selectedKnowledgeBaseIds: [],
          reasoningMode: "auto",
          reasoningEffort: null,
          sendMessage,
          createSession: vi.fn(),
          renameSession: vi.fn(),
          t: ((key: string) => key) as TFunction,
        }),
      { initialProps: { enabled: true } },
    );
    act(() => {
      result.current.handleSend("first");
    });
    expect(sendMessage.mock.calls[0][9].applyModelToTeam).toBe(true);
    rerender({ enabled: false });
    act(() => {
      result.current.handleSend("queued", undefined, {
        threadId: "other-room",
        agentId: "host",
        modelRef: "p/queued",
        composerContext: { model: "p/queued", applyModelToTeam: true },
      });
    });
    expect(sendMessage.mock.calls[1][4]).toBe("other-room");
    expect(sendMessage.mock.calls[1][5]).toBe("p/queued");
    expect(sendMessage.mock.calls[1][9].applyModelToTeam).toBe(true);
    rerender({ enabled: true });
    act(() => {
      result.current.handleSend("queued off", undefined, {
        composerContext: { model: "p/queued", applyModelToTeam: false },
      });
    });
    expect(sendMessage.mock.calls[2][9].applyModelToTeam).toBe(false);
  });
});
