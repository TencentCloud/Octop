import { act, render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import HtmlArtifactPreview, {
  htmlPreviewDocument,
} from "./HtmlArtifactPreview";

describe("HTML artifact preview", () => {
  it("enforces self-contained resource policy before user scripts", () => {
    const html = htmlPreviewDocument(
      '<html><head><base href="https://example.com"><meta http-equiv="refresh" content="0;url=https://example.com"></head><body><svg></svg><script>window.ready=true</script></body></html>',
      "test-instance",
    );
    const doc = new DOMParser().parseFromString(html, "text/html");
    expect(doc.querySelector("base")).toBeNull();
    expect(doc.querySelector('meta[http-equiv="refresh"]')).toBeNull();
    expect(doc.head.firstElementChild?.getAttribute("content")).toContain(
      "connect-src 'none'",
    );
    expect(doc.querySelector("svg")).toBeTruthy();
    expect(html).toContain("window.ready=true");
  });

  it("accepts height reports only from its own frame and instance, and clamps them", () => {
    const { container, unmount } = render(
      <HtmlArtifactPreview
        content="<p>图表</p>"
        title="分层图"
        mode="inline"
      />,
    );
    const frame = container.querySelector("iframe")!;
    expect(frame.getAttribute("sandbox")).toBe("allow-scripts");
    expect(frame.style.height).toBe("360px");
    const instance = /instance: ("[^"]+")/.exec(frame.srcdoc)![1];
    const report = (
      height: number,
      source: MessageEventSource | null = frame.contentWindow,
      id = JSON.parse(instance),
    ) =>
      act(() => {
        window.dispatchEvent(
          new MessageEvent("message", {
            source,
            data: { type: "octop-html-height", instance: id, height },
          }),
        );
      });
    report(600, window);
    report(600, frame.contentWindow, "other");
    report(NaN);
    expect(frame.style.height).toBe("360px");
    report(1200);
    expect(frame.style.height).toBe("800px");
    report(100);
    expect(frame.style.height).toBe("200px");
    unmount();
  });
});
