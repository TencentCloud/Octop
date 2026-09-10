import { act, render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import PdfDocumentPreview from "./PdfDocumentPreview";

/**
 * react-pdf is mocked: Document reports a 4-page PDF whose pages are all
 * 2:1 (height:width) at scale 1, and Page just renders a marker div.
 */
/** Outline data served by the mocked PDF instance (hoisted for the
 * vi.mock factory below). */
const outlineState = vi.hoisted(() => ({
  items: null as { title: string; dest?: unknown; items?: unknown[] }[] | null,
  dests: {} as Record<string, unknown[]>,
}));

vi.mock("react-pdf", async () => {
  const React = await import("react");
  const Document = ({
    onLoadSuccess,
    children,
  }: {
    onLoadSuccess?: (pdf: unknown) => void;
    children?: React.ReactNode;
  }) => {
    React.useLayoutEffect(() => {
      onLoadSuccess?.({
        numPages: 4,
        getPage: async () => ({
          getViewport: () => ({ width: 500, height: 1000 }),
        }),
        getOutline: async () => outlineState.items,
        getDestination: async (id: string) => outlineState.dests[id] ?? null,
        getPageIndex: async (ref: { num: number }) => ref.num - 1,
      });
    }, [onLoadSuccess]);
    return <div data-testid="pdf-document">{children}</div>;
  };
  const Page = ({
    pageNumber,
    onRenderSuccess,
  }: {
    pageNumber: number;
    onRenderSuccess?: () => void;
  }) => {
    React.useLayoutEffect(() => {
      onRenderSuccess?.();
    }, [onRenderSuccess]);
    return <div data-testid={`pdf-page-${pageNumber}`} />;
  };
  return {
    Document,
    Page,
    pdfjs: { GlobalWorkerOptions: { workerSrc: "" } },
  };
});

interface FakeEntry {
  target: HTMLElement;
  isIntersecting: boolean;
  intersectionRatio?: number;
  boundingClientRect?: DOMRect;
}

class FakeIntersectionObserver {
  static instances: FakeIntersectionObserver[] = [];
  callback: (entries: FakeEntry[]) => void;
  targets = new Set<Element>();
  options?: IntersectionObserverInit;

  constructor(
    callback: (entries: FakeEntry[]) => void,
    options?: IntersectionObserverInit,
  ) {
    this.callback = callback;
    this.options = options;
    FakeIntersectionObserver.instances.push(this);
  }

  observe(target: Element) {
    this.targets.add(target);
  }

  unobserve(target: Element) {
    this.targets.delete(target);
  }

  disconnect() {
    this.targets.clear();
  }

  emit(entries: FakeEntry[]) {
    this.callback(entries);
  }
}

/** Emit to every live observer still watching the slot (windowing + current page). */
function emitSlot(
  target: HTMLElement,
  isIntersecting: boolean,
  intersectionRatio = isIntersecting ? 0.6 : 0,
) {
  const rect = target.getBoundingClientRect();
  for (const observer of FakeIntersectionObserver.instances) {
    if (!observer.targets.has(target)) continue;
    observer.emit([
      {
        target,
        isIntersecting,
        intersectionRatio,
        boundingClientRect: rect,
      },
    ]);
  }
}

class FakeResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

function slot(container: HTMLElement, pageNo: number) {
  return container.querySelector<HTMLElement>(
    `[data-pdf-page="${pageNo}"]`,
  ) as HTMLElement;
}

/** Settle Document onLoadSuccess + follow-up ratio/outline promises under act(). */
async function flushPdfAsync() {
  for (let i = 0; i < 3; i += 1) {
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
      await vi.advanceTimersByTimeAsync(250);
    });
  }
}

async function renderPdf(ui: Parameters<typeof render>[0]) {
  const result = render(ui);
  await flushPdfAsync();
  return result;
}

function mountedPages(container: HTMLElement) {
  return Array.from(
    container.querySelectorAll<HTMLElement>('[data-testid^="pdf-page-"]'),
  ).map((el) => el.getAttribute("data-testid"));
}

