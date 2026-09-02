import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import PwaInstallPrompt from "./index";

describe("PwaInstallPrompt in desktop shell", () => {
  afterEach(() => {
    delete (window as Window & { _wails?: unknown })._wails;
  });

  it("hides the install button when the Wails bridge is present", () => {
    Object.defineProperty(window, "_wails", {
      configurable: true,
      value: { invoke: () => undefined },
    });
    render(<PwaInstallPrompt appearance="chatFloat" />);
    expect(screen.queryByLabelText("安装应用")).toBeNull();
  });

  it("still offers install in a regular browser", () => {
    render(<PwaInstallPrompt appearance="chatFloat" />);
    expect(screen.getByLabelText("安装应用")).toBeInTheDocument();
  });
});
