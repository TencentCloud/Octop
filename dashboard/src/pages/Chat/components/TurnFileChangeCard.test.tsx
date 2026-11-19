import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ChatFilePreviewProvider } from "../ChatFilePreviewContext";
import type { ChatMessage } from "../hooks/useChat";
import TurnFileChangeCard from "./TurnFileChangeCard";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      const templates: Record<string, string> = {
        "chat.fileChangePending": "进行中",
        "chat.fileChangeMore": "还有 {{count}} 个",
        "chat.editFileCard": "编辑了{{count}}个文件",
        "git.filesChanged": "{{count}} 个文件变更",
        "git.review": "Review",
        "git.open": "打开",
      };
      let text = templates[key] ?? key;
      if (opts) {
        for (const [name, value] of Object.entries(opts)) {
          if (typeof value === "number") {
            text = text.replaceAll(`{{${name}}}`, String(value));
          }
        }
      }
      return text;
    },
  }),
}));

function writeMessage(): ChatMessage {
  return {
    id: "w",
    role: "assistant",
    content: "",
    timestamp: 1,
    status: "done",
    toolData: {
      name: "write_file",
      arguments: JSON.stringify({
        file_path: "src/app.py",
        content: "one\ntwo\n",
      }),
      output: "Updated file src/app.py",
    },
  };
}

function renderCard(messages: ChatMessage[]) {
  const openFilePreview = vi.fn();
  const openGitChange = vi.fn();
  render(
    <ChatFilePreviewProvider
      openFilePreview={openFilePreview}
      openGitChange={openGitChange}
      openKnowledgeCitation={vi.fn()}
    >
      <TurnFileChangeCard messages={messages} onOpenList={vi.fn()} />
    </ChatFilePreviewProvider>,
  );
  return { openFilePreview, openGitChange };
}

describe("TurnFileChangeCard", () => {
  it("shows the collapsed summary bar with line totals, then expands", () => {
    const { openGitChange, openFilePreview } = renderCard([writeMessage()]);

    const summary = screen.getByRole("button", {
      name: "1 个文件变更 +2 −0",
    });
    expect(summary).toHaveAttribute("aria-expanded", "false");

    fireEvent.click(summary);
    const row = screen.getByTestId("turn-change-row");
    expect(row).toHaveTextContent("app.py");

    // Row body (and Review) opens the diff in the git panel.
    fireEvent.click(screen.getByRole("button", { name: "Review" }));
    expect(openGitChange).toHaveBeenCalledWith("src/app.py", null);
    expect(openFilePreview).not.toHaveBeenCalled();

    // Open goes to the file viewer.
    fireEvent.click(screen.getByRole("button", { name: "打开" }));
    expect(openFilePreview).toHaveBeenCalledWith("src/app.py", null);
  });

  it("shows the first files and reveals the rest", () => {
    const messages = ["a", "b", "c", "d", "e"].map(
      (name, index): ChatMessage => ({
        id: String(index),
        role: "assistant",
        content: "",
        timestamp: 1,
        status: "done",
        toolData: {
          name: "write_file",
          arguments: JSON.stringify({
            file_path: `src/${name}.py`,
            content: "x\n",
          }),
        },
      }),
    );
    renderCard(messages);
    fireEvent.click(screen.getByRole("button", { name: /5 个文件变更/ }));
    expect(
      screen.getByRole("button", { name: /src\/d\.py/ }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /src\/e\.py/ })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "还有 1 个" }));
    expect(
      screen.getByRole("button", { name: /src\/e\.py/ }),
    ).toBeInTheDocument();
  });
});
