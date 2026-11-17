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
      };
      let text = templates[key] ?? key;
      if (opts) {
        for (const [name, value] of Object.entries(opts)) {
          text = text.replaceAll(`{{${name}}}`, String(value));
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

describe("TurnFileChangeCard", () => {
  it("shows the line totals and opens the file from the list", () => {
    const openFilePreview = vi.fn();
    render(
      <ChatFilePreviewProvider
        openFilePreview={openFilePreview}
        openKnowledgeCitation={vi.fn()}
      >
        <TurnFileChangeCard messages={[writeMessage()]} onOpenList={vi.fn()} />
      </ChatFilePreviewProvider>,
    );

    const row = screen.getByRole("button", { name: "src/app.py +2 −0" });
    fireEvent.click(row);
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
    render(
      <ChatFilePreviewProvider
        openFilePreview={vi.fn()}
        openKnowledgeCitation={vi.fn()}
      >
        <TurnFileChangeCard messages={messages} />
      </ChatFilePreviewProvider>,
    );
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
