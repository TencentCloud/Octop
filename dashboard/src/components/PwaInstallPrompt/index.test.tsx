import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import PwaInstallPrompt from "./index";

type BridgeHost = Window & { octopDesktop?: unknown };

describe("PwaInstallPrompt in desktop shell", () => {
  afterEach(() => {
    delete (window as BridgeHost).octopDesktop;
  });

  it("hides the install button when the preload bridge is present", () => {
    Object.defineProperty(window, "octopDesktop", {
      configurable: true,
      value: {},
    });
    render(<PwaInstallPrompt appearance="chatFloat" />);
    expect(screen.queryByLabelText("安装应用")).toBeNull();
  });

  it("still offers install in a regular browser", () => {
    render(<PwaInstallPrompt appearance="chatFloat" />);
    expect(screen.getByLabelText("安装应用")).toBeInTheDocument();
  });
});
