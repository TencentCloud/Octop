/**
 * AssistantProcessSummary — default collapsed while streaming (#718).
 */

import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import AssistantProcessSummary from "./AssistantProcessSummary";
import type { AssistantTurnSplit } from "../utils/messageContent";
import {
  PROCESS_SUMMARY_EXPAND_WHILE_STREAMING_KEY,
  saveExpandProcessWhileStreaming,
} from "../utils/chatStorage";

function makeSplit(): AssistantTurnSplit {
  return {
    tools: [],
    thinkings: [
      {
        messageId: "m1",
        content: "step-by-step reasoning",
        isStreaming: true,
      },
    ],
    processSteps: [
      {
        kind: "thinking",
        item: {
          messageId: "m1",
          content: "step-by-step reasoning",
          isStreaming: true,
        },
      },
    ],
    answerMessage: null,
  };
}

describe("<AssistantProcessSummary />", () => {
  beforeEach(() => {
    localStorage.removeItem(PROCESS_SUMMARY_EXPAND_WHILE_STREAMING_KEY);
  });

  afterEach(() => {
    localStorage.removeItem(PROCESS_SUMMARY_EXPAND_WHILE_STREAMING_KEY);
  });

  it("stays collapsed while streaming by default", () => {
    render(<AssistantProcessSummary split={makeSplit()} isStreaming />);

    expect(
      screen.getByRole("button", { expanded: false }),
    ).toBeInTheDocument();
    expect(screen.queryByText("step-by-step reasoning")).not.toBeInTheDocument();
  });

  it("auto-expands while streaming when preference is on", () => {
    saveExpandProcessWhileStreaming(true);
    render(<AssistantProcessSummary split={makeSplit()} isStreaming />);

    expect(screen.getByRole("button", { expanded: true })).toBeInTheDocument();
    expect(screen.getByText("step-by-step reasoning")).toBeInTheDocument();
  });

  it("lets the user expand manually when preference is off", async () => {
    const user = userEvent.setup();
    render(<AssistantProcessSummary split={makeSplit()} isStreaming />);

    await user.click(screen.getByRole("button", { expanded: false }));
    expect(screen.getByRole("button", { expanded: true })).toBeInTheDocument();
    expect(screen.getByText("step-by-step reasoning")).toBeInTheDocument();
  });

  it("reacts when the preference flips on during a live turn", () => {
    render(<AssistantProcessSummary split={makeSplit()} isStreaming />);
    expect(
      screen.getByRole("button", { expanded: false }),
    ).toBeInTheDocument();

    act(() => {
      saveExpandProcessWhileStreaming(true);
    });

    expect(screen.getByRole("button", { expanded: true })).toBeInTheDocument();
    expect(screen.getByText("step-by-step reasoning")).toBeInTheDocument();
  });
});
