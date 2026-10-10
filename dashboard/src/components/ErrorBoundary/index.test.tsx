import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import GlobalErrorBoundary from ".";

const originalLocation = window.location;

// The boundary reads copy through the real i18n instance, which is not
// initialized in unit tests (initI18n runs in main.tsx). Return the key so
// button labels stay deterministic (e.g. "errors.reload" → reload button).
vi.mock("../../i18n", () => ({
  default: {
    t: (key: string) => key,
  },
}));

const { tryReloadOnStaleChunk } = vi.hoisted(() => ({
  tryReloadOnStaleChunk: vi.fn(),
}));

vi.mock("../../utils/reloadOnStaleChunk", async (importOriginal) => {
  const actual = await importOriginal<
    typeof import("../../utils/reloadOnStaleChunk")
  >();
  return { ...actual, tryReloadOnStaleChunk };
});

function Boom() {
  throw new Error("Failed to fetch dynamically imported module: /assets/a.js");
}

function renderBoundary() {
  vi.spyOn(console, "error").mockImplementation(() => {});
  return render(
    <GlobalErrorBoundary>
      <Boom />
    </GlobalErrorBoundary>,
  );
}

describe("GlobalErrorBoundary chunk failures", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    tryReloadOnStaleChunk.mockReset();
  });

  afterEach(() => {
    Object.defineProperty(window, "location", {
      configurable: true,
      value: originalLocation,
    });
  });

  it("renders nothing while a recovery reload is under way", () => {
    tryReloadOnStaleChunk.mockReturnValue(true);

    const { container } = renderBoundary();

    expect(container).toBeEmptyDOMElement();
  });

  it("offers a way out when no recovery reload will happen", () => {
    tryReloadOnStaleChunk.mockReturnValue(false);

    renderBoundary();

    expect(screen.getByRole("button", { name: /reload/i })).toBeInTheDocument();
  });

  it.each([
    ["/chat/agent-a/thr_1", "/chat"],
    ["/embed/chat/agent-a/thr_1", "/embed/chat/agent-a"],
  ])("keeps recovery from %s in the same surface", (pathname, expected) => {
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { pathname, href: pathname },
    });
    renderBoundary();
    fireEvent.click(screen.getByRole("button", { name: "errors.backHome" }));
    expect(window.location.href).toBe(expected);
  });

  it("does not offer a console exit when the embedded agent is missing", () => {
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { pathname: "/embed/chat" },
    });
    renderBoundary();
    expect(
      screen.queryByRole("button", { name: "errors.backHome" }),
    ).toBeNull();
  });
});
