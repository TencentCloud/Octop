import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import SceneTabs from "./SceneTabs";
import DeferredFeature from "../pages/DeferredFeature";
import WorkBuddyNavigation from "./Navigation";

describe("WorkBuddy display interactions", () => {
  it("opens the current workspace from More without navigating or creating a replacement resource", async () => {
    const onOpenFiles = vi.fn(),
      onNavigate = vi.fn();
    render(
      <MemoryRouter>
        <WorkBuddyNavigation
          compact={false}
          onNavigate={onNavigate}
          onOpenFiles={onOpenFiles}
        />
      </MemoryRouter>,
    );
    await userEvent.click(
      screen.getByRole("button", { name: "workbuddy.moreCapabilities" }),
    );
    await userEvent.click(
      await screen.findByRole("menuitem", { name: "workbuddy.files" }),
    );
    expect(onOpenFiles).toHaveBeenCalledOnce();
    expect(onNavigate).not.toHaveBeenCalled();
  });

  it("disables the file action when no agent workspace is selected", async () => {
    const onOpenFiles = vi.fn();
    render(
      <MemoryRouter>
        <WorkBuddyNavigation
          compact={false}
          onNavigate={vi.fn()}
          onOpenFiles={onOpenFiles}
          filesAvailable={false}
        />
      </MemoryRouter>,
    );
    await userEvent.click(
      screen.getByRole("button", { name: "workbuddy.moreCapabilities" }),
    );
    const files = await screen.findByRole("menuitem", {
      name: "workbuddy.files",
    });
    expect(files).toHaveAttribute("aria-disabled", "true");
    await userEvent.click(files);
    expect(onOpenFiles).not.toHaveBeenCalled();
  });

  it("offers scene selection without executing a conversation mode", async () => {
    const onChange = vi.fn();
    render(<SceneTabs value="work" onChange={onChange} />);
    expect(
      screen.getByRole("button", { name: "workbuddy.scenes.work" }),
    ).toHaveAttribute("aria-pressed", "true");
    await userEvent.click(
      screen.getByRole("button", { name: "workbuddy.scenes.code" }),
    );
    expect(onChange).toHaveBeenCalledExactlyOnceWith("code");
  });
  it("renders unavailable capabilities with no save, connect or execute controls", () => {
    render(
      <MemoryRouter>
        <DeferredFeature feature="projects" />
      </MemoryRouter>,
    );
    expect(
      screen.getByRole("heading", { level: 1, name: /workbuddy.projects/ }),
    ).toHaveTextContent("workbuddy.projects");
    expect(
      screen.getByRole("button", { name: "workbuddy.newProject" }),
    ).toBeDisabled();
    expect(screen.getByRole("searchbox")).toBeDisabled();
    expect(
      screen
        .getAllByRole("button")
        .filter((button) => !(button as HTMLButtonElement).disabled),
    ).toHaveLength(1);
    expect(
      screen.getByRole("button", { name: "workbuddy.backHome" }),
    ).toBeEnabled();
  });
  it("retains home and deferred navigation separately from persisted nav preferences", async () => {
    const onNavigate = vi.fn();
    render(
      <MemoryRouter initialEntries={["/home"]}>
        <WorkBuddyNavigation compact={false} onNavigate={onNavigate} />
      </MemoryRouter>,
    );
    const home = screen.getByRole("link", { name: "workbuddy.newTask" });
    expect(home).toHaveAttribute("aria-current", "page");
    await userEvent.click(
      screen.getByRole("link", { name: /workbuddy.projects/ }),
    );
    expect(onNavigate).toHaveBeenCalledOnce();
  });
});
