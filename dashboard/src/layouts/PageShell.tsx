import type { ReactNode } from "react";
import { Segmented, Typography } from "antd";
import AgentSelector from "../components/AgentSelector";
import { useIsMobile } from "../hooks/useIsMobile";
import {
  titleRowEndPadding,
  DESKTOP_DRAG_REGION_CLASS,
  DESKTOP_NO_DRAG_CLASS,
} from "../utils/desktopChrome";
import styles from "./PageShell.module.less";

const { Title, Text } = Typography;

/** One option for URL-synced path tabs (Workbench / Personalization). */
export interface PathTabOption {
  value: string;
  label: string;
  icon: ReactNode;
}

export interface PathTabsConfig {
  value: string;
  options: PathTabOption[];
  onChange: (value: string | number) => void;
}

interface PageShellProps {
  title: string;
  subtitle?: string;
  /** Right-aligned action buttons shown alongside the title. */
  actions?: React.ReactNode;
  /**
   * Path tabs shared by Workbench / Personalization:
   * desktop → title-row actions; mobile → full-width bar above content.
   */
  pathTabs?: PathTabsConfig;
  /** Render agent picker below the title row, outside the scrollable content card. */
  agentScoped?: boolean;
  /** When true, the content area does not scroll; children fill remaining height. */
  fill?: boolean;
  children: React.ReactNode;
}

function PathTabsSegmented({
  pathTabs,
  isMobile,
}: {
  pathTabs: PathTabsConfig;
  isMobile: boolean;
}) {
  return (
    <Segmented
      size={isMobile ? "small" : "middle"}
      value={pathTabs.value}
      block={isMobile}
      className={isMobile ? styles.pathTabsMobileSegmented : undefined}
      onChange={pathTabs.onChange}
      options={pathTabs.options.map((opt) => ({
        value: opt.value,
        label: isMobile ? (
          opt.label
        ) : (
          <span className={styles.pathTabLabel}>
            {opt.icon}
            {opt.label}
          </span>
        ),
      }))}
    />
  );
}

/**
 * Universal page wrapper for every non-fullscreen, non-Chat page.
 *
 * Visual contract (master spec §5 / sub-project ② spec §6.2):
 *  - Title row: 20px / 600 weight, fixed (does not scroll with content)
 *  - Subtitle: 13px / secondary colour, 4px below title
 *  - Optional agent bar (`agentScoped`): below title, outside content card
 *  - Gap between title row and content: 24px (12px + agent bar when scoped)
 *  - Content: colorBgContainer background, 24px padding, 8px radius
 *  - Only the content area scrolls internally
 *  - `actions` slot: right-aligned in the title row
 *  - `pathTabs`: desktop in title row; mobile full-width bar in content
 *
 * Tabbed helpers: `PageShell.FillTabs` (Ant Tabs) and `PageShell.Tabbed`
 * (custom tab bar) pin the tab chrome and scroll only the body on desktop.
 */
function PageShell({
  title,
  subtitle,
  actions,
  pathTabs,
  agentScoped,
  fill,
  children,
}: PageShellProps) {
  const isMobile = useIsMobile();
  const outerPad = isMobile ? 12 : 32;
  const outerPadTop = isMobile ? 12 : 24;
  const contentPad = isMobile ? 12 : 24;
  /** Fill layout, or mobile path-tabs that must stay pinned above the body. */
  const pinBody = Boolean(fill || (isMobile && pathTabs));

  const titleActions =
    !isMobile && pathTabs ? (
      <>
        <PathTabsSegmented pathTabs={pathTabs} isMobile={false} />
        {actions}
      </>
    ) : (
      actions
    );

  return (
    <div
      className={DESKTOP_DRAG_REGION_CLASS}
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        padding: `${outerPadTop}px ${outerPad}px ${outerPad}px`,
        boxSizing: "border-box",
        overflow: "hidden",
      }}
    >
      {/* Title row — fixed, never scrolls */}
      <div
        style={{
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          gap: 12,
          flexShrink: 0,
          marginBottom: agentScoped ? 12 : 24,
          paddingRight: titleRowEndPadding(outerPad),
        }}
      >
        <div>
          <Title
            level={4}
            style={{
              margin: 0,
              lineHeight: "28px",
              fontSize: 20,
              fontWeight: 600,
            }}
          >
            {title}
          </Title>
          {subtitle && (
            <Text
              type="secondary"
              style={{ fontSize: 13, marginTop: 4, display: "block" }}
            >
              {subtitle}
            </Text>
          )}
        </div>
        {titleActions && (
          <div style={{ flexShrink: 0, paddingTop: 2 }}>{titleActions}</div>
        )}
      </div>

      {agentScoped && (
        <div className={styles.agentBar}>
          <AgentSelector />
        </div>
      )}

      {/* Content — scrolls internally. Tighter side padding on mobile so
         tabbed pages get more usable horizontal space. Path tabs on mobile
         pin above the body (same chrome as Workbench / Personalization). */}
      <div
        className={DESKTOP_NO_DRAG_CLASS}
        style={{
          flex: 1,
          background: "var(--fn-bg-container, var(--fn-bg-elevated))",
          borderRadius: 8,
          padding: contentPad,
          // Mobile: never create a page-level horizontal scrollbar; wide
          // tables scroll via antd scroll.x inside their own wrapper.
          overflowX: pinBody || isMobile ? "hidden" : "auto",
          overflowY: pinBody ? "hidden" : "auto",
          minHeight: 0,
          minWidth: 0,
          display: pinBody ? "flex" : undefined,
          flexDirection: pinBody ? "column" : undefined,
        }}
      >
        {isMobile && pathTabs && (
          <div className={styles.pathTabsMobile}>
            <PathTabsSegmented pathTabs={pathTabs} isMobile />
          </div>
        )}
        {children}
      </div>
    </div>
  );
}

type TabbedShellProps = Omit<PageShellProps, "fill" | "children"> & {
  children: ReactNode;
};

/** Ant Design Tabs: pin nav, scroll only the active pane (desktop). */
function PageShellFillTabs({ children, ...shell }: TabbedShellProps) {
  const isMobile = useIsMobile();
  return (
    <PageShell {...shell} fill={!isMobile}>
      <div className={styles.fillTabs}>{children}</div>
    </PageShell>
  );
}

type PageShellTabbedProps = TabbedShellProps & {
  /** Custom tab bar rendered above the scrollable body. */
  tabBar: ReactNode;
};

/** Custom tab bar + scrollable body (desktop pins the bar). */
function PageShellTabbed({ tabBar, children, ...shell }: PageShellTabbedProps) {
  const isMobile = useIsMobile();
  return (
    <PageShell {...shell} fill={!isMobile}>
      <div className={styles.tabbed}>
        {tabBar}
        <div className={styles.tabbedBody}>{children}</div>
      </div>
    </PageShell>
  );
}

PageShell.FillTabs = PageShellFillTabs;
PageShell.Tabbed = PageShellTabbed;

export default PageShell;
export { styles as pageShellStyles };
export type { PageShellProps };
