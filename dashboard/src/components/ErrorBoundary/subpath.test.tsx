import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import GlobalErrorBoundary from "./index";

vi.mock("../../i18n", () => ({ default: { t: (key: string) => key } }));

const originalLocation = window.location;
afterEach(() => {
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
  Object.defineProperty(window, "location", {
    configurable: true,
    value: originalLocation,
  });
});

function Broken(): never {
  throw new Error("Synthetic render failure");
}

it.each(["/", "/octop/", "/tools/octop/"])(
  "recovers to the application home under %s",
  (base) => {
    vi.stubEnv("BASE_URL", base);
    const location = { href: `${base}chat/expert/thread` };
    Object.defineProperty(window, "location", {
      configurable: true,
      value: location,
    });
    vi.spyOn(console, "error").mockImplementation(() => {});
    render(
      <GlobalErrorBoundary>
        <Broken />
      </GlobalErrorBoundary>,
    );
    fireEvent.click(screen.getByRole("button", { name: "errors.backHome" }));
    expect(location.href).toBe(`${base}chat`);
  },
);
