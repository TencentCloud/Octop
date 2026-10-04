import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import Navigation from "./Navigation";
import { buildNavSections } from "../layouts/sidebarNav";
const state = vi.hoisted(() => ({ mobile: true }));
vi.mock("../hooks/useIsMobile", () => ({ useIsMobile: () => state.mobile }));
const sections = buildNavSections({
  id: 1,
  username: "test",
  display_name: null,
  role: "admin",
  permissions: [],
  locale: "en",
});
describe("market navigation", () => {
  it("opens the mobile submenu without navigating or closing the sidebar first", async () => {
    state.mobile = true;
    const navigate = vi.fn();
    render(
      <MemoryRouter>
        <Navigation compact={false} onNavigate={navigate} sections={sections} />
      </MemoryRouter>,
    );
    await userEvent.click(
      screen.getByRole("button", { name: "workbuddy.market.title" }),
    );
    expect(navigate).not.toHaveBeenCalled();
    await userEvent.click(
      await screen.findByRole("menuitem", { name: "workbuddy.market.skills" }),
    );
    expect(navigate).toHaveBeenCalledExactlyOnceWith("/skills");
    expect(
      screen.getByRole("button", { name: "workbuddy.market.title" }),
    ).toHaveAttribute("aria-expanded", "false");
  });
  it("keeps desktop click as a direct expert entry", async () => {
    state.mobile = false;
    const navigate = vi.fn();
    render(
      <MemoryRouter>
        <Navigation compact={false} onNavigate={navigate} sections={sections} />
      </MemoryRouter>,
    );
    await userEvent.click(
      screen.getByRole("button", { name: "workbuddy.market.title" }),
    );
    expect(navigate).toHaveBeenCalledExactlyOnceWith("/experts");
  });
});
