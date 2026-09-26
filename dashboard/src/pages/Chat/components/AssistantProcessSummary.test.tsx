import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AssistantTurnSplit } from "../utils/messageContent";
import type { ChatMessage } from "../hooks/useChat";
import {
  COLLAPSE_THINKING_SOLO_KEY,
  COLLAPSE_THINKING_TEAM_KEY,
} from "../hooks/useCollapseThinking";
import AssistantProcessSummary from "./AssistantProcessSummary";
import ChatTitleBar from "./ChatTitleBar";

vi.mock("../../../components/Markdown/LazyMarkdown", () => ({
  default: ({ content }: { content: string }) => <div>{content}</div>,
}));
vi.mock("./MessageBubble", () => ({ ToolDetailsInline: () => null }));
vi.mock("./SessionChannelIcon", () => ({ default: () => null }));

function thinkingSplit(content = "Thinking content"): AssistantTurnSplit {
  const item = { messageId: "thinking", content, isStreaming: true };
  return {
    tools: [],
    thinkings: [item],
    processSteps: [{ kind: "thinking", item }],
    answerMessage: null,
  };
}

function runningToolSplit(name = "read_file"): AssistantTurnSplit {
  const message: ChatMessage = {
    id: "tool-1",
    role: "assistant",
    content: "",
    status: "streaming",
    timestamp: Date.now(),
    toolData: { name, arguments: "{}" },
  };
  return {
    tools: [message],
    thinkings: [],
    processSteps: [{ kind: "tool", message }],
    answerMessage: null,
  };
}

function TitleBar({ isTeam = false }: { isTeam?: boolean }) {
  return (
    <ChatTitleBar
      session={{
        id: "thread",
        threadId: "thread",
        name: "Chat",
        updatedAt: null,
        channelType: "dashboard",
      }}
      title="Chat"
      onRename={vi.fn()}
      onPin={vi.fn()}
      onFork={vi.fn()}
      onDelete={vi.fn()}
      isTeam={isTeam}
    />
  );
}

describe("thinking display preference", () => {
  beforeEach(() => localStorage.clear());

  it("keeps the existing default: expand while streaming, collapse on completion", () => {
    const split = thinkingSplit();
    const { rerender } = render(
      <AssistantProcessSummary split={split} isStreaming />,
    );
    expect(screen.getByText("Thinking content")).toBeInTheDocument();
    rerender(<AssistantProcessSummary split={split} isStreaming={false} />);
    expect(screen.queryByText("Thinking content")).not.toBeInTheDocument();
  });

  it("collapses by default while streaming in team chats", () => {
    render(
      <AssistantProcessSummary split={thinkingSplit()} isStreaming isTeam />,
    );
    expect(screen.queryByText("Thinking content")).not.toBeInTheDocument();
    expect(screen.getByRole("button")).toHaveAttribute(
      "aria-expanded",
      "false",
    );
  });

  it("shows a live hint while a tool is running", () => {
    render(<AssistantProcessSummary split={runningToolSplit()} isStreaming />);
    expect(
      screen.getByText(/正在调用工具|Calling tools/),
    ).toBeInTheDocument();
    expect(screen.getByRole("button")).toHaveAttribute("aria-busy", "true");
  });

  it("shows an organizing hint between tool rounds", () => {
    const message: ChatMessage = {
      id: "tool-done",
      role: "assistant",
      content: "",
      status: "done",
      timestamp: Date.now(),
      toolData: { name: "read_file", arguments: "{}", output: "ok" },
    };
    const split: AssistantTurnSplit = {
      tools: [message],
      thinkings: [],
      processSteps: [{ kind: "tool", message }],
      answerMessage: null,
    };
    render(<AssistantProcessSummary split={split} isStreaming />);
    expect(
      screen.getByText(/整理结果中|Organizing results/),
    ).toBeInTheDocument();
  });

  it("saves the menu choice and applies it to mounted panels and later visits", async () => {
    const { unmount } = render(
      <>
        <TitleBar />
        <AssistantProcessSummary split={thinkingSplit()} isStreaming />
      </>,
    );
    fireEvent.click(screen.getByRole("button", { name: "更多" }));
    const preference = await screen.findByRole("switch", {
      name: "chat.collapseThinking",
    });
    expect(preference).not.toBeChecked();
    fireEvent.click(
      screen.getByRole("menuitem", { name: /chat.collapseThinking/ }),
    );
    expect(localStorage.getItem(COLLAPSE_THINKING_SOLO_KEY)).toBe("true");
    expect(screen.queryByText("Thinking content")).not.toBeInTheDocument();
    unmount();
    render(
      <>
        <TitleBar />
        <AssistantProcessSummary split={thinkingSplit()} isStreaming />
      </>,
    );
    expect(screen.queryByText("Thinking content")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "更多" }));
    expect(
      await screen.findByRole("switch", { name: "chat.collapseThinking" }),
    ).toBeChecked();
  });

  it("defaults team menu switch on and stores team preference separately", async () => {
    render(
      <>
        <TitleBar isTeam />
        <AssistantProcessSummary split={thinkingSplit()} isStreaming isTeam />
      </>,
    );
    expect(screen.queryByText("Thinking content")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "更多" }));
    const preference = await screen.findByRole("switch", {
      name: "chat.collapseThinking",
    });
    expect(preference).toBeChecked();
    fireEvent.click(preference);
    expect(localStorage.getItem(COLLAPSE_THINKING_TEAM_KEY)).toBe("false");
    expect(localStorage.getItem(COLLAPSE_THINKING_SOLO_KEY)).toBeNull();
    expect(screen.getByText("Thinking content")).toBeInTheDocument();
  });

  it("allows manual expansion during streaming without resetting on content updates", () => {
    localStorage.setItem(COLLAPSE_THINKING_SOLO_KEY, "true");
    const { rerender } = render(
      <AssistantProcessSummary split={thinkingSplit()} isStreaming />,
    );
    expect(screen.queryByText("Thinking content")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button"));
    rerender(
      <AssistantProcessSummary
        split={thinkingSplit("More thinking")}
        isStreaming
      />,
    );
    expect(screen.getByText("More thinking")).toBeInTheDocument();
    rerender(
      <AssistantProcessSummary split={thinkingSplit()} isStreaming={false} />,
    );
    rerender(<AssistantProcessSummary split={thinkingSplit()} isStreaming />);
    expect(screen.getByRole("button")).toHaveAttribute(
      "aria-expanded",
      "false",
    );
  });

  it("can restore automatic expansion from the menu", async () => {
    localStorage.setItem(COLLAPSE_THINKING_SOLO_KEY, "true");
    render(
      <>
        <TitleBar />
        <AssistantProcessSummary split={thinkingSplit()} isStreaming />
      </>,
    );
    fireEvent.click(screen.getByRole("button", { name: "更多" }));
    const preference = await screen.findByRole("switch", {
      name: "chat.collapseThinking",
    });
    expect(preference).toBeChecked();
    fireEvent.click(preference);
    expect(localStorage.getItem(COLLAPSE_THINKING_SOLO_KEY)).toBe("false");
    expect(screen.getByText("Thinking content")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "更多" }));
    expect(
      await screen.findByRole("switch", { name: "chat.collapseThinking" }),
    ).not.toBeChecked();
  });
});
