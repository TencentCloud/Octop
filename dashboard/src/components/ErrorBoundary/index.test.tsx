import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import GlobalErrorBoundary from ".";

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
});

function Detonate() {
  throw new Error("Cannot read properties of undefined (reading 'rows')");
}

describe("GlobalErrorBoundary unexpected failures", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    tryReloadOnStaleChunk.mockReset();
    tryReloadOnStaleChunk.mockReturnValue(false);
  });

  it("leads with copy a person can act on, not the raw exception", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    render(
      <GlobalErrorBoundary>
        <Detonate />
      </GlobalErrorBoundary>,
    );

    expect(screen.getByRole("heading")).toHaveTextContent(
      "errors.unexpectedTitle",
    );
    // The message still exists — it just is not the headline any more.
    expect(screen.getByText(/reading 'rows'/)).toBeInTheDocument();
  });

  it("keeps the exception behind a disclosure", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    render(
      <GlobalErrorBoundary>
        <Detonate />
      </GlobalErrorBoundary>,
    );

    const details = screen.getByText(/reading 'rows'/).closest("details");
    expect(details).not.toBeNull();
    expect(details?.open).toBe(false);
    expect(screen.getByText("errors.details")).toBeInTheDocument();
  });
});
