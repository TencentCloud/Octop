import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import ThemeSwitcher from "./ThemeSwitcher";

const setPreference = vi.fn();

vi.mock("../context/ThemeContext", () => ({
  useTheme: () => ({ preference: "dark", setPreference }),
}));

describe("ThemeSwitcher", () => {
  it("names each icon button and marks the current theme as pressed", () => {
    render(<ThemeSwitcher />);
    const dark = screen.getByRole("button", { name: "header.themeDark" });
    const light = screen.getByRole("button", { name: "header.themeLight" });
    const system = screen.getByRole("button", { name: "header.themeSystem" });
    expect(dark).toHaveAttribute("aria-pressed", "true");
    expect(light).toHaveAttribute("aria-pressed", "false");
    expect(system).toHaveAttribute("aria-pressed", "false");
    expect(light).toHaveAttribute("type", "button");
  });

  it("does not submit a surrounding form", () => {
    const onSubmit = vi.fn((e: Event) => e.preventDefault());
    render(
      <form onSubmit={(e) => onSubmit(e.nativeEvent)}>
        <ThemeSwitcher compact />
      </form>,
    );
    fireEvent.click(screen.getByRole("button", { name: "header.themeLight" }));
    expect(setPreference).toHaveBeenCalledWith("light");
    expect(onSubmit).not.toHaveBeenCalled();
  });
});
