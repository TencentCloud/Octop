import type { ReactNode } from "react";
import { Search } from "lucide-react";
import { useFilteredList } from "../../hooks/useFilteredList";
import styles from "./picker.module.less";

export type PickerPanelWidth = "wide" | "narrow" | "compact";

interface SearchablePickerPanelProps<T> {
  items: T[];
  filterFn: (item: T, query: string) => boolean;
  searchPlaceholder: string;
  emptyMessage: string;
  width?: PickerPanelWidth;
  renderItem: (item: T) => ReactNode;
  /** Optional grouping: consecutive items with the same key get a header. */
  getGroupKey?: (item: T) => string;
  renderGroupHeader?: (key: string, firstItem: T) => ReactNode;
  footerIcon: ReactNode;
  footerLabel: string;
  onFooterClick: () => void;
  /** Soften the footer (e.g. remote-bridge “edit on peer” hint). */
  footerMuted?: boolean;
  /** Optional row(s) rendered between the list and the primary footer. */
  beforeFooter?: ReactNode;
}

export default function SearchablePickerPanel<T>({
  items,
  filterFn,
  searchPlaceholder,
  emptyMessage,
  width = "wide",
  renderItem,
  getGroupKey,
  renderGroupHeader,
  footerIcon,
  footerLabel,
  onFooterClick,
  footerMuted = false,
  beforeFooter,
}: SearchablePickerPanelProps<T>) {
  const { query, setQuery, filtered } = useFilteredList(items, filterFn);
  const panelClass =
    width === "compact"
      ? styles.panelCompact
      : width === "narrow"
      ? styles.panelNarrow
      : styles.panelWide;

  return (
    <div className={panelClass} data-picker-panel="">
      <div className={styles.search} data-picker-search="">
        <input
          type="search"
          className={styles.searchInput}
          placeholder={searchPlaceholder}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <Search size={15} className={styles.searchIcon} aria-hidden />
      </div>

      <div className={styles.list} data-picker-list="">
        {filtered.length === 0 ? (
          <div className={styles.empty}>{emptyMessage}</div>
        ) : (
          filtered.map((item, index) => {
            const groupKey = getGroupKey?.(item) ?? "";
            const prevKey =
              index > 0 ? getGroupKey?.(filtered[index - 1]) ?? "" : null;
            const showHeader =
              Boolean(getGroupKey && renderGroupHeader) && groupKey !== prevKey;
            return (
              <div key={index}>
                {showHeader ? renderGroupHeader?.(groupKey, item) : null}
                {renderItem(item)}
              </div>
            );
          })
        )}
      </div>

      {beforeFooter}

      <button
        type="button"
        className={`${styles.footer} ${footerMuted ? styles.footerMuted : ""}`}
        data-picker-footer=""
        onClick={onFooterClick}
      >
        {footerIcon}
        <span>{footerLabel}</span>
      </button>
    </div>
  );
}

export { styles as pickerStyles };
