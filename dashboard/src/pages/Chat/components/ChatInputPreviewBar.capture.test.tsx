import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import ChatInputPreviewBar from "./ChatInputPreviewBar";
vi.mock("../../../hooks/useAuthImageSrc", () => ({
  useAuthImageSrc: (url: string) => ({ src: url, loadState: "ready" }),
}));
it("shows scan thumbnail and retains original PDF attachment", () => {
  render(
    <ChatInputPreviewBar
      attachments={[
        {
          url: "/original.pdf",
          previewUrl: "/thumbnail.png",
          filename: "scan.pdf",
          mediaType: "application/pdf",
          kind: "file",
        },
      ]}
      uploading={false}
      selectedConnectors={[]}
      selectedKnowledgeBaseIds={[]}
      onRemoveAttachment={vi.fn()}
    />,
  );
  expect(screen.getByRole("img", { name: "scan.pdf" })).toHaveAttribute(
    "src",
    "/thumbnail.png",
  );
  expect(screen.getByText("scan.pdf")).toBeInTheDocument();
});
