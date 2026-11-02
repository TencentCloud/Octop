import { createContext, useContext, type ReactNode } from "react";

const RailSeamContext = createContext(false);

export function RailSeamProvider({
  split,
  children,
}: {
  split: boolean;
  children: ReactNode;
}) {
  return (
    <RailSeamContext.Provider value={split}>
      {children}
    </RailSeamContext.Provider>
  );
}

/**
 * Nav is open and the history rail is folded, so the split handle on the nav
 * edge owns both actions and the history rail must not paint a second pill.
 */
export function useSplitHistorySeam(): boolean {
  return useContext(RailSeamContext);
}
