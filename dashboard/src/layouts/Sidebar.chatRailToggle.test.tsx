import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useEffect } from "react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { LayoutModeProvider } from "../context/LayoutModeContext";
import { EXPAND_CHAT_RAIL_EVENT } from "../pages/Chat/components/ChatSidebarPanel";
import { useChatSidebarOpen } from "../pages/Chat/hooks/useChatSidebarState";
import { LAYOUT_MODE_KEY } from "./layoutModeStorage";
import Sidebar from "./Sidebar";

vi.mock("../components/AvatarDropdown", () => ({
  default: () => null,
}));
vi.mock("../components/AppVersionBadge", () => ({
  default: () => null,
}));
vi.mock("../components/CurrentVersionBadge", () => ({
  default: () => null,
}));
vi.mock("../hooks/useUpdateStatus", () => ({
  useUpdateStatus: () => ({ hasUpdate: false }),
}));
vi.mock("../hooks/useServerCapabilities", () => ({
  useServerCapabilities: () => ({ mobileEnabled: false, loading: false }),
}));

function LocationProbe() {
  const { pathname } = useLocation();
  return <div data-testid="path">{pathname}</div>;
}

function renderSidebar(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <LocationProbe />
      <Sidebar
        selectedKey="chat"
        collapsed={false}
        onToggle={() => undefined}
        isMobile={false}
      />
    </MemoryRouter>,
  );
}

function toggleButton() {
  return screen.getByRole("button", {
    name: /展开对话历史|收起对话历史/,
  });
}

describe("classic chat rail toggle", () => {
  beforeEach(() => {
    localStorage.removeItem(LAYOUT_MODE_KEY);
    const hook = renderHookOpen();
    act(() => hook.setOpen(false));
    hook.unmount();
  });

  it("stays beside Chat and collapses an open history rail", async () => {
    const user = userEvent.setup();
    const onExpand = vi.fn();
    window.addEventListener(EXPAND_CHAT_RAIL_EVENT, onExpand);
    renderSidebar("/chat");

    const button = toggleButton();
    expect(button).toHaveAttribute("aria-expanded", "false");
    expect(button).toHaveAccessibleName("展开对话历史");

    await user.click(button);
    expect(onExpand).toHaveBeenCalledTimes(1);
    expect(button).toHaveAttribute("aria-expanded", "true");
    expect(button).toHaveAccessibleName("收起对话历史");

    await user.click(button);
    expect(onExpand).toHaveBeenCalledTimes(1);
    expect(button).toHaveAttribute("aria-expanded", "false");
    expect(button).toHaveAccessibleName("展开对话历史");

    window.removeEventListener(EXPAND_CHAT_RAIL_EVENT, onExpand);
  });

  it("opens the history rail and goes to chat from another page", async () => {
    const user = userEvent.setup();
    const hook = renderHookOpen();
    act(() => hook.setOpen(true));
    hook.unmount();

    renderSidebar("/experts");
    const button = toggleButton();
    expect(button).toHaveAccessibleName("展开对话历史");

    await user.click(button);
    expect(screen.getByTestId("path")).toHaveTextContent("/chat");
    expect(button).toHaveAccessibleName("收起对话历史");
  });

  it("hides the control in minimal layout", () => {
    localStorage.setItem(LAYOUT_MODE_KEY, "minimal");
    render(
      <LayoutModeProvider>
        <MemoryRouter initialEntries={["/chat"]}>
          <Sidebar
            selectedKey="chat"
            collapsed={false}
            onToggle={() => undefined}
            isMobile={false}
          />
        </MemoryRouter>
      </LayoutModeProvider>,
    );
    expect(
      screen.queryByRole("button", { name: /展开对话历史|收起对话历史/ }),
    ).not.toBeInTheDocument();
  });
});

function renderHookOpen() {
  let setOpen: (open: boolean) => void = () => undefined;
  function Probe() {
    const [, set] = useChatSidebarOpen();
    useEffect(() => {
      setOpen = set;
    }, [set]);
    return null;
  }
  const view = render(<Probe />);
  return {
    setOpen: (open: boolean) => setOpen(open),
    unmount: view.unmount,
  };
}
