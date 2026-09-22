import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("../context/ThemeContext", () => ({
  useTheme: () => ({ isDark: false }),
}));

vi.mock("../components/PwaInstallPrompt", () => ({
  default: () => null,
}));

vi.mock("../components/AppVersionBadge", () => ({
  default: () => null,
}));

vi.mock("../components/CurrentVersionBadge", () => ({
  default: () => null,
}));

import Header from "./Header";

describe("Header", () => {
  it("pads mobile chrome for iOS PWA safe-area inset", () => {
    render(<Header isMobile onToggle={() => undefined} />);
    const header = screen.getByRole("banner");
    expect(header.style.height).toContain("safe-area-inset-top");
    expect(header.style.padding).toContain("safe-area-inset-top");
  });

  it("keeps the status-bar inset opaque so iOS does not frost page content", () => {
    render(<Header isMobile onToggle={() => undefined} />);
    const header = screen.getByRole("banner");
    expect(header.style.backdropFilter).toBe("none");
    expect(header.style.WebkitBackdropFilter).toBe("none");
  });

  it("renders nothing on desktop", () => {
    const { container } = render(<Header isMobile={false} />);
    expect(container).toBeEmptyDOMElement();
  });
});