describe("PdfDocumentPreview windowed rendering", () => {
  let consoleErrorSpy: ReturnType<typeof vi.spyOn> | undefined;

  beforeEach(() => {
    FakeIntersectionObserver.instances = [];
    vi.stubGlobal("IntersectionObserver", FakeIntersectionObserver);
    vi.stubGlobal("ResizeObserver", FakeResizeObserver);
    vi.useFakeTimers({ shouldAdvanceTime: true });
    // react-pdf mock resolves outline/ratio promises outside the render act
    // boundary; filter that noise so real failures stay visible.
    const original = console.error.bind(console);
    consoleErrorSpy = vi
      .spyOn(console, "error")
      .mockImplementation((...args: unknown[]) => {
        const msg = String(args[0] ?? "");
        if (msg.includes("not wrapped in act")) return;
        original(...(args as Parameters<typeof console.error>));
      });
  });

  afterEach(async () => {
    await flushPdfAsync();
    consoleErrorSpy?.mockRestore();
    consoleErrorSpy = undefined;
    vi.useRealTimers();
    vi.unstubAllGlobals();
    outlineState.items = null;
    outlineState.dests = {};
  });

  it("renders size-accurate placeholders and mounts only intersecting pages", async () => {
    const { container } = await renderPdf(
      <PdfDocumentPreview fileUrl="blob:test" filename="test.pdf" />,
    );

    // All 4 page slots exist once the document reports its page count.
    await waitFor(() => {
      expect(slot(container, 1)).toBeTruthy();
      expect(slot(container, 4)).toBeTruthy();
    });

    // Page 1 is seeded visible so the first canvas can paint under the
    // boot overlay; other pages stay placeholders until they intersect.
    await waitFor(() => {
      expect(mountedPages(container)).toEqual(["pdf-page-1"]);
    });

    // Ratios prefetched (2:1) make placeholder heights exact:
    // width 720 (default measure without a real container) -> height 1440.
    await waitFor(() => {
      expect(slot(container, 1).style.height).toBe("1440px");
    });

    const observers = FakeIntersectionObserver.instances.filter(
      (o) => o.targets.size === 4,
    );
    expect(observers.length).toBeGreaterThanOrEqual(1);

    emitSlot(slot(container, 2), true);
    await waitFor(() => {
      expect(mountedPages(container).sort()).toEqual([
        "pdf-page-1",
        "pdf-page-2",
      ]);
    });
  });

  it("keeps a nearby page mounted after it leaves the viewport", async () => {
    const { container } = await renderPdf(
      <PdfDocumentPreview fileUrl="blob:test" filename="test.pdf" />,
    );
    await waitFor(() => {
      expect(slot(container, 3)).toBeTruthy();
    });

    emitSlot(slot(container, 3), true);
    await waitFor(() => {
      expect(mountedPages(container).sort()).toEqual([
        "pdf-page-1",
        "pdf-page-3",
      ]);
    });

    // Still within MOUNT_KEEP_RADIUS of current page 1 — keep canvas mounted.
    emitSlot(slot(container, 3), false);
    await waitFor(() => {
      expect(mountedPages(container).sort()).toEqual([
        "pdf-page-1",
        "pdf-page-3",
      ]);
    });
  });

  it("unmounts a page once it is far from the current page", async () => {
    const { container } = await renderPdf(
      <PdfDocumentPreview fileUrl="blob:test" filename="test.pdf" />,
    );
    await waitFor(() => {
      expect(slot(container, 4)).toBeTruthy();
    });

    emitSlot(slot(container, 4), true);
    await waitFor(() => {
      expect(mountedPages(container).sort()).toEqual([
        "pdf-page-1",
        "pdf-page-4",
      ]);
    });

    // Leaving page 4 alone can leave currentPage stuck on 4 (no other
    // intersecting ratios). Re-assert page 1 as the reading position so the
    // keep-radius prune can drop the far sticky mount.
    emitSlot(slot(container, 4), false);
    emitSlot(slot(container, 1), true, 1);
    await waitFor(() => {
      expect(mountedPages(container)).toEqual(["pdf-page-1"]);
    });
  });

  it("mounts every page when IntersectionObserver is unavailable", async () => {
    vi.stubGlobal("IntersectionObserver", undefined);
    vi.resetModules();
    const { default: PdfNoIO } = await import("./PdfDocumentPreview");
    const { container } = await renderPdf(
      <PdfNoIO fileUrl="blob:test" filename="test.pdf" />,
    );
    await waitFor(() => {
      expect(mountedPages(container)).toHaveLength(4);
    });
  });

  it("shows the outline sidebar and scrolls a bookmark to its page", async () => {
    outlineState.items = [
      {
        title: "第一章",
        dest: "ch1",
        items: [{ title: "1.1 小节", dest: [{ num: 3 }] }],
      },
      { title: "外部链接", url: "https://example.com" },
    ];
    outlineState.dests = { ch1: [{ num: 2 }] };
    const scrollIntoView = vi.fn();
    Element.prototype.scrollIntoView = scrollIntoView;

    const { container } = await renderPdf(
      <PdfDocumentPreview fileUrl="blob:test" filename="book.pdf" />,
    );
    await waitFor(() => {
      expect(slot(container, 1)).toBeTruthy();
    });
    await flushPdfAsync();

    // Outline stays closed by default — open via the toolbar toggle.
    const toggle = await waitFor(() => {
      const btn = Array.from(container.querySelectorAll("button")).find(
        (b) =>
          b.getAttribute("aria-label") === "书签" ||
          b.getAttribute("aria-label") === "Outline",
      );
      expect(btn?.disabled).toBeFalsy();
      return btn as HTMLElement;
    });
    expect(container.querySelector("nav")).toBeNull();
    await act(async () => {
      toggle.click();
    });
    const nav = await waitFor(() => {
      const el = container.querySelector("nav");
      expect(el).toBeTruthy();
      return el as HTMLElement;
    });
    const labels = Array.from(nav.querySelectorAll("button, a")).map(
      (el) => el.textContent,
    );
    expect(labels).toEqual(["第一章", "1.1 小节", "外部链接"]);

    // Toggle collapses the sidebar.
    await act(async () => {
      toggle.click();
    });
    await waitFor(() => {
      expect(container.querySelector("nav")).toBeNull();
    });
    await act(async () => {
      toggle.click();
    });
    await waitFor(() => {
      expect(container.querySelector("nav")).toBeTruthy();
    });

    // Named destination "ch1" resolves to page 2 and scrolls its slot.
    const nav2 = container.querySelector("nav") as HTMLElement;
    await act(async () => {
      (
        Array.from(nav2.querySelectorAll("button")).find(
          (el) => el.textContent === "第一章",
        ) as HTMLElement
      ).click();
    });
    await waitFor(() => {
      expect(scrollIntoView).toHaveBeenCalled();
    });
    await flushPdfAsync();
    const target = scrollIntoView.mock.contexts[0] as HTMLElement;
    expect(target.dataset.pdfPage).toBe("2");

    // External-link bookmarks render as anchors.
    const link = nav2.querySelector(
      "a[href='https://example.com']",
    ) as HTMLAnchorElement;
    expect(link.target).toBe("_blank");
  });
});
