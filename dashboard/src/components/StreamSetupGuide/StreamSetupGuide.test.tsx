import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const isMobileRef = { current: false };

vi.mock("../../hooks/useIsMobile", () => ({
  useIsMobile: () => isMobileRef.current,
}));

import StreamSetupGuide from "./StreamSetupGuide";

function renderGuide() {
  return render(
    <StreamSetupGuide
      icon={<span />}
      title="Guide"
      steps={[]}
      primaryAction={{
        label: "启动浏览器",
        onClick: () => undefined,
      }}
      secondaryAction={{
        label: "检查",
        onClick: () => undefined,
        type: "default",
        title: "检查本机是否已准备好浏览器",
      }}
    />,
  );
}

describe("StreamSetupGuide actions", () => {
  it("keeps desktop actions content-sized", () => {
    isMobileRef.current = false;
    renderGuide();

    const start = screen.getByRole("button", { name: "启动浏览器" });
    const check = screen.getByRole("button", { name: /检\s*查/ });
    expect(start.className).not.toMatch(/ant-btn-block/);
    expect(check.className).not.toMatch(/ant-btn-block/);
  });

  it("stretches mobile actions to the same full width", () => {
    isMobileRef.current = true;
    renderGuide();

    const start = screen.getByRole("button", { name: "启动浏览器" });
    const check = screen.getByRole("button", { name: /检\s*查/ });
    expect(start.className).toMatch(/ant-btn-block/);
    expect(check.className).toMatch(/ant-btn-block/);
  });
});
