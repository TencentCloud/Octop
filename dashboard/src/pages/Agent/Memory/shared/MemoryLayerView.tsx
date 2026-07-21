/**
 * MemoryLayerView — shared shell for memory-layer list pages.
 *
 * Extracts pagination, drawer container, loading/empty switches, and toolbar
 * layout so feature files only provide fetch logic, item rendering, and drawer content.
 * Keeps the antd Drawer pattern instead of an embedded detail column.
 */

import type { ReactNode } from "react";
import { Card, Drawer, Empty, Pagination, Skeleton, Space } from "antd";
import { useIsMobile } from "../../../../hooks/useIsMobile";

interface MemoryLayerViewProps<T> {
  /** Optional top toolbar for filters and controls. */
  toolbar?: ReactNode;

  /** List items. */
  items: T[];
  /** Total count for pagination. */
  total: number;
  /** Current page, 1-based. */
  page: number;
  /** Items per page. */
  pageSize: number;
  /** Page-change callback. */
  onPageChange: (p: number) => void;

  /** Loading state. */
  loading: boolean;

  /** Render one list item. */
  renderItem: (item: T) => ReactNode;
  /** Get the React key for a list item. */
  keyOf: (item: T) => string;

  /** Currently selected item driving drawer visibility; null/undefined closes it. */
  selected?: T | null;
  /** Close drawer callback. */
  onCloseDrawer?: () => void;
  /** Drawer title. */
  drawerTitle?: ReactNode;
  /** Drawer width. */
  drawerWidth?: number;
  /** Render drawer content. */
  renderDrawer?: (item: T) => ReactNode;

  /** List item click callback. */
  onItemClick?: (item: T) => void;

  /** Empty-state copy. */
  emptyText?: ReactNode;
  /**
   * Full replacement node for the empty state. Takes precedence over
   * ``emptyText``; use for guided empties (e.g. memory-pipeline hint).
   */
  emptyContent?: ReactNode;
}

export default function MemoryLayerView<T>(props: MemoryLayerViewProps<T>) {
  const {
    toolbar,
    items,
    total,
    page,
    pageSize,
    onPageChange,
    loading,
    renderItem,
    keyOf,
    selected,
    onCloseDrawer,
    drawerTitle,
    drawerWidth = 560,
    renderDrawer,
    onItemClick,
    emptyText,
    emptyContent,
  } = props;

  const isMobile = useIsMobile();
  const resolvedDrawerWidth = isMobile ? "100%" : drawerWidth;

  return (
    <Card size="small">
      {toolbar ? (
        <Space style={{ marginBottom: 12 }} wrap>
          {toolbar}
        </Space>
      ) : null}

      {loading && items.length === 0 ? (
        <Skeleton active />
      ) : items.length === 0 ? (
        (emptyContent ?? (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={emptyText ?? undefined}
          />
        ))
      ) : (
        <ul style={listStyle}>
          {items.map((it) => (
            <li
              key={keyOf(it)}
              onClick={onItemClick ? () => onItemClick(it) : undefined}
              style={{
                ...itemStyle,
                cursor: onItemClick ? "pointer" : "default",
              }}
            >
              {renderItem(it)}
            </li>
          ))}
        </ul>
      )}

      <div style={{ marginTop: 12, textAlign: "right" }}>
        <Pagination
          current={page}
          pageSize={pageSize}
          total={total}
          showSizeChanger={false}
          onChange={onPageChange}
        />
      </div>

      {renderDrawer ? (
        <Drawer
          title={drawerTitle}
          open={!!selected}
          onClose={onCloseDrawer}
          width={resolvedDrawerWidth}
        >
          {selected ? renderDrawer(selected) : null}
        </Drawer>
      ) : null}
    </Card>
  );
}

const listStyle: React.CSSProperties = {
  listStyle: "none",
  margin: 0,
  padding: 0,
};

const itemStyle: React.CSSProperties = {
  padding: "8px 0",
  borderBottom: "1px dashed #f0f0f0",
};
