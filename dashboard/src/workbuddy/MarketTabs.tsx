import { useEffect, useId, useState, type ReactNode } from "react";

interface MarketTab {
  key: string;
  label: ReactNode;
  children: ReactNode;
}

/** Source expert-centre tabs; visited panes retain their local drafts and filters. */
export default function MarketTabs({
  activeKey,
  onChange,
  items,
  variant = "heading",
}: {
  activeKey: string;
  onChange: (key: string) => void;
  items: MarketTab[];
  variant?: "heading" | "filters";
}) {
  const id = useId();
  const [visited, setVisited] = useState(() => new Set([activeKey]));
  useEffect(() => {
    setVisited((previous) =>
      previous.has(activeKey) ? previous : new Set([...previous, activeKey]),
    );
  }, [activeKey]);
  const select = (key: string) => {
    setVisited((previous) => new Set([...previous, key]));
    onChange(key);
  };
  return (
    <div className="wb-market-tabs">
      <header className="ec-header">
        <div
          className={
            variant === "filters" ? "ec-category-tabs" : "ec-title-tabs"
          }
          role="tablist"
        >
          {items.map((item, index) => (
            <button
              type="button"
              role="tab"
              key={item.key}
              id={`${id}-tab-${item.key}`}
              aria-controls={`${id}-panel-${item.key}`}
              aria-selected={item.key === activeKey}
              tabIndex={item.key === activeKey ? 0 : -1}
              className={
                variant === "filters"
                  ? `ec-category-tab${
                      item.key === activeKey ? " is-active" : ""
                    }`
                  : `ec-title${
                      item.key === activeKey ? " ec-title-active" : ""
                    }`
              }
              onClick={() => select(item.key)}
              onKeyDown={(event) => {
                const next =
                  event.key === "ArrowRight"
                    ? (index + 1) % items.length
                    : event.key === "ArrowLeft"
                    ? (index + items.length - 1) % items.length
                    : event.key === "Home"
                    ? 0
                    : event.key === "End"
                    ? items.length - 1
                    : null;
                if (next === null) return;
                event.preventDefault();
                select(items[next].key);
                document
                  .getElementById(`${id}-tab-${items[next].key}`)
                  ?.focus();
              }}
            >
              {item.label}
            </button>
          ))}
        </div>
      </header>
      <div className="wb-market-tabs__body">
        {items.map((item) =>
          visited.has(item.key) || item.key === activeKey ? (
            <section
              role="tabpanel"
              key={item.key}
              id={`${id}-panel-${item.key}`}
              aria-labelledby={`${id}-tab-${item.key}`}
              hidden={item.key !== activeKey}
              tabIndex={0}
            >
              {item.children}
            </section>
          ) : null,
        )}
      </div>
    </div>
  );
}
