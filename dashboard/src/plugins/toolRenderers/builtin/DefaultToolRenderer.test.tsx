import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { DefaultToolRenderer } from "./DefaultToolRenderer";
import type { OctopPluginUIHost } from "../types";

vi.mock("../../../pages/Chat/hooks/toolDisplayNames", () => ({
  useToolDisplayNames: () => (name: string) => name,
  resolveToolLabel: (name: string) => name,
}));

describe("tool execution feedback", () => {
  it("shows an error status and keeps the actual arguments and failure reason inspectable", async () => {
    render(
      <DefaultToolRenderer
        pluginId="builtin"
        toolName="write_file"
        status="error"
        args={{ file_path: "notes.md" }}
        data={null}
        output="Permission denied"
        host={{} as OctopPluginUIHost}
        isStreaming={false}
      />,
    );
    const tool = screen.getByRole("button", {
      name: /write_file.*toolFeedback.failed/,
    });
    expect(tool).not.toHaveTextContent("Done");
    await userEvent.click(tool);
    expect(screen.getByText("Permission denied")).toBeInTheDocument();
    expect(screen.getByText(/"file_path": "notes.md"/)).toBeInTheDocument();
  });
  it("keeps execution marked as running until the result arrives", () => {
    const props = {
      pluginId: "builtin",
      toolName: "read_file",
      args: { file_path: "notes.md" },
      data: null,
      host: {} as OctopPluginUIHost,
    };
    const { rerender } = render(
      <DefaultToolRenderer {...props} status="running" isStreaming />,
    );
    expect(screen.getByRole("button")).toHaveAttribute("aria-busy", "true");
    rerender(
      <DefaultToolRenderer
        {...props}
        status="done"
        output="File contents"
        isStreaming={false}
      />,
    );
    expect(screen.getByRole("button")).not.toHaveAttribute("aria-busy");
    expect(screen.getByRole("button")).toHaveTextContent("Done");
  });
});
