import {
  act,
  fireEvent,
  render,
  renderHook,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { OctopAgent } from "../../context/AgentContext";
import type { KnowledgeBase } from "../../api/modules/knowledgeBases";
import { connectorsApi } from "../../api/modules/connectors";
import { knowledgeBasesApi } from "../../api/modules/knowledgeBases";
import { preferencesApi } from "../../api/modules/preferences";
import { providerApi } from "../../api/modules/provider";
import { useChatComposerResources } from "./hooks/useChatComposerResources";
import { useChatSend } from "./hooks/useChatSend";
import * as chatStore from "./hooks/chatStore";
import { saveKnowledgeBaseIds } from "./utils/chatStorage";
import ChatInputActionsRow from "./components/ChatInputActionsRow";

// Only API responses and user identity are mocked; composer and send logic are real.
const fixture = vi.hoisted(() => ({ agents: [] as OctopAgent[] }));
vi.mock("../../context/AgentContext", () => ({
  useAgent: () => ({ agents: fixture.agents }),
}));
vi.mock("../../hooks/useCurrentUser", () => ({
  useCurrentUser: () => ({ id: 7 }),
}));
vi.mock("../../api/modules/connectors", () => ({
  connectorsApi: { listInstances: vi.fn() },
}));
vi.mock("../../api/modules/knowledgeBases", () => ({
  knowledgeBasesApi: { getCapability: vi.fn(), list: vi.fn() },
}));
vi.mock("../../api/modules/provider", () => ({
  providerApi: {
    listResolvedModels: vi.fn().mockResolvedValue([
      {
        provider_id: 1,
        provider_name: "DeepSeek",
        provider_kind: "deepseek",
        model: "deepseek-chat",
        name: "DeepSeek Chat",
      },
    ]),
    getActiveModel: vi.fn().mockResolvedValue(null),
  },
}));
vi.mock("../../api/modules/preferences", () => ({
  preferencesApi: { get: vi.fn(), set: vi.fn() },
}));
vi.mock("../../api/modules/octopThreads", () => ({
  octopThreadsApi: { patch: vi.fn().mockResolvedValue({}) },
}));
vi.mock("../../api/request", () => ({ request: vi.fn() }));
vi.mock("./components/ContextWindowRing", () => ({ default: () => null }));

const expertModel = "DeepSeek/deepseek-chat";
const base = (id: string, owner = 7, defaultOpen = false): KnowledgeBase => ({
  id,
  owner_user_id: owner,
  name: `Knowledge ${id}`,
  description: "",
  default_open: defaultOpen,
  shared: false,
  icon_name: "book",
  embedding_model: "test",
  embedding_dim: 384,
  doc_count: 1,
  max_documents: 0,
  created_at: 0,
  updated_at: 0,
});

beforeEach(() => {
  vi.restoreAllMocks();
  vi.clearAllMocks();
  localStorage.clear();
  fixture.agents = [
    {
      agent_id: "expertA",
      default_model: expertModel,
      knowledge_base_ids: ["k1"],
      mcp_servers: [],
      config: { conversation_mode: "ask" },
    } as OctopAgent,
  ];
  vi.mocked(preferencesApi.get).mockResolvedValue({
    locale: "zh",
    preferred_model: null,
    model_reasoning: {},
    remote_browser_bookmarks: [],
  });
  vi.mocked(connectorsApi.listInstances).mockResolvedValue([]);
  vi.mocked(providerApi.listResolvedModels).mockResolvedValue([
    {
      provider_id: 1,
      provider_name: "DeepSeek",
      provider_kind: "deepseek",
      model: "deepseek-chat",
      name: "DeepSeek Chat",
    } as Awaited<ReturnType<typeof providerApi.listResolvedModels>>[number],
  ]);
  vi.mocked(providerApi.getActiveModel).mockResolvedValue(
    null as unknown as Awaited<ReturnType<typeof providerApi.getActiveModel>>,
  );
  vi.mocked(knowledgeBasesApi.getCapability).mockResolvedValue({
    usable: true,
  } as Awaited<ReturnType<typeof knowledgeBasesApi.getCapability>>);
  vi.mocked(knowledgeBasesApi.list).mockResolvedValue([
    base("k1"),
    base("k2"),
    base("k3"),
  ]);
});

function wrapper({ children }: { children: React.ReactNode }) {
  return <MemoryRouter>{children}</MemoryRouter>;
}

function renderNewChat() {
  return renderHook(
    () => {
      const resources = useChatComposerResources("expertA", null);
      const { t } = useTranslation();
      const send = useChatSend({
        ...resources,
        resolvedAgentId: "expertA",
        activeThreadId: null,
        sessions: [],
        messagesLength: 0,
        defaultModel: expertModel,
        sendMessage: vi.fn(),
        createSession: () => ({
          session: {
            id: "repro-thread",
            threadId: "repro-thread",
            name: "New Chat",
            updatedAt: null,
            channelType: "dashboard",
          },
          resolvedId: Promise.resolve("repro-thread"),
        }),
        renameSession: vi.fn(),
        t,
      });
      return { ...resources, ...send };
    },
    { wrapper },
  );
}

function renderToolbar(resources: ReturnType<typeof useChatComposerResources>) {
  render(
    <MemoryRouter>
      <ChatInputActionsRow
        {...resources}
        availableKnowledgeBases={resources.chatKnowledgeBases}
        availableConnectors={resources.chatConnectors}
        onKnowledgeBaseIdsChange={resources.handleKnowledgeBaseIdsChange}
        onConnectorsChange={resources.handleConnectorsChange}
        onModelChange={resources.setSelectedModel}
        onConversationModeChange={resources.handleConversationModeChange}
        defaultModel={expertModel}
        isMobile={false}
        isStreaming={false}
        canSend={false}
        text=""
        polishing={false}
        uploading={false}
        recording={false}
        transcribing={false}
        slashPickerGroups={null}
        slashMenuItems={[]}
        onSlashShortcutSelect={vi.fn()}
        onFileSelect={vi.fn()}
        onNewChat={vi.fn()}
        onPolish={vi.fn()}
        onToggleVoice={vi.fn()}
        onCancel={vi.fn()}
        onSubmit={vi.fn()}
      />
    </MemoryRouter>,
  );
  fireEvent.click(screen.getByTestId("composer-plus"));
}

describe("expert composer defaults", () => {
  it("shows the expert default model without creating an explicit override", async () => {
    const { result } = renderNewChat();
    await waitFor(() => expect(result.current.modelsReady).toBe(true));
    await waitFor(() =>
      expect(result.current.selectedKnowledgeBaseIds).toEqual(["k1"]),
    );
    expect(result.current.conversationMode).toBe("ask");
    expect(result.current.selectedModel).toBeNull();

    renderToolbar(result.current);
    const modelRow = await screen.findByRole("button", {
      name: "Model Default: DeepSeek Chat",
    });
    expect(modelRow).toHaveTextContent("Default: DeepSeek Chat");
    expect(result.current.selectedModel).toBeNull();
    expect(screen.getByTestId("composer-plus")).toHaveTextContent("1");
    fireEvent.click(screen.getByText("chat.knowledgePicker"));
    const panel = await screen.findByTestId("composer-plus-panel");
    expect(
      within(panel)
        .getAllByRole("switch")
        .map((control) => control.getAttribute("aria-checked")),
    ).toEqual(["true", "false", "false"]);
  });

  it.each(["ask", "plan"] as const)(
    "excludes inactive connectors from the %s badge and sends only the selected KB",
    async (mode) => {
      fixture.agents[0].config = { conversation_mode: mode };
      vi.mocked(connectorsApi.listInstances).mockResolvedValue([
        {
          status: "active",
          has_credentials: true,
          mcp_server_name: "c1",
          display_name: "Connector C1",
          owner_user_id: 7,
          kind: "mcp",
          default_open: true,
        } as Awaited<ReturnType<typeof connectorsApi.listInstances>>[number],
      ]);
      const sendTurn = vi
        .spyOn(chatStore, "sendTurn")
        .mockImplementation(() => {});
      const { result } = renderNewChat();
      await waitFor(() =>
        expect(result.current.selectedConnectors).toEqual(["c1"]),
      );
      await waitFor(() =>
        expect(result.current.selectedKnowledgeBaseIds).toEqual(["k1"]),
      );

      renderToolbar(result.current);
      expect(screen.getByTestId("composer-plus")).toHaveTextContent("1");
      const knowledgeRow = await screen.findByRole("button", {
        name: "chat.knowledgePicker 1",
      });
      expect(knowledgeRow).toHaveTextContent("1");
      expect(
        screen.queryByText("connectors.chatPicker"),
      ).not.toBeInTheDocument();

      act(() => {
        result.current.handleSend("reproduce defaults");
      });
      await waitFor(() => expect(sendTurn).toHaveBeenCalledOnce());
      const args = sendTurn.mock.calls[0];
      expect(args[6]).toBeNull();
      expect(args[8]).toEqual([]);
      expect(args[9]).toEqual(["k1"]);
      expect(args[13]).toBe(mode);
    },
  );

  it("a user preferred model is automatically sent as an override of the expert default", async () => {
    const preferred = "OpenAI/gpt-4o";
    vi.mocked(preferencesApi.get).mockResolvedValue({
      locale: "zh",
      preferred_model: preferred,
      model_reasoning: {},
      remote_browser_bookmarks: [],
    });
    const sendTurn = vi
      .spyOn(chatStore, "sendTurn")
      .mockImplementation(() => {});
    const { result } = renderNewChat();
    await waitFor(() => expect(result.current.selectedModel).toBe(preferred));
    await waitFor(() =>
      expect(result.current.selectedKnowledgeBaseIds).toEqual(["k1"]),
    );
    act(() => {
      result.current.handleSend("reproduce model priority");
    });
    await waitFor(() => expect(sendTurn).toHaveBeenCalledOnce());
    expect(sendTurn.mock.calls[0][6]).toBe(preferred);
    expect(sendTurn.mock.calls[0][6]).not.toBe(expertModel);
  });

  it("new chat ignores saved KB picks and restores the expert KB", async () => {
    saveKnowledgeBaseIds("expertA", ["k3"]);
    const { result } = renderNewChat();
    await waitFor(() =>
      expect(result.current.chatKnowledgeBases).toHaveLength(3),
    );
    expect(result.current.selectedKnowledgeBaseIds).toEqual(["k1"]);
  });

  it("an owned default-open KB is added to expert defaults, but another owner's is not", async () => {
    vi.mocked(knowledgeBasesApi.list).mockResolvedValue([
      base("k1"),
      base("k2", 7, true),
      base("k3", 8, true),
    ]);
    const { result } = renderNewChat();
    await waitFor(() =>
      expect(result.current.chatKnowledgeBases).toHaveLength(3),
    );
    expect(result.current.selectedKnowledgeBaseIds).toEqual(["k2", "k1"]);
  });

  it("expert defaults arriving after the initial catalog load still apply", async () => {
    fixture.agents = [];
    const { result, rerender } = renderNewChat();
    await waitFor(() =>
      expect(result.current.chatKnowledgeBases).toHaveLength(3),
    );
    expect(result.current.selectedKnowledgeBaseIds).toEqual([]);
    fixture.agents = [
      {
        agent_id: "expertA",
        default_model: expertModel,
        knowledge_base_ids: ["k1"],
        config: { conversation_mode: "ask" },
      } as OctopAgent,
    ];
    rerender();
    await waitFor(() =>
      expect(result.current.selectedKnowledgeBaseIds).toEqual(["k1"]),
    );
    expect(result.current.conversationMode).toBe("ask");
  });
});
