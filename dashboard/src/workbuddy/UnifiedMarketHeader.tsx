import { useRef } from "react";
import marketIcons from "./generated/market-icons.json";
import { useTranslation } from "react-i18next";
import type { MarketTab } from "./marketModel";

export default function UnifiedMarketHeader({
  tabs,
  active,
  onSelect,
}: {
  tabs: readonly MarketTab[];
  active: string;
  onSelect: (tab: MarketTab) => void;
}) {
  const { t } = useTranslation();
  const buttons = useRef<Array<HTMLButtonElement | null>>([]);
  return (
    <div className="um-header__inner">
      <div
        className="um-header__tabs"
        role="tablist"
        aria-label={t("workbuddy.market.title")}
      >
        {tabs.map((tab, index) => {
          const icon = marketIcons[tab.id];
          return (
            <button
              key={tab.id}
              ref={(node) => {
                buttons.current[index] = node;
              }}
              id={`um-tab-${tab.id}`}
              type="button"
              role="tab"
              aria-controls={`um-panel-${tab.id}`}
              aria-selected={active === tab.id}
              tabIndex={active === tab.id ? 0 : -1}
              className={`um-tab${active === tab.id ? " um-tab--active" : ""}`}
              onClick={() => onSelect(tab)}
              onKeyDown={(event) => {
                const offset =
                  event.key === "ArrowRight"
                    ? 1
                    : event.key === "ArrowLeft"
                    ? -1
                    : 0;
                const target =
                  event.key === "Home"
                    ? 0
                    : event.key === "End"
                    ? tabs.length - 1
                    : offset
                    ? (index + offset + tabs.length) % tabs.length
                    : -1;
                if (target < 0) return;
                event.preventDefault();
                buttons.current[target]?.focus();
                onSelect(tabs[target]);
              }}
            >
              <svg
                width={14}
                height={14}
                viewBox={icon.viewBox}
                aria-hidden="true"
              >
                <path {...icon.path} fillRule={"evenodd"} />
              </svg>
              {t(tab.label)}
            </button>
          );
        })}
      </div>
    </div>
  );
}
