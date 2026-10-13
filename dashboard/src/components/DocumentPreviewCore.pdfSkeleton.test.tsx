import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import DocumentPreviewCore from "./DocumentPreviewCore";

vi.mock("react-pdf", () => ({
  Document: () => <div data-testid="pdf-document" />,
  Page: () => <div data-testid="pdf-page" />,
  pdfjs: { GlobalWorkerOptions: { workerSrc: "" } },
}));

describe("DocumentPreviewCore pdf skeleton", () => {
  it("shows the progress-bar skeleton while the blob downloads", () => {
    // Never-resolving fetchBlob keeps the component in the download phase.
    const pending = new Promise<Blob>(() => {});
    const { container } = render(
      <DocumentPreviewCore
        kind="pdf"
        filename="big.pdf"
        fetchBlob={() => pending}
      />,
    );

    // Two clean paper placeholders plus the top loading bar.
    expect(container.querySelectorAll("[class*=skelPage]").length).toBe(2);
    expect(container.querySelector("[class*=pdfLoadingBar]")).toBeTruthy();
    // The real viewer (react-pdf Document) must not mount yet.
    expect(container.querySelector('[data-testid="pdf-document"]')).toBeNull();
    expect(container.querySelector('[aria-busy="true"]')).toBeTruthy();
  });
});
