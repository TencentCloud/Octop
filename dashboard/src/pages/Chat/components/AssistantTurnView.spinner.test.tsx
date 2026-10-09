import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ChatMessage } from "../hooks/sseHelpers";
import AssistantTurnView from "./AssistantTurnView";

// Record what the process spinner was actually told to do, so the assertions
// below observe the rendered call site rather than a helper in isolation.
const spinnerStates: boolean[] = [];

vi.mock("./TurnProcessBlocks", () => ({
  __esModule: true,
  TurnProcessBlocks: ({ isStreaming }: { isStreaming?: boolean }) => {
    spinnerStates.push(Boolean(isStreaming));
    return <div data-testid="process-blocks" />;
  },
  turnHasProcessSummary: () => true,
  turnHasVisibleProcess: () => true,
}));
vi.mock("./MessageBubble", () => ({
  __esModule: true,
  default: () => <div data-testid="message-bubble" />,
  ToolDetailsInline: () => null,
}));
vi.mock("./TodoProgressPanel", () => ({ default: () => null }));
vi.mock("./KnowledgeCitationsStrip", () => ({ default: () => null }));
vi.mock("../../../context/AgentContext", () => ({
  useAgent: () => ({ activeAgentId: null }),
}));
vi.mock("../../../components/Markdown/LazyMarkdown", () => ({
  default: ({ content }: { content: string }) => <div>{content}</div>,
}));
vi.mock("../../../utils/collectTurnToolMedia", () => ({
  collectTurnToolMedia: () => ({ images: [], videos: [], files: [] }),
}));
vi.mock("../../../utils/collectTurnKnowledgeCitations", () => ({
  collectTurnKnowledgeCitations: () => [],
}));

function streamingToolMessage(id: string): ChatMessage {
  return {
    id,
    role: "assistant",
    content: "",
    status: "streaming",
    timestamp: Date.now(),
    toolData: { name: "read_file", arguments: "{}" },
  } as unknown as ChatMessage;
}

/**
 * An `ask_user_question` card rebuilt from a tool chunk: it still carries
 * `status: "pending"` but has no `pending_id`, so the server can never resume
 * it and the composer stays unlocked for the rest of the session.
 */
function unresumableAskCard(id: string): ChatMessage {
  return {
    id,
    role: "assistant",
    content: "",
    status: "done",
    timestamp: 0,
    hitlData: {
      status: "pending",
      action_requests: [
        {
          name: "ask_user_question",
          args: { questions: [{ question: "Continue?" }] },
        },
      ],
    },
  } as unknown as ChatMessage;
}

/** A genuinely resumable approval card: carries a `pending_id`. */
function resumableApprovalCard(id: string): ChatMessage {
  return {
    id,
    role: "assistant",
    content: "",
    status: "done",
    timestamp: 0,
    hitlData: {
      status: "pending",
      pending_id: `pending-${id}`,
      action_requests: [{ name: "write_file", args: {} }],
    },
  } as unknown as ChatMessage;
}

function renderTurn(hitlMessage: ChatMessage) {
  spinnerStates.length = 0;
  render(
    <AssistantTurnView
      messages={[streamingToolMessage("tool-1"), hitlMessage]}
      isTurnInProgress
    />,
  );
  return spinnerStates;
}

describe("AssistantTurnView process spinner vs. unresumable ask card", () => {
  it("keeps the spinner running when the pending ask card cannot be resumed", () => {
    const states = renderTurn(unresumableAskCard("ask-1"));
    expect(states.length).toBeGreaterThan(0);
    // The unresumable card must not freeze the turn: the user can keep
    // chatting, so a permanently spinning process bar would be a lie.
    expect(states.some(Boolean)).toBe(true);
  });

  it("still freezes the spinner for a genuinely resumable approval", () => {
    const states = renderTurn(resumableApprovalCard("approval-1"));
    expect(states.length).toBeGreaterThan(0);
    expect(states.some(Boolean)).toBe(false);
  });
});
