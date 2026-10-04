import { createContext, useContext, type ReactNode } from "react";
import { createPortal } from "react-dom";
export const MarketTopbarContext = createContext<{
  host: HTMLElement | null;
  active: string;
}>({ host: null, active: "" });
export default function MarketTopbarActions({
  tab,
  children,
}: {
  tab: string;
  children: ReactNode;
}) {
  const { host, active } = useContext(MarketTopbarContext);
  return host
    ? createPortal(
        <div className="wb-market-topbar-actions" hidden={active !== tab}>
          {children}
        </div>,
        host,
      )
    : null;
}
