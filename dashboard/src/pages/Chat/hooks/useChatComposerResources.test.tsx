/**
 * useChatComposerResources.test.tsx — per-expert knowledge base selection.
 *
 * Regression for the "remember KB selection" bug: one global selection array
 * + a touched flag reset on expert switch meant Expert B's selection leaked
 * into (or replaced) Expert A's remembered selection when switching back.
 * Selection is now persisted per expert (chatStorage) and restored on switch.
 */

import { renderHook, waitFor, act } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../../api/modules/connectors", () => ({
  connectorsApi: {
    listInstances: vi.fn().mockResolvedValue([
      {
        status: "active",
        has_credentials: true,
        mcp_server_name: "c1",
        display_name: "C1",
        owner_user_id: 7,
        kind: "mcp",
      },
      {
        status: "active",
        has_credentials: true,
        mcp_server_name: "c2",
        display_name: "C2",
        owner_user_id: 7,
        kind: "mcp",
      },
    ]),
  },
}));
vi.mock("../../../api/modules/provider", () => ({
  providerApi: {
    listResolvedModels: vi.fn().mockResolvedValue([]),
    getActiveModel: vi.fn().mockResolvedValue(null),
  },
}));
vi.mock("../../../api/modules/preferences", () => ({
  preferencesApi: {
    get: vi.fn().mockResolvedValue(null),
    set: vi.fn().mockResolvedValue(undefined),
  },
}));
vi.mock("../../../api/modules/octopThreads", () => ({
  octopThreadsApi: { patch: vi.fn().mockResolvedValue({}) },
}));
vi.mock("../../../api/request", () => ({
  request: vi.fn().mockResolvedValue(null),
}));
vi.mock("../../../api/modules/knowledgeBases", () => ({
  knowledgeBasesApi: {
    getCapability: vi.fn().mockResolvedValue({ usable: true }),
    list: vi.fn().mockResolvedValue([
      { id: "k1", default_open: false, owner_user_id: 7 },
      { id: "k2", default_open: false, owner_user_id: 7 },
      { id: "k3", default_open: false, owner_user_id: 7 },
      { id: "k4", default_open: false, owner_user_id: 7 },
    ]),
  },
}));
vi.mock("../../../hooks/useCurrentUser", () => ({
  useCurrentUser: () => ({ id: 7 }),
}));
vi.mock("../../../context/AgentContext", () => ({
  useAgent: () => ({
    agents: [
      { agent_id: "expertA", knowledge_base_ids: ["k1"] },
      { agent_id: "expertB", knowledge_base_ids: ["k3"] },
      { agent_id: "team", kind: "team", member_ids: ["expertA", "expertB"] },
    ],
  }),
}));

import { useChatComposerResources } from "./useChatComposerResources";
import type { ChatMessage } from "./sseHelpers";

describe("team conversation model selection", () => {
  it("defaults off and isolates the choice across conversations", async () => {
    const { result, rerender } = renderHook(
      ({ threadId }) => useChatComposerResources("team", threadId, "p/chosen"),
      { initialProps: { threadId: "room-a" } },
    );
    await waitFor(() => expect(result.current.modelsReady).toBe(true));
    expect(result.current.applyModelToTeam).toBe(false);
    act(() => result.current.handleApplyModelToTeamChange(true));
    expect(result.current.applyModelToTeam).toBe(true);
    // Navigation resets the visible model without changing the room being left.
    act(() => result.current.resetSelectedModel(null));
    rerender({ threadId: "room-b" });
    expect(result.current.applyModelToTeam).toBe(false);
    rerender({ threadId: "room-a" });
    expect(result.current.applyModelToTeam).toBe(true);
    act(() => result.current.setSelectedModel(null));
    expect(result.current.applyModelToTeam).toBe(false);
    act(() => result.current.setSelectedModel("p/chosen"));
    expect(result.current.applyModelToTeam).toBe(false);
  });

  it("restores the first turn through pending and real threads without leaking to a new chat", async () => {
    const sent: ChatMessage[] = [
      {
        id: "u",
        role: "user",
        content: "hi",
        status: "done",
        timestamp: 1,
        composerContext: { model: "p/chosen", applyModelToTeam: true },
      },
    ];
    const { result, rerender } = renderHook(
      ({
        threadId,
        messages,
      }: {
        threadId: string | null;
        messages: ChatMessage[];
      }) =>
        useChatComposerResources(
          "team",
          threadId,
          "p/chosen",
          null,
          null,
          null,
          null,
          messages,
        ),
      { initialProps: { threadId: null, messages: [] } },
    );
    await waitFor(() => expect(result.current.modelsReady).toBe(true));
    act(() => result.current.handleApplyModelToTeamChange(true));
    expect(result.current.applyModelToTeam).toBe(true);
    rerender({ threadId: "__pending__", messages: sent });
    expect(result.current.applyModelToTeam).toBe(true);
    rerender({ threadId: "room", messages: sent });
    expect(result.current.applyModelToTeam).toBe(true);
    rerender({ threadId: null, messages: [] });
    expect(result.current.applyModelToTeam).toBe(false);
  });

  it("ignores the option for individual experts", async () => {
    const { result, rerender } = renderHook(
      ({ agentId }) => useChatComposerResources(agentId, "room", "p/chosen"),
      { initialProps: { agentId: "team" } },
    );
    await waitFor(() => expect(result.current.modelsReady).toBe(true));
    act(() => result.current.handleApplyModelToTeamChange(true));
    rerender({ agentId: "expertA" });
    expect(result.current.applyModelToTeam).toBe(false);
    act(() => result.current.handleApplyModelToTeamChange(true));
    expect(result.current.applyModelToTeam).toBe(false);
  });
});

