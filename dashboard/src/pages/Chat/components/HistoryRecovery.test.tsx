import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import HistoryRecovery from "./HistoryRecovery";

it("keeps unverified text and attachments recoverable outside the transcript", () => {
  const restore = vi.fn();
  const retry = vi.fn();
  const message = {
    id: "old",
    role: "user" as const,
    content: "unsent text",
    timestamp: 1,
    attachments: [
      {
        url: "",
        workspacePath: "inbound/file.txt",
        filename: "file.txt",
        kind: "file" as const,
      },
    ],
  };
  render(
    <HistoryRecovery
      messages={[message]}
      onRetry={retry}
      onRestore={restore}
    />,
  );
  expect(screen.getByText("unsent text")).toBeInTheDocument();
  expect(screen.getByText("file.txt")).toBeInTheDocument();
  fireEvent.click(
    screen.getByRole("button", { name: "chat.historyRecoveryRestore" }),
  );
  expect(restore).toHaveBeenCalledWith(message);
  fireEvent.click(screen.getByRole("button", { name: "chat.historyRetry" }));
  expect(retry).toHaveBeenCalledOnce();
});
