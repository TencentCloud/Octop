import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ChatFilePreviewProvider } from "../ChatFilePreviewContext";
import { MessageFileCard } from "./MessageFileCard";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

describe("MessageFileCard 3D model preview", () => {
  it("shows preview action for .glb artifacts and opens the file preview dock", () => {
    const openFilePreview = vi.fn();
    render(
      <ChatFilePreviewProvider
        openFilePreview={openFilePreview}
        openGitChange={vi.fn()}
        openTurnDiff={vi.fn()}
        openKnowledgeCitation={vi.fn()}
      >
        <MessageFileCard
          url="/api/agents/ag-1/workspace/download?path=generated%2F3d%2Fmesh.glb"
          filename="mesh.glb"
          agentId="ag-1"
        />
      </ChatFilePreviewProvider>,
    );

    const previewBtn = screen.getByRole("button", { name: "common.preview" });
    fireEvent.click(previewBtn);
    expect(openFilePreview).toHaveBeenCalledWith(
      "generated/3d/mesh.glb",
      "ag-1",
    );
  });

  it("keeps unsupported binary archives like .zip download-only", () => {
    render(
      <ChatFilePreviewProvider
        openFilePreview={vi.fn()}
        openGitChange={vi.fn()}
        openTurnDiff={vi.fn()}
        openKnowledgeCitation={vi.fn()}
      >
        <MessageFileCard
          url="/api/agents/ag-1/workspace/download?path=generated%2F3d%2Fmesh.zip"
          filename="mesh.zip"
          agentId="ag-1"
        />
      </ChatFilePreviewProvider>,
    );

    expect(screen.queryByRole("button", { name: "common.preview" })).toBeNull();
    expect(
      screen.getByRole("button", { name: "common.download" }),
    ).toBeTruthy();
  });
});
