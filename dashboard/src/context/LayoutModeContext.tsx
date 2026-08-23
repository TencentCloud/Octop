import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  loadLayoutMode,
  loadMinimalNavPane,
  saveLayoutMode,
  saveMinimalNavPane,
  type LayoutMode,
  type MinimalNavPane,
} from "../layouts/layoutModeStorage";

interface LayoutModeContextValue {
  layoutMode: LayoutMode;
  setLayoutMode: (mode: LayoutMode) => void;
  /** Lower pane in minimal layout (settings vs records). Ignored in classic. */
  minimalPane: MinimalNavPane;
  setMinimalPane: (pane: MinimalNavPane) => void;
}

const LayoutModeContext = createContext<LayoutModeContextValue>({
  layoutMode: "classic",
  setLayoutMode: () => {},
  minimalPane: "settings",
  setMinimalPane: () => {},
});

export function LayoutModeProvider({ children }: { children: ReactNode }) {
  const [layoutMode, setLayoutModeState] = useState<LayoutMode>(() =>
    loadLayoutMode(),
  );
  const [minimalPane, setMinimalPaneState] = useState<MinimalNavPane>(() =>
    loadMinimalNavPane(),
  );

  const setLayoutMode = useCallback((mode: LayoutMode) => {
    setLayoutModeState(mode);
    saveLayoutMode(mode);
  }, []);

  const setMinimalPane = useCallback((pane: MinimalNavPane) => {
    setMinimalPaneState(pane);
    saveMinimalNavPane(pane);
  }, []);

  const value = useMemo(
    () => ({ layoutMode, setLayoutMode, minimalPane, setMinimalPane }),
    [layoutMode, setLayoutMode, minimalPane, setMinimalPane],
  );

  return (
    <LayoutModeContext.Provider value={value}>
      {children}
    </LayoutModeContext.Provider>
  );
}

export function useLayoutMode(): LayoutModeContextValue {
  return useContext(LayoutModeContext);
}
