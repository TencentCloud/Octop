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
  footerIcon: ReactNode;
  footerLabel: string;
  onFooterClick: () => void;
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
  footerIcon,
  footerLabel,
  onFooterClick,
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
    <div className={panelClass}>
      <div className={styles.search}>
        <input
          type="search"
          className={styles.searchInput}
          placeholder={searchPlaceholder}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <Search size={15} className={styles.searchIcon} aria-hidden />
      </div>

      <div className={styles.list}>
        {filtered.length === 0 ? (
          <div className={styles.empty}>{emptyMessage}</div>
        ) : (
          filtered.map((item) => renderItem(item))
        )}
      </div>

      {beforeFooter}

      <button type="button" className={styles.footer} onClick={onFooterClick}>
        {footerIcon}
        <span>{footerLabel}</span>
      </button>
    </div>
  );
}

export { styles as pickerStyles };
