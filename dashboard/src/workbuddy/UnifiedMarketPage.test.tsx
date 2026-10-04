import { useEffect } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation, useNavigate } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import UnifiedMarketPage from "./UnifiedMarketPage";
const state = vi.hoisted(() => ({ mounts: 0 }));
vi.mock("./navigationModel", async () => {
  const { buildNavSections } = await import("../layouts/sidebarNav");
  const catalog = buildNavSections({
    role: "admin",
    id: 1,
    username: "fixture",
    display_name: null,
    locale: "en",
    permissions: [],
  });
  return { useWorkBuddyNavigation: () => ({ catalog, sections: catalog }) };
});
vi.mock("../pages/Experts", () => ({
  default: function MockExperts() {
    useEffect(() => {
      state.mounts++;
    }, []);
    return <input aria-label="Expert filter" defaultValue="" />;
  },
}));
vi.mock("../pages/Agent/Skills", () => ({
  default: () => <div>Skills content</div>,
}));
vi.mock("../pages/Agent/Connectors", () => ({
  default: () => <div>Connector content</div>,
}));
function Host() {
  const location = useLocation();
  const navigate = useNavigate();
  return (
    <>
      <button onClick={() => navigate(-1)}>Browser back</button>
      <output>
        {location.pathname}
        {location.search}
      </output>
      <UnifiedMarketPage location={location} />
    </>
  );
}
describe("Unified market lifecycle", () => {
  it("keeps visited controllers and filters mounted across URL tab changes", async () => {
    state.mounts = 0;
    render(
      <MemoryRouter initialEntries={["/experts?tab=market&source=bookmark"]}>
        <Host />
      </MemoryRouter>,
    );
    await userEvent.type(
      await screen.findByRole("textbox", { name: "Expert filter" }),
      "Saved filter",
    );
    await userEvent.click(
      screen.getByRole("tab", { name: "workbuddy.market.skills" }),
    );
    await screen.findByText("Skills content");
    await userEvent.click(screen.getByRole("button", { name: "Browser back" }));
    expect(
      screen.getByText("/experts?tab=market&source=bookmark"),
    ).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Expert filter" })).toHaveValue(
      "Saved filter",
    );
    await waitFor(() => expect(state.mounts).toBe(1));
  });
});
