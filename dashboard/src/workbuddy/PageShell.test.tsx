import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import PageShell from "../layouts/PageShell";
import { DESKTOP_NO_DRAG_CLASS } from "../utils/desktopChrome";

const context = vi.hoisted(() => ({ mobile: false }));
vi.mock("./variant", () => ({ WORKBUDDY_UI: true }));
vi.mock("../hooks/useIsMobile", () => ({ useIsMobile: () => context.mobile }));
vi.mock("../context/AgentContext", () => ({
  useAgent: () => ({
    activeAgent: {
      bridge_disconnected: true,
      bridge_connection_name: "Remote",
      bridge_inbound: true,
    },
  }),
}));
vi.mock("../components/AgentSelector", () => ({
  default: () => <div>Agent selector</div>,
}));
vi.mock("../components/RemoteDisconnectBanner", () => ({
  default: ({ connectionName }: { connectionName: string }) => (
    <div role="alert">{connectionName}</div>
  ),
}));

describe("WorkBuddy page shell", () => {
  it("preserves agent selection, disconnect guidance and an actionable window-safe toolbar", async () => {
    context.mobile = false;
    const onClick = vi.fn();
    render(
      <PageShell
        title="Plugins"
        subtitle="Manage installed plugins"
        agentScoped
        actions={<button onClick={onClick}>Install</button>}
      >
        <input aria-label="Plugin URL" />
      </PageShell>,
    );
    expect(
      screen.getByRole("heading", { name: "Plugins" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Agent selector")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Remote");
    expect(
      screen.getByRole("button", { name: "Install" }).parentElement,
    ).toHaveClass(DESKTOP_NO_DRAG_CLASS);
    await userEvent.click(screen.getByRole("button", { name: "Install" }));
    expect(onClick).toHaveBeenCalledOnce();
  });
  it("keeps mounted form drafts across a toolbar update", async () => {
    const { rerender } = render(
      <PageShell title="Models">
        <input aria-label="Provider name" defaultValue="" />
      </PageShell>,
    );
    await userEvent.type(
      screen.getByRole("textbox", { name: "Provider name" }),
      "Local provider",
    );
    rerender(
      <PageShell title="Models" actions={<button>Save</button>}>
        <input aria-label="Provider name" defaultValue="" />
      </PageShell>,
    );
    expect(screen.getByRole("textbox", { name: "Provider name" })).toHaveValue(
      "Local provider",
    );
  });
  it("keeps mobile path tabs and callbacks available inside a pinned control page", async () => {
    context.mobile = true;
    const onChange = vi.fn();
    render(
      <PageShell
        title="Console"
        pathTabs={{
          value: "terminal",
          options: [
            { value: "terminal", label: "Terminal", icon: null },
            { value: "browser", label: "Browser", icon: null },
          ],
          onChange,
        }}
        fill
      >
        <div>Control session</div>
      </PageShell>,
    );
    await userEvent.click(screen.getByText("Browser"));
    expect(onChange).toHaveBeenCalledWith("browser");
    expect(screen.getByText("Control session")).toBeInTheDocument();
    const toggle = vi.fn();
    window.addEventListener("octop:toggle-nav", toggle);
    await userEvent.click(
      screen.getByRole("button", { name: "nav.expandSidebar" }),
    );
    expect(toggle).toHaveBeenCalledOnce();
    window.removeEventListener("octop:toggle-nav", toggle);
    context.mobile = false;
  });
});
