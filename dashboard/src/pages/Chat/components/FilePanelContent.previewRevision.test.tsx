import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import FilePanelContent from "./FilePanelContent";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (_key: string, fallback?: string) => fallback ?? _key,
  }),
}));

vi.mock("../../../utils/antdMessage", () => ({
  message: { error: vi.fn(), success: vi.fn(), warning: vi.fn() },
}));

vi.mock("../../Agent/Workspace/components/FileViewer", () => ({
  default: ({ refreshToken }: { refreshToken?: number }) => (
    <div data-testid="viewer-token">{refreshToken}</div>
  ),
}));

describe("FilePanelContent previewRevision", () => {
  it("reloads an open Office preview when the agent overwrites the same path", () => {
    const { rerender } = render(
      <FilePanelContent
        agentId="agent-a"
        filePath="report.docx"
        previewRevision={0}
      />,
    );
    expect(screen.getByTestId("viewer-token").textContent).toBe("0");

    rerender(
      <FilePanelContent
        agentId="agent-a"
        filePath="report.docx"
        previewRevision={2}
      />,
    );
    expect(screen.getByTestId("viewer-token").textContent).toBe("2");
  });
});
