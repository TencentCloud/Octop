import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  knowledgeBasesApi,
  type KnowledgeBase,
} from "../../../api/modules/knowledgeBases";
import {
  consumePendingAttachKnowledgeBaseId,
  peekPendingAttachKnowledgeBaseId,
  setPendingAttachKnowledgeBaseId,
} from "../utils/pendingAttachKnowledgeBase";
import { useChatComposerResources } from "./useChatComposerResources";

vi.mock("../../../hooks/useCurrentUser", () => ({
  useCurrentUser: () => ({ id: 1 }),
}));
vi.mock("../../../context/AgentContext", () => ({
  useAgent: () => ({
    agents: [
      { agent_id: "agent-1", knowledge_base_ids: ["expert", "unavailable"] },
    ],
  }),
}));
vi.mock("../../../api/modules/connectors", () => ({
  connectorsApi: { listInstances: vi.fn().mockResolvedValue([]) },
}));
vi.mock("../../../api/modules/provider", () => ({
  providerApi: { listResolvedModels: vi.fn().mockResolvedValue([]) },
}));
vi.mock("../../../api/modules/preferences", () => ({
  preferencesApi: { get: vi.fn().mockResolvedValue({}) },
}));
vi.mock("../../../api/request", () => ({
  request: vi.fn().mockResolvedValue(null),
}));
vi.mock("../../../api/modules/knowledgeBases", () => ({
  knowledgeBasesApi: {
    getCapability: vi.fn().mockResolvedValue({ usable: true }),
    list: vi.fn(),
  },
}));

function knowledgeBase(
  id: string,
  overrides: Partial<KnowledgeBase> = {},
): KnowledgeBase {
  return {
    id,
    owner_user_id: 1,
    name: id,
    description: "",
    default_open: false,
    shared: false,
    icon_name: "",
    embedding_model: "",
    embedding_dim: 0,
    doc_count: 0,
    max_documents: 100,
    created_at: 0,
    updated_at: 0,
    ...overrides,
  };
}

describe("useChatComposerResources knowledge bases", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    consumePendingAttachKnowledgeBaseId();
    vi.mocked(knowledgeBasesApi.list).mockResolvedValue([
      knowledgeBase("creative", { default_open: true }),
      knowledgeBase("research"),
      knowledgeBase("expert"),
      knowledgeBase("shared-default", {
        default_open: true,
        owner_user_id: 2,
        shared: true,
      }),
    ]);
  });

  it("restores history selections without adding defaults and filters unavailable bases", async () => {
    const { result, rerender } = renderHook(
      ({ threadKbKey }: { threadKbKey: string | null }) =>
        useChatComposerResources("agent-1", "thread-1", threadKbKey),
      { initialProps: { threadKbKey: null as string | null } },
    );
    await waitFor(() =>
      expect(result.current.chatKnowledgeBases).toHaveLength(4),
    );

    // History can arrive after the knowledge-base list.
    rerender({ threadKbKey: "research\0deleted" });
    expect(result.current.selectedKnowledgeBaseIds).toEqual(["research"]);

    act(() => result.current.handleKnowledgeBaseIdsChange([]));
    rerender({ threadKbKey: "creative" });
    expect(result.current.selectedKnowledgeBaseIds).toEqual([]);
  });

  it("restores each thread on navigation, including an explicit empty selection", async () => {
    const { result, rerender } = renderHook(
      ({ threadId, threadKbKey }) =>
        useChatComposerResources("agent-1", threadId, threadKbKey),
      { initialProps: { threadId: "thread-1", threadKbKey: "research" } },
    );
    await waitFor(() =>
      expect(result.current.selectedKnowledgeBaseIds).toEqual(["research"]),
    );

    act(() => result.current.handleKnowledgeBaseIdsChange(["creative"]));
    rerender({ threadId: "thread-2", threadKbKey: "" });
    expect(result.current.selectedKnowledgeBaseIds).toEqual([]);

    rerender({ threadId: "thread-1", threadKbKey: "research" });
    expect(result.current.selectedKnowledgeBaseIds).toEqual(["research"]);
    expect(knowledgeBasesApi.list).toHaveBeenCalledTimes(1);
  });

  it("uses owned and expert defaults for new and empty threads", async () => {
    const { result, rerender } = renderHook(
      ({ threadId }: { threadId: string | null }) =>
        useChatComposerResources("agent-1", threadId, null),
      { initialProps: { threadId: null as string | null } },
    );
    await waitFor(() =>
      expect(result.current.selectedKnowledgeBaseIds).toEqual([
        "creative",
        "expert",
      ]),
    );

    act(() => result.current.handleKnowledgeBaseIdsChange([]));
    rerender({ threadId: "empty-thread" });
    await waitFor(() =>
      expect(result.current.selectedKnowledgeBaseIds).toEqual([
        "creative",
        "expert",
      ]),
    );
  });

  it("attaches a pending base once alongside restored history or new-thread defaults", async () => {
    setPendingAttachKnowledgeBaseId("research");
    const existing = renderHook(() =>
      useChatComposerResources("agent-1", "thread-1", ""),
    );
    await waitFor(() =>
      expect(existing.result.current.selectedKnowledgeBaseIds).toEqual([
        "research",
      ]),
    );
    expect(peekPendingAttachKnowledgeBaseId()).toBe("");
    act(() => existing.result.current.handleKnowledgeBaseIdsChange([]));
    existing.rerender();
    expect(existing.result.current.selectedKnowledgeBaseIds).toEqual([]);
    existing.unmount();

    setPendingAttachKnowledgeBaseId("research");
    const fresh = renderHook(() =>
      useChatComposerResources("agent-1", "__pending__", null),
    );
    await waitFor(() =>
      expect(fresh.result.current.selectedKnowledgeBaseIds).toEqual([
        "research",
        "creative",
        "expert",
      ]),
    );
    expect(peekPendingAttachKnowledgeBaseId()).toBe("");
  });
});