beforeEach(() => {
  localStorage.clear();
});

describe("useChatComposerResources — per-expert KB selection", () => {
  it("restores expert A's manual selection after switching A -> B -> A", async () => {
    const threadId = "thread-existing"; // existing session → saved prefs apply
    const { result, rerender } = renderHook(
      ({ agentId }: { agentId: string }) =>
        useChatComposerResources(agentId, threadId),
      { initialProps: { agentId: "expertA" } },
    );

    // A starts with its expert default (k1)
    await waitFor(() =>
      expect(result.current.selectedKnowledgeBaseIds).toEqual(["k1"]),
    );

    // user manually adds k2 in expert A
    act(() => result.current.handleKnowledgeBaseIdsChange(["k1", "k2"]));
    expect(result.current.selectedKnowledgeBaseIds).toEqual(["k1", "k2"]);

    // switch to expert B: B's own default, nothing leaked from A
    rerender({ agentId: "expertB" });
    await waitFor(() =>
      expect(result.current.selectedKnowledgeBaseIds).toEqual(["k3"]),
    );

    // user selects k3+k4 in expert B
    act(() => result.current.handleKnowledgeBaseIdsChange(["k3", "k4"]));

    // switch back to expert A: remembered k1+k2 (was: k3/k4 leak or reset)
    rerender({ agentId: "expertA" });
    await waitFor(() =>
      expect(result.current.selectedKnowledgeBaseIds).toEqual(["k1", "k2"]),
    );

    // and back to B: remembered k3+k4
    rerender({ agentId: "expertB" });
    await waitFor(() =>
      expect(result.current.selectedKnowledgeBaseIds).toEqual(["k3", "k4"]),
    );
  });

  it("does not leak a cleared selection across experts", async () => {
    const threadId = "thread-existing";
    const { result, rerender } = renderHook(
      ({ agentId }: { agentId: string }) =>
        useChatComposerResources(agentId, threadId),
      { initialProps: { agentId: "expertA" } },
    );
    await waitFor(() =>
      expect(result.current.selectedKnowledgeBaseIds).toEqual(["k1"]),
    );

    // user clears A's selection entirely (explicit empty is a choice)
    act(() => result.current.handleKnowledgeBaseIdsChange([]));

    rerender({ agentId: "expertB" });
    await waitFor(() =>
      expect(result.current.selectedKnowledgeBaseIds).toEqual(["k3"]),
    );
    act(() => result.current.handleKnowledgeBaseIdsChange(["k4"]));

    rerender({ agentId: "expertA" });
    await waitFor(() =>
      expect(result.current.selectedKnowledgeBaseIds).toEqual([]),
    );
  });

  it("connectors get the same per-expert isolation (aligned with KB fix)", async () => {
    const threadId = "thread-existing";
    const { result, rerender } = renderHook(
      ({ agentId }: { agentId: string }) =>
        useChatComposerResources(agentId, threadId),
      { initialProps: { agentId: "expertA" } },
    );
    await waitFor(() => expect(result.current.chatConnectors.length).toBe(2));

    // manual connector selection in A (saved per agent)
    act(() => result.current.handleConnectorsChange(["c1"]));
    expect(result.current.selectedConnectors).toEqual(["c1"]);

    // switch to B: A's c1 must NOT leak; B has no saved prefs / defaults
    rerender({ agentId: "expertB" });
    await waitFor(() => expect(result.current.selectedConnectors).toEqual([]));

    // manual selection in B, then back to A: each expert remembers its own
    act(() => result.current.handleConnectorsChange(["c2"]));
    rerender({ agentId: "expertA" });
    await waitFor(() =>
      expect(result.current.selectedConnectors).toEqual(["c1"]),
    );
    rerender({ agentId: "expertB" });
    await waitFor(() =>
      expect(result.current.selectedConnectors).toEqual(["c2"]),
    );
  });
});
