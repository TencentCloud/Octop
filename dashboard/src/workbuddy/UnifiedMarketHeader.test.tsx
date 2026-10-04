import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import UnifiedMarketHeader from "./UnifiedMarketHeader";
import { MARKET_TABS } from "./marketModel";
describe("Unified market header", () => {
  it("supports keyboard selection and announces the active tab", async () => {
    const onSelect = vi.fn();
    render(
      <UnifiedMarketHeader
        tabs={MARKET_TABS}
        active="experts"
        onSelect={onSelect}
      />,
    );
    const expert = screen.getByRole("tab", {
      name: "workbuddy.market.experts",
    });
    expert.focus();
    await userEvent.keyboard("{ArrowRight}");
    expect(onSelect).toHaveBeenCalledWith(MARKET_TABS[1]);
    expect(
      screen.getByRole("tab", { name: "workbuddy.market.skills" }),
    ).toHaveFocus();
    expect(expert).toHaveAttribute("aria-selected", "true");
  });
});
