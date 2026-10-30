import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import FilePreview from "./FilePreview";

vi.mock("../../../../components/Markdown/LazyMarkdown", () => ({
  default: ({ content }: { content: string }) => <div>{content}</div>,
}));
afterEach(cleanup);

function preview(content: string) {
  render(<FilePreview kind="html" content={content} />);
  const doc = new DOMParser().parseFromString(
    screen.getByTitle("HTML preview").getAttribute("srcdoc")!,
    "text/html",
  );
  const scrollTo = vi.fn();
  // Run the exact bootstrap shipped to the iframe against an isolated document.
  const script = doc.head.querySelector("script");
  if (script) {
    new Function("document", "window", "Element", script.textContent!)(
      doc,
      { scrollTo },
      Element,
    );
  }
  const click = () => {
    const event = new MouseEvent("click", { bubbles: true, cancelable: true });
    doc.querySelector("a[href] span")!.dispatchEvent(event);
    return event;
  };
  return { doc, scrollTo, click };
}

describe("HTML file preview fragment navigation", () => {
  it.each([
    ["summary", '<h2 id="summary">Summary</h2>'],
    ["%E6%97%85%E8%A1%8C", '<h2 id="旅行">旅行</h2>'],
    ["legacy", '<a name="legacy">Summary</a>'],
    ["bad%escape", '<h2 id="bad%escape">Summary</h2>'],
  ])(
    "scrolls to %s without navigating to the dashboard",
    (fragment, target) => {
      const { doc, click } = preview(
        `<a href="#${fragment}"><span>Jump</span></a>${target}`,
      );
      const element = doc.querySelector("h2, a[name]")!;
      const scrollIntoView = vi.fn();
      element.scrollIntoView = scrollIntoView;
      expect(click().defaultPrevented).toBe(true);
      expect(scrollIntoView).toHaveBeenCalledOnce();
    },
  );

  it("returns to the top for an empty fragment and blocks navigation to missing targets", () => {
    const { doc, scrollTo, click } = preview(
      '<a href="#"><span>Top</span></a>',
    );
    expect(click().defaultPrevented).toBe(true);
    expect(scrollTo).toHaveBeenCalledWith(0, 0);
    doc.querySelector("a")!.setAttribute("href", "#missing");
    expect(click().defaultPrevented).toBe(true);
  });

  it("preserves relative resource URLs and leaves non-fragment links alone", () => {
    const { doc, click } = preview(
      '<a href="https://example.com/"><span>External</span></a><img src="image.png">',
    );
    expect(click().defaultPrevented).toBe(false);
    expect(doc.querySelector("img")!.getAttribute("src")).toBe("image.png");
    expect(doc.querySelector("base")).toBeNull();
  });

  it("preserves the doctype and user markup while keeping the sandbox opaque", () => {
    const content =
      "<!doctype html><html><head><script>window.ready=true</script></head><body><p>旅行</p></body></html>";
    render(<FilePreview kind="html" content={content} />);
    const frame = screen.getByTitle("HTML preview");
    expect(frame.getAttribute("sandbox")).toBe(
      "allow-scripts allow-popups allow-forms",
    );
    const doc = new DOMParser().parseFromString(
      frame.getAttribute("srcdoc")!,
      "text/html",
    );
    expect(doc.doctype?.name).toBe("html");
    expect(doc.querySelector("p")?.textContent).toBe("旅行");
    expect(doc.head.querySelectorAll("script")[1].textContent).toBe(
      "window.ready=true",
    );
  });
});
