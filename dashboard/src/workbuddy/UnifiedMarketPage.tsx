import { MarketTopbarContext } from "./MarketTopbarActions";
import { MarketDetailContext } from "./MarketDetailContext";
import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { Route, Routes, useNavigate, type Location } from "react-router-dom";
import { useWorkBuddyNavigation } from "./navigationModel";
import { marketTabForPath, visibleMarketTabs } from "./marketModel";
import { EmbeddedPageContext } from "../layouts/PageShell";
import PageLoading from "../components/PageLoading";
import ForbiddenPage from "../components/ForbiddenPage";
import UnifiedMarketHeader from "./UnifiedMarketHeader";
import WorkBuddyTopbar from "./Topbar";
import RetainedSurface from "./RetainedSurface";
const Experts = lazy(() => import("../pages/Experts"));
const Skills = lazy(() => import("../pages/Agent/Skills"));
const Connectors = lazy(() => import("../pages/Agent/Connectors"));
const pages = { experts: Experts, skills: Skills, connectors: Connectors };
export default function UnifiedMarketPage({
  location,
}: {
  location: Location;
}) {
  const navigate = useNavigate();
  const [actionHost, setActionHost] = useState<HTMLDivElement | null>(null);
  const { catalog, sections } = useWorkBuddyNavigation();
  const active = marketTabForPath(location.pathname);
  const snapshots = useRef<Record<string, Location>>({});
  if (active) snapshots.current[active.id] = location;
  const [visited, setVisited] = useState<string[]>(active ? [active.id] : []);
  useEffect(() => {
    if (active)
      setVisited((prev) =>
        prev.includes(active.id) ? prev : [...prev, active.id],
      );
  }, [active]);
  const allowed = visibleMarketTabs(catalog);
  const visible = visibleMarketTabs(sections);
  const tabs =
    active &&
    allowed.some((tab) => tab.id === active.id) &&
    !visible.some((tab) => tab.id === active.id)
      ? [...visible, active]
      : visible;
  return (
    <section className="wb-unified-market" hidden={!active}>
      <WorkBuddyTopbar
        actions={<div ref={setActionHost} />}
        title={
          <UnifiedMarketHeader
            tabs={tabs}
            active={active?.id ?? "experts"}
            onSelect={(tab) => navigate(snapshots.current[tab.id] ?? tab.path)}
          />
        }
      />
      <MarketTopbarContext.Provider
        value={{ host: actionHost, active: active?.id ?? "" }}
      >
        <EmbeddedPageContext.Provider value={true}>
          <MarketDetailContext.Provider value={true}>
            {visited.map((id) => {
              const entry = allowed.find((tab) => tab.id === id);
              if (!entry)
                return active?.id === id ? <ForbiddenPage key={id} /> : null;
              const Page = pages[entry.id];
              return (
                <div
                  key={id}
                  id={`um-panel-${id}`}
                  role="tabpanel"
                  aria-labelledby={`um-tab-${id}`}
                  hidden={active?.id !== id}
                  className="wb-market-pane"
                >
                  <RetainedSurface active={active?.id === id}>
                    <Routes location={snapshots.current[id]}>
                      <Route
                        path={`${entry.path}/*`}
                        element={
                          <Suspense fallback={<PageLoading />}>
                            <Page />
                          </Suspense>
                        }
                      />
                    </Routes>
                  </RetainedSurface>
                </div>
              );
            })}
          </MarketDetailContext.Provider>
        </EmbeddedPageContext.Provider>
      </MarketTopbarContext.Provider>
    </section>
  );
}
