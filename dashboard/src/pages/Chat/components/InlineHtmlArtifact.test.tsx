import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import InlineHtmlArtifact from "./InlineHtmlArtifact";
import { MessageFileCard } from "./MessageFileCard";
import { request } from "../../../api/request";

vi.mock("../../../api/request", () => ({ request: vi.fn() }));
vi.mock("../../../components/HtmlArtifactPreview", () => ({
  default: ({ content }: { content: string }) => (
    <div data-testid="html-preview">{content}</div>
  ),
}));
let intersect: IntersectionObserverCallback;
beforeEach(() => {
  vi.mocked(request).mockReset();
  vi.stubGlobal(
    "IntersectionObserver",
    class {
      constructor(callback: IntersectionObserverCallback) {
        intersect = callback;
      }
      observe() {}
      disconnect() {}
    },
  );
});
function show() {
  act(() =>
    intersect(
      [{ isIntersecting: true }] as IntersectionObserverEntry[],
      {} as IntersectionObserver,
    ),
  );
}

describe("inline HTML delivery", () => {
  it("loads only on visibility, with the producer agent/path, and aborts on unmount", async () => {
    vi.mocked(request).mockResolvedValue({ content: "<h1>分层</h1>" });
    const { unmount } = render(
      <InlineHtmlArtifact
        agentId="producer"
        path="generated/分层.html"
        title="分层"
      />,
    );
    expect(request).not.toHaveBeenCalled();
    show();
    await screen.findByTestId("html-preview");
    expect(vi.mocked(request).mock.calls[0][0]).toContain(
      "/agents/producer/workspace/file?path=",
    );
    expect(decodeURIComponent(vi.mocked(request).mock.calls[0][0])).toContain(
      "generated/分层.html",
    );
    const signal = vi.mocked(request).mock.calls[0][1]?.signal;
    unmount();
    expect(signal?.aborted).toBe(true);
  });

  it("offers retry on failure and can collapse a delivered artifact", async () => {
    vi.mocked(request)
      .mockRejectedValueOnce(new Error("failed"))
      .mockResolvedValue({ content: "<svg></svg>" });
    render(
      <MessageFileCard
        url="/api/agents/a/workspace/download?path=outbound/chart.html"
        agentId="a"
        workspacePath="outbound/chart.html"
        filename="chart.html"
        inlineHtml
      />,
    );
    show();
    await screen.findByRole("alert");
    fireEvent.click(screen.getByText("workspace.retryPreview"));
    await screen.findByTestId("html-preview");
    fireEvent.click(
      screen.getByRole("button", { name: "chat.collapseArtifact" }),
    );
    expect(screen.queryByTestId("html-preview")).toBeNull();
    fireEvent.click(
      screen.getByRole("button", { name: "chat.expandArtifact" }),
    );
    show();
    await waitFor(() => expect(request).toHaveBeenCalledTimes(3));
  });

  it("leaves user uploads and non-HTML files as ordinary cards", () => {
    render(
      <>
        <MessageFileCard
          url="/api/file"
          agentId="a"
          workspacePath="inbound/chart.html"
          filename="chart.html"
        />
        <MessageFileCard
          url="/api/file"
          agentId="a"
          workspacePath="outbound/plan.xlsx"
          filename="plan.xlsx"
          inlineHtml
        />
      </>,
    );
    expect(
      screen.queryByRole("button", { name: "chat.collapseArtifact" }),
    ).toBeNull();
    expect(request).not.toHaveBeenCalled();
  });

  it("explains when a delivered HTML file has been deleted", async () => {
    vi.mocked(request).mockRejectedValue(new Error("404 Not Found"));
    render(
      <InlineHtmlArtifact
        agentId="a"
        path="outbound/deleted.html"
        title="deleted"
      />,
    );
    show();
    await screen.findByText("workspace.fileMaybeDeleted");
  });
});
