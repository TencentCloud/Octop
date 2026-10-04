import { render, screen } from "@testing-library/react";
import { MemoryRouter, type Location } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import Sidebar from "./Sidebar";
import { SettingsBackgroundContext } from "./SettingsBackground";
vi.mock("../context/AgentContext", () => ({
  useAgent: () => ({ activeAgentId: "main" }),
}));
vi.mock("../hooks/useCurrentUser", () => ({
  useCurrentUser: () => null,
  useSetCurrentUser: () => vi.fn(),
}));
vi.mock("./navigationModel", () => ({
  useWorkBuddyNavigation: () => ({ catalog: [], sections: [] }),
}));
vi.mock("./Navigation", () => ({ default: () => null }));
vi.mock("../components/AvatarDropdown", () => ({ default: () => null }));
vi.mock("../layouts/SidebarNavCustomizer", () => ({ default: () => null }));
vi.mock("./HistoryHost", () => ({
  default: () => <div>Fallback history</div>,
}));
describe("settings background history ownership", () => {
  it.each(["/home", "/chat/main/thread"])(
    "does not mount a second history over %s",
    (path) => {
      render(
        <MemoryRouter initialEntries={["/settings/models"]}>
          <SettingsBackgroundContext.Provider
            value={{ pathname: path } as Location}
          >
            <Sidebar collapsed={false} onToggle={() => {}} />
          </SettingsBackgroundContext.Provider>
        </MemoryRouter>,
      );
      expect(screen.queryByText("Fallback history")).not.toBeInTheDocument();
    },
  );
  it("keeps the non-chat history when settings cover a market page", () => {
    render(
      <MemoryRouter initialEntries={["/settings/models"]}>
        <SettingsBackgroundContext.Provider
          value={{ pathname: "/experts" } as Location}
        >
          <Sidebar collapsed={false} onToggle={() => {}} />
        </SettingsBackgroundContext.Provider>
      </MemoryRouter>,
    );
    expect(screen.getByText("Fallback history")).toBeInTheDocument();
  });
});
