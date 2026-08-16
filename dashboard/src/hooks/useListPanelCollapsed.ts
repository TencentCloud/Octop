import { useCallback, useState } from "react";

function loadCollapsed(storageKey: string, defaultCollapsed: boolean): boolean {
  try {
    const stored = localStorage.getItem(storageKey);
    if (stored === null) return defaultCollapsed;
    return stored === "1";
  } catch {
    return defaultCollapsed;
  }
}

function saveCollapsed(storageKey: string, collapsed: boolean) {
  try {
    localStorage.setItem(storageKey, collapsed ? "1" : "0");
  } catch {
    /* ignore */
  }
}

export function useListPanelCollapsed(
  storageKey: string,
  options?: { defaultCollapsed?: boolean },
) {
  const defaultCollapsed = options?.defaultCollapsed ?? false;
  const [collapsed, setCollapsed] = useState(() =>
    loadCollapsed(storageKey, defaultCollapsed),
  );

  const toggle = useCallback(() => {
    setCollapsed((prev) => {
      const next = !prev;
      saveCollapsed(storageKey, next);
      return next;
    });
  }, [storageKey]);

  return { collapsed, toggle, setCollapsed };
}
