import { useMemo } from "react";
import { useImeSearchInput } from "./useImeSearchInput";

export function useFilteredList<T>(
  items: T[],
  filterFn: (item: T, query: string) => boolean,
) {
  const {
    value: query,
    committed,
    setValue: setQuery,
    inputProps,
  } = useImeSearchInput();

  const filtered = useMemo(() => {
    const q = committed.trim().toLowerCase();
    if (!q) return items;
    return items.filter((item) => filterFn(item, q));
  }, [items, committed, filterFn]);

  return { query, committed, setQuery, inputProps, filtered };
}
