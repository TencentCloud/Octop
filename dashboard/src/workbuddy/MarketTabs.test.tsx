import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import MarketTabs from "./MarketTabs";

describe("expert-centre display tabs", () => {
  it("loads a pane on first visit and keeps its draft when navigating away", async () => {
    const mounted = vi.fn();
    function Market() {
      mounted();
      return <input aria-label="Market search" />;
    }
    function Fixture() {
      const [activeKey, setActiveKey] = useState("agents");
      return (
        <MarketTabs
          activeKey={activeKey}
          onChange={setActiveKey}
          items={[
            { key: "agents", label: "Agents", children: <p>Owned agents</p> },
            { key: "market", label: "Market", children: <Market /> },
          ]}
        />
      );
    }
    render(<Fixture />);
    expect(mounted).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("tab", { name: "Market" }));
    const input = screen.getByRole("textbox", { name: "Market search" });
    await userEvent.type(input, "Research");
    await userEvent.click(screen.getByRole("tab", { name: "Agents" }));
    expect(
      screen.queryByRole("textbox", { name: "Market search" }),
    ).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "Market" }));
    expect(screen.getByRole("textbox", { name: "Market search" })).toBe(input);
    expect(input).toHaveValue("Research");
  });
  it("supports keyboard switching with a linked panel", async () => {
    const onChange = vi.fn();
    render(
      <MarketTabs
        activeKey="agents"
        onChange={onChange}
        items={[
          { key: "agents", label: "Agents", children: <p>Owned agents</p> },
          { key: "teams", label: "Teams", children: <p>Teams</p> },
        ]}
      />,
    );
    screen.getByRole("tab", { name: "Agents" }).focus();
    await userEvent.keyboard("{ArrowRight}");
    expect(onChange).toHaveBeenCalledExactlyOnceWith("teams");
    expect(screen.getByRole("tab", { name: "Teams" })).toHaveFocus();
    expect(screen.getByRole("tabpanel")).toHaveAttribute(
      "aria-labelledby",
      screen.getByRole("tab", { name: "Agents" }).id,
    );
  });
  it("preserves a pane opened by an external create callback", async () => {
    const items = [
      { key: "agents", label: "Agents", children: <p>Agents</p> },
      {
        key: "teams",
        label: "Teams",
        children: <input aria-label="Team draft" />,
      },
    ];
    const { rerender } = render(
      <MarketTabs activeKey="agents" onChange={() => {}} items={items} />,
    );
    rerender(
      <MarketTabs activeKey="teams" onChange={() => {}} items={items} />,
    );
    const input = screen.getByRole("textbox", { name: "Team draft" });
    await userEvent.type(input, "Team name");
    rerender(
      <MarketTabs activeKey="agents" onChange={() => {}} items={items} />,
    );
    rerender(
      <MarketTabs activeKey="teams" onChange={() => {}} items={items} />,
    );
    expect(screen.getByRole("textbox", { name: "Team draft" })).toBe(input);
    expect(input).toHaveValue("Team name");
  });
});
