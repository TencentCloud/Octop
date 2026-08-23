import { afterEach, describe, expect, it } from "vitest";
import {
  LAYOUT_MODE_KEY,
  MINIMAL_NAV_PANE_KEY,
  loadLayoutMode,
  loadMinimalNavPane,
  saveLayoutMode,
  saveMinimalNavPane,
} from "../../src/layouts/layoutModeStorage";

describe("layoutModeStorage", () => {
  afterEach(() => {
    localStorage.removeItem(LAYOUT_MODE_KEY);
    localStorage.removeItem(MINIMAL_NAV_PANE_KEY);
  });

  it("defaults to classic layout and records pane", () => {
    expect(loadLayoutMode()).toBe("classic");
    expect(loadMinimalNavPane()).toBe("records");
  });

  it("persists layout mode and minimal pane", () => {
    saveLayoutMode("minimal");
    saveMinimalNavPane("settings");
    expect(loadLayoutMode()).toBe("minimal");
    expect(loadMinimalNavPane()).toBe("settings");
  });

  it("migrates briefly-shipped chat/nav aliases", () => {
    localStorage.setItem(MINIMAL_NAV_PANE_KEY, "chat");
    expect(loadMinimalNavPane()).toBe("records");
    localStorage.setItem(MINIMAL_NAV_PANE_KEY, "nav");
    expect(loadMinimalNavPane()).toBe("settings");
  });

  it("ignores invalid stored values", () => {
    localStorage.setItem(LAYOUT_MODE_KEY, "weird");
    localStorage.setItem(MINIMAL_NAV_PANE_KEY, "other");
    expect(loadLayoutMode()).toBe("classic");
    expect(loadMinimalNavPane()).toBe("records");
  });
});
