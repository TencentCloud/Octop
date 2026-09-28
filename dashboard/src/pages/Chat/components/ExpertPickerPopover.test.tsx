import { describe, expect, it, beforeEach, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import ExpertPickerPopover from "./ExpertPickerPopover";
import {
  HIDDEN_SHARED_EXPERTS_STORAGE_KEY,
  hiddenExpertsStorageKey,
} from "../utils/hiddenExpertsPrefs";

vi.mock("../../../hooks/useCurrentUser", () => ({
  useCurrentUser: () => ({ id: 1, username: "tester" }),
}));

const agents = [
  {
    agent_id: "own-1",
    name: "我的专家",
    is_shared: false,
    is_owner: true,
  },
  {
    agent_id: "shared-1",
    name: "共享专家甲",
    is_shared: true,
    is_owner: false,
  },
  {
    agent_id: "shared-2",
    name: "共享专家乙",
    is_shared: true,
    is_owner: false,
  },
];

const HIDE_BUTTON_NAME = /chat\.expertHide|Hide shared expert|隐藏共享专家/;
const UNHIDE_BUTTON_NAME = /chat\.expertUnhide|Show expert again|重新显示专家/;
const HIDDEN_TOGGLE_NAME = /chat\.expertPickerHidden|Hidden experts|已隐藏专家/;

/** The picker row (select button + hide button) that renders `expertName`. */
function rowOf(expertName: string): HTMLElement {
  const row = screen.getByText(expertName).closest("div");
  if (!row) throw new Error(`picker row not found for ${expertName}`);
  return row as HTMLElement;
}

const hideButtonIn = (expertName: string) =>
  within(rowOf(expertName)).getByRole("button", { name: HIDE_BUTTON_NAME });

const unhideButtonIn = (expertName: string) =>
  within(rowOf(expertName)).getByRole("button", { name: UNHIDE_BUTTON_NAME });

const hiddenToggle = () =>
  screen.getByRole("button", { name: HIDDEN_TOGGLE_NAME });

function renderPicker() {
  const onSelect = vi.fn();
  render(
    <MemoryRouter>
      <ExpertPickerPopover
        agents={agents}
        selectedAgentIds={[]}
        onSelect={onSelect}
      />
    </MemoryRouter>,
  );
  return onSelect;
}

describe("ExpertPickerPopover hide experts", () => {
  beforeEach(() => {
    localStorage.removeItem(HIDDEN_SHARED_EXPERTS_STORAGE_KEY);
    localStorage.removeItem(hiddenExpertsStorageKey(1));
  });

  it("hides a shared expert and can restore via hidden list", async () => {
    const user = userEvent.setup();
    const onSelect = renderPicker();

    expect(screen.getByText("共享专家甲")).toBeInTheDocument();
    expect(screen.getByText("共享专家乙")).toBeInTheDocument();
    expect(screen.getByText("我的专家")).toBeInTheDocument();

    // 放开隐藏后每个专家（含自建）都可隐藏：2 共享 + 1 自建 = 3。
    const hideButtons = screen.getAllByRole("button", {
      name: HIDE_BUTTON_NAME,
    });
    expect(hideButtons.length).toBe(3);
    await user.click(hideButtonIn("共享专家甲"));

    expect(screen.queryByText("共享专家甲")).not.toBeInTheDocument();
    expect(screen.getByText("共享专家乙")).toBeInTheDocument();

    await user.click(hiddenToggle());
    expect(screen.getByText("共享专家甲")).toBeInTheDocument();

    await user.click(unhideButtonIn("共享专家甲"));
    // Last hidden expert restored → auto-return to the visible list.
    expect(screen.getByText("共享专家甲")).toBeInTheDocument();
    expect(screen.getByText("共享专家乙")).toBeInTheDocument();
    expect(screen.getByText("我的专家")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: HIDDEN_TOGGLE_NAME }),
    ).not.toBeInTheDocument();
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("hides an owned expert and can restore it", async () => {
    const user = userEvent.setup();
    renderPicker();

    await user.click(hideButtonIn("我的专家"));

    // 自建专家可隐藏：从可见列表消失，且落进未变的 storage key。
    expect(screen.queryByText("我的专家")).not.toBeInTheDocument();
    expect(screen.getByText("共享专家甲")).toBeInTheDocument();
    expect(screen.getByText("共享专家乙")).toBeInTheDocument();
    expect(localStorage.getItem(hiddenExpertsStorageKey(1))).toBe('["own-1"]');

    // 「已隐藏」视图里能找回自建专家并恢复。
    await user.click(hiddenToggle());
    expect(screen.getByText("我的专家")).toBeInTheDocument();
    await user.click(unhideButtonIn("我的专家"));

    expect(screen.getByText("我的专家")).toBeInTheDocument();
    expect(screen.getByText("共享专家甲")).toBeInTheDocument();
    expect(screen.getByText("共享专家乙")).toBeInTheDocument();
    expect(localStorage.getItem(hiddenExpertsStorageKey(1))).toBeNull();
    expect(
      screen.queryByRole("button", { name: HIDDEN_TOGGLE_NAME }),
    ).not.toBeInTheDocument();
  });
});
