import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import GlobalErrorBoundary from ".";

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
