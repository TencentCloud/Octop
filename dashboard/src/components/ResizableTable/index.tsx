import { useCallback, useMemo, useRef, useState } from "react";
import type {
  HTMLAttributes,
  MouseEvent as ReactMouseEvent,
  TdHTMLAttributes,
  ThHTMLAttributes,
} from "react";
import { Table } from "antd";
import type { TableProps } from "antd";
import type { ColumnsType, ColumnType, ColumnGroupType } from "antd/es/table";
import styles from "./ResizableTable.module.css";

const DEFAULT_MIN_WIDTH = 48;

interface ResizableHeaderCellProps
  extends ThHTMLAttributes<HTMLTableCellElement> {
  onResize?: (width: number) => void;
  width?: number;
  // antd injects the column config and index into the header cell; they are
  // not valid DOM attributes, so we drop them before spreading onto <th>.
  column?: unknown;
  colIndex?: number;
}

function ResizableTitle({
  onResize,
  width,
  column: _column,
  colIndex: _colIndex,
  className,
  children,
  ...restProps
}: ResizableHeaderCellProps) {
  const startX = useRef(0);
  const startWidth = useRef(0);

  const handleMouseDown = useCallback(
    (event: ReactMouseEvent<HTMLSpanElement>) => {
      event.stopPropagation();
      event.preventDefault();
      startX.current = event.clientX;
      const headerCell = event.currentTarget.parentElement;
      startWidth.current =
        typeof width === "number" ? width : headerCell?.offsetWidth ?? 0;

      const handleMouseMove = (moveEvent: MouseEvent) => {
        const delta = moveEvent.clientX - startX.current;
        onResize?.(Math.max(startWidth.current + delta, DEFAULT_MIN_WIDTH));
      };
      const handleMouseUp = () => {
        document.removeEventListener("mousemove", handleMouseMove);
        document.removeEventListener("mouseup", handleMouseUp);
        document.body.style.cursor = "";
        document.body.style.userSelect = "";
      };

      document.addEventListener("mousemove", handleMouseMove);
      document.addEventListener("mouseup", handleMouseUp);
      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";
    },
    [onResize, width],
  );

  const cellClassName = [styles.cell, className]
    .filter(Boolean)
    .join(" ")
    .trim();

  return (
    <th {...restProps} className={cellClassName}>
      {children}
      {onResize != null ? (
        <span
          className={styles.handle}
          onMouseDown={handleMouseDown}
          onClick={(event) => event.stopPropagation()}
        />
      ) : null}
    </th>
  );
}

type AnyColumn<T> = ColumnType<T> | ColumnGroupType<T>;

function columnKey<T>(col: AnyColumn<T>, index: number): string {
  const key = (col as ColumnType<T>).key;
  if (key != null) {
    return String(key);
  }
  const dataIndex = (col as ColumnType<T>).dataIndex;
  if (dataIndex != null) {
    return String(dataIndex);
  }
  return `__col_${index}`;
}

function columnWidth<T>(col: AnyColumn<T>): string | number | undefined {
  return (col as ColumnType<T>).width;
}

interface UseResizableColumnsOptions {
  storageKey?: string;
  minWidth?: number;
}

export function useResizableColumns<T extends object>(
  columns: ColumnsType<T>,
  options: UseResizableColumnsOptions = {},
): { components: TableProps<T>["components"]; mergedColumns: ColumnsType<T> } {
  const { storageKey, minWidth = DEFAULT_MIN_WIDTH } = options;

  const [widths, setWidths] = useState<Record<string, number>>(() => {
    if (!storageKey) {
      return {};
    }
    try {
      const raw = window.localStorage.getItem(storageKey);
      return raw ? (JSON.parse(raw) as Record<string, number>) : {};
    } catch {
      return {};
    }
  });

  const persist = useCallback(
    (next: Record<string, number>) => {
      if (!storageKey) {
        return;
      }
      try {
        window.localStorage.setItem(storageKey, JSON.stringify(next));
      } catch {
        // Storage may be unavailable (private mode / quota); resizing stays
        // effective for the current session regardless.
      }
    },
    [storageKey],
  );

  const handleResize = useCallback(
    (key: string) => (nextWidth: number) => {
      setWidths((prev) => {
        const updated = { ...prev, [key]: Math.max(nextWidth, minWidth) };
        persist(updated);
        return updated;
      });
    },
    [minWidth, persist],
  );

  const mergedColumns = useMemo<ColumnsType<T>>(
    () =>
      columns.map((col, index) => {
        // Group headers (with children) cannot be resized as a single column.
        if ("children" in (col as ColumnGroupType<T>)) {
          return col;
        }
        const key = columnKey(col, index);
        const defaultWidth = columnWidth(col);
        const currentWidth = key in widths ? widths[key] : defaultWidth;
        return {
          ...col,
          ...(currentWidth != null ? { width: currentWidth } : {}),
          onHeaderCell: () =>
            ({
              width: (currentWidth ?? null) as string | number | null,
              onResize: handleResize(key),
            }) as unknown as HTMLAttributes<HTMLElement> &
              TdHTMLAttributes<HTMLElement>,
        };
      }),
    [columns, widths, handleResize],
  );

  const components = useMemo<TableProps<T>["components"]>(
    () => ({
      header: {
        cell: ResizableTitle,
      },
    }),
    [],
  );

  return { components, mergedColumns };
}

interface ResizableTableProps<T> extends TableProps<T> {
  storageKey?: string;
  minWidth?: number;
}

export function ResizableTable<T extends object>({
  columns,
  components,
  storageKey,
  minWidth,
  ...rest
}: ResizableTableProps<T>) {
  const { components: resizeComponents, mergedColumns } = useResizableColumns(
    columns as ColumnsType<T>,
    { storageKey, minWidth },
  );
  return (
    <Table
      columns={mergedColumns}
      components={{ ...resizeComponents, ...components }}
      {...rest}
    />
  );
}
