import { useCallback, useState } from "react";

function loadCollapsed(storageKey: string): boolean {
  try {
    return localStorage.getItem(storageKey) === "1";
  } catch {
    return false;
  }
}

function saveCollapsed(storageKey: string, collapsed: boolean) {
  try {
    localStorage.setItem(storageKey, collapsed ? "1" : "0");
  } catch {
    /* ignore */
  }
}

export function useListPanelCollapsed(storageKey: string) {
  const [collapsed, setCollapsed] = useState(() => loadCollapsed(storageKey));

  const toggle = useCallback(() => {
    setCollapsed((prev) => {
      const next = !prev;
      saveCollapsed(storageKey, next);
      return next;
    });
  }, [storageKey]);

  return { collapsed, toggle, setCollapsed };
}
