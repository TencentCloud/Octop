import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "antd";
import { ChatFilePreviewProvider } from "../ChatFilePreviewContext";
import type { ChatMessage } from "../hooks/useChat";
import TurnFileChangeCard, { turnSummaryCache } from "./TurnFileChangeCard";

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
        "git.undo": "撤销",
        "git.reverted": "已撤销",
        "git.rewindSafe": "可回滚",
        "git.rewindUnsafe": "已被外部修改",
        "git.rewindIgnored": "已忽略",
        "git.rewindCannotApply": "有文件在本轮之后被修改，无法安全回滚。",
        "git.diffUnavailable": "暂时无法预览这份 Diff。",
        "git.rewindApply": "回滚",
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

const checkpoints = vi.hoisted(() => ({
  turnSummary: vi.fn(),
  turnDiff: vi.fn(),
  rewindPreview: vi.fn(),
  rewindApply: vi.fn(),
}));
vi.mock("../../../api/modules/fileCheckpoints", () => ({
  fileCheckpointsApi: checkpoints,
}));

function writeMessage(): ChatMessage {
  return {
    id: "assistant-1",
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

function renderCard(messages: ChatMessage[], threadId: string | null = "th-1") {
  const openFilePreview = vi.fn();
  const openGitChange = vi.fn();
  const view = render(
    <App>
      <ChatFilePreviewProvider
        openFilePreview={openFilePreview}
        openGitChange={openGitChange}
        openKnowledgeCitation={vi.fn()}
        threadId={threadId}
      >
        <TurnFileChangeCard
          messages={messages}
          agentId="ag-1"
          onOpenList={vi.fn()}
        />
      </ChatFilePreviewProvider>
    </App>,
  );
  return { ...view, openFilePreview, openGitChange };
}

describe("TurnFileChangeCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    turnSummaryCache.clear();
    checkpoints.turnSummary.mockResolvedValue({
      files: [],
      additions: 0,
      deletions: 0,
      reverted: false,
    });
  });

  it("Review opens the per-turn diff modal", async () => {
    checkpoints.turnDiff.mockResolvedValue({
      path: "src/app.py",
      diff: "@@ -1 +1 @@\n-old\n+one\n",
    });
    renderCard([writeMessage()]);
    fireEvent.click(screen.getByRole("button", { name: /1 个文件变更/ }));
    fireEvent.click(screen.getByRole("button", { name: "Review" }));
    await waitFor(() => {
      expect(checkpoints.turnDiff).toHaveBeenCalledWith(
        "ag-1",
        "th-1",
        "assistant-1",
        "src/app.py",
      );
    });
    expect(await screen.findByText("+one")).toBeInTheDocument();
  });

  it("shows unavailable instead of falling back to the git worktree diff", async () => {
    checkpoints.turnDiff.mockRejectedValue(new Error("404"));
    const { openGitChange } = renderCard([writeMessage()]);
    fireEvent.click(screen.getByRole("button", { name: /1 个文件变更/ }));
    fireEvent.click(screen.getByRole("button", { name: "Review" }));
    expect(
      await screen.findByText("暂时无法预览这份 Diff。"),
    ).toBeInTheDocument();
    expect(openGitChange).not.toHaveBeenCalled();
  });

  it("Undo previews and applies rewind when the preview is safe", async () => {
    checkpoints.rewindPreview.mockResolvedValue({
      safe: [{ path: "src/app.py", before: null, after: "one\ntwo\n" }],
      unsafe: [],
      ignored: [],
      can_apply: true,
    });
    checkpoints.rewindApply.mockResolvedValue({
      applied: ["src/app.py"],
      blocked: [],
    });
    renderCard([writeMessage()]);
    fireEvent.click(screen.getByTestId("turn-undo"));
    await waitFor(() => {
      expect(checkpoints.rewindPreview).toHaveBeenCalled();
    });
    expect(await screen.findByText("可回滚")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /回滚 \(1\)/ }));
    await waitFor(() => {
      expect(checkpoints.rewindApply).toHaveBeenCalledWith(
        "ag-1",
        "th-1",
        "assistant-1",
      );
    });
  });

  it("blocks undo when any file is unsafe (all-or-nothing)", async () => {
    checkpoints.rewindPreview.mockResolvedValue({
      safe: [{ path: "src/app.py", before: null, after: "one\ntwo\n" }],
      unsafe: [{ path: "other.md", reason: "external_modified" }],
      ignored: [],
      can_apply: false,
    });
    renderCard([writeMessage()]);
    fireEvent.click(screen.getByTestId("turn-undo"));
    const applyButton = await screen.findByRole("button", {
      name: /回滚 \(1\)/,
    });
    expect(applyButton).toBeDisabled();
    expect(
      screen.getByText("有文件在本轮之后被修改，无法安全回滚。"),
    ).toBeInTheDocument();
    expect(checkpoints.rewindApply).not.toHaveBeenCalled();
  });

  it("marks rewound turns and hides undo", async () => {
    checkpoints.turnSummary.mockResolvedValue({
      files: [
        {
          path: "src/app.py",
          added: 2,
          removed: 0,
          write_count: 1,
          tool_names: [],
        },
      ],
      additions: 2,
      deletions: 0,
      reverted: true,
    });
    renderCard([writeMessage()]);
    expect(
      await screen.findByTestId("turn-change-reverted"),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("turn-undo")).not.toBeInTheDocument();
  });

  it("shows the server-only list when the client estimate is empty", async () => {
    // Subagent turns write files the client-side tool scan cannot see; the
    // card must still render the server-authoritative list.
    checkpoints.turnSummary.mockResolvedValue({
      files: [
        {
          path: "src/octop_harness/middleware/file_capture.py",
          added: 312,
          removed: 0,
          write_count: 3,
          tool_names: ["write_file"],
        },
        {
          path: "src/octop_harness/middleware/tool_paths.py",
          added: 35,
          removed: 0,
          write_count: 1,
          tool_names: ["edit_file"],
        },
      ],
      additions: 347,
      deletions: 0,
      reverted: false,
    });
    const textOnly: ChatMessage[] = [
      {
        id: "assistant-1",
        role: "assistant",
        content: "delegated the edits",
        timestamp: 1,
        status: "done",
      },
    ];
    renderCard(textOnly);
    expect(
      await screen.findByRole("button", { name: /2 个文件变更/ }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /2 个文件变更/ }));
    expect(
      await screen.findByText("middleware/file_capture.py"),
    ).toBeInTheDocument();
    expect(screen.getByText("middleware/tool_paths.py")).toBeInTheDocument();
  });

  it("reuses a warm cache on remount without a second request", async () => {
    checkpoints.turnSummary.mockResolvedValue({
      files: [
        { path: "a.md", added: 1, removed: 0, write_count: 1, tool_names: [] },
      ],
      additions: 1,
      deletions: 0,
      reverted: false,
    });
    const { unmount } = renderCard([writeMessage()]);
    await screen.findByRole("button", { name: /1 个文件变更/ });
    unmount();
    const second = renderCard([writeMessage()]);
    await waitFor(() => {
      expect(
        second.container.querySelector('[data-testid="turn-change-card"]'),
      ).not.toBeNull();
    });
    await new Promise((r) => setTimeout(r, 900));
    expect(checkpoints.turnSummary).toHaveBeenCalledTimes(1);
    expect(
      second.container.querySelector('[data-testid="turn-change-card"]'),
    ).not.toBeNull();
  });

  it("does not cache a failed summary and retries on remount", async () => {
    checkpoints.turnSummary.mockRejectedValue(new Error("500"));
    const { unmount } = renderCard([writeMessage()]);
    // Failure falls back to the client estimate, never caching the miss.
    await waitFor(() => {
      expect(checkpoints.turnSummary).toHaveBeenCalled();
    });
    unmount();
    renderCard([writeMessage()]);
    await waitFor(() => {
      expect(checkpoints.turnSummary).toHaveBeenCalledTimes(2);
    });
  });

  it("renders nothing when no source knows about files", async () => {
    checkpoints.turnSummary.mockResolvedValue({
      files: [],
      additions: 0,
      deletions: 0,
      reverted: false,
    });
    const textOnly: ChatMessage[] = [
      {
        id: "assistant-1",
        role: "assistant",
        content: "plain",
        timestamp: 1,
        status: "done",
      },
    ];
    const { container } = renderCard(textOnly);
    await waitFor(() => {
      expect(checkpoints.turnSummary).toHaveBeenCalled();
    });
    expect(
      container.querySelector('[data-testid="turn-change-card"]'),
    ).toBeNull();
  });

  it("Open still opens the file viewer", () => {
    const { openFilePreview } = renderCard([writeMessage()]);
    fireEvent.click(screen.getByRole("button", { name: /1 个文件变更/ }));
    fireEvent.click(screen.getByRole("button", { name: "打开" }));
    expect(openFilePreview).toHaveBeenCalledWith("src/app.py", "ag-1");
  });
});
