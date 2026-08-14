import { describe, expect, it, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useListPanelCollapsed } from "./useListPanelCollapsed";

describe("useListPanelCollapsed", () => {
  const key = "octop:test-list-collapsed";

  beforeEach(() => {
    localStorage.removeItem(key);
  });

  it("defaults to expanded when no storage entry", () => {
    const { result } = renderHook(() => useListPanelCollapsed(key));
    expect(result.current.collapsed).toBe(false);
  });

  it("defaults to collapsed when defaultCollapsed is true", () => {
    const { result } = renderHook(() =>
      useListPanelCollapsed(key, { defaultCollapsed: true }),
    );
    expect(result.current.collapsed).toBe(true);
  });

  it("persists toggle state", () => {
    const { result } = renderHook(() => useListPanelCollapsed(key));
    act(() => result.current.toggle());
    expect(result.current.collapsed).toBe(true);
    expect(localStorage.getItem(key)).toBe("1");
    act(() => result.current.toggle());
    expect(result.current.collapsed).toBe(false);
    expect(localStorage.getItem(key)).toBe("0");
  });
});
