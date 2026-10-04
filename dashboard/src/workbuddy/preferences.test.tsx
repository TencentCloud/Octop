import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  resolveAssistantPinned,
  useWorkBuddyAppearance,
  useAssistantPanelPreference,
  WORKBUDDY_APPEARANCE_KEY,
  WORKBUDDY_ASSISTANT_PIN_KEY,
} from "./preferences";

beforeEach(() => localStorage.clear());
afterEach(() => vi.restoreAllMocks());

function PreferencesProbe() {
  const [custom, setCustom] = useWorkBuddyAppearance();
  const [pinned, setPinned] = useAssistantPanelPreference();
  return (
    <>
      <button onClick={() => setCustom(!custom)}>
        {custom ? "custom" : "standard"}
      </button>
      <button onClick={() => setPinned(!pinned)}>
        {pinned ? "pinned" : "floating"}
      </button>
    </>
  );
}

describe("WorkBuddy preference migration", () => {
  it.each([
    [null, null, "classic", true],
    [null, null, "minimal", false],
    [null, "true", "minimal", true],
    [null, "false", "classic", false],
    ["true", "false", "minimal", true],
    ["false", "true", "classic", false],
  ])("maps %s / %s / %s to pinned=%s", (stored, open, layout, expected) => {
    expect(resolveAssistantPinned(stored, open, layout)).toBe(expected);
  });
  it("defaults to source appearance without destroying legacy palette and layout values", async () => {
    localStorage.setItem("octop:palette", "rose");
    localStorage.setItem("octop:layout-mode", "minimal");
    localStorage.setItem("octop:chat-sidebar:open", "true");
    render(<PreferencesProbe />);
    await userEvent.click(screen.getByRole("button", { name: "standard" }));
    await userEvent.click(screen.getByRole("button", { name: "pinned" }));
    expect(localStorage.getItem(WORKBUDDY_APPEARANCE_KEY)).toBe("custom");
    expect(localStorage.getItem(WORKBUDDY_ASSISTANT_PIN_KEY)).toBe("false");
    expect(localStorage.getItem("octop:palette")).toBe("rose");
    expect(localStorage.getItem("octop:layout-mode")).toBe("minimal");
    expect(localStorage.getItem("octop:chat-sidebar:open")).toBe("true");
  });
  it("keeps appearance controls responsive when browser storage is unavailable", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    render(<PreferencesProbe />);
    await userEvent.click(screen.getByRole("button", { name: "standard" }));
    expect(screen.getByRole("button", { name: "custom" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "custom" }));
  });
});
