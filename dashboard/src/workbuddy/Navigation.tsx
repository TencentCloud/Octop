import { marketTabForPath, visibleMarketTabs } from "./marketModel";
import {
  Home,
  FolderKanban,
  Boxes,
  Sparkles,
  Timer,
  MoreHorizontal,
  Bot,
  Files,
  ChevronRight,
} from "lucide-react";
import { useState } from "react";
import { useIsMobile } from "../hooks/useIsMobile";
import { Dropdown } from "antd";
import { NavLink, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import type { NavSection } from "../layouts/sidebarNav";

import { workBuddyLabelKey } from "./navigationModel";

export default function WorkBuddyNavigation({
  compact,
  onNavigate,
  sections = [],
  onOpenFiles,
  filesAvailable = true,
}: {
  compact: boolean;
  onNavigate: (path: string) => void;
  sections?: NavSection[];
  onOpenFiles?: () => void;
  filesAvailable?: boolean;
}) {
  const { t } = useTranslation();
  const isMobile = useIsMobile();
  const [marketMenuOpen, setMarketMenuOpen] = useState(false);
  const { pathname } = useLocation();
  const items = sections.flatMap((section) => section.items);
  const renderLink = (
    path: string,
    label: string,
    Icon: typeof Home,
    deferred = false,
  ) => (
    <NavLink
      key={path}
      to={path}
      end={path === "/home"}
      onClick={(event) => {
        event.preventDefault();
        onNavigate(path);
      }}
      title={compact ? label : undefined}
      className={({ isActive }) =>
        `conversation-list-tab-button conversation-list-tab-button-box wb-navigation__item${
          isActive ? " active wb-navigation__item--active" : ""
        }`
      }
    >
      <Icon size={16} aria-hidden="true" />
      {!compact && (
        <>
          <span className="conversation-list-tab-button-label">{label}</span>
          {deferred && <small>{t("workbuddy.notConnected")}</small>}
        </>
      )}
    </NavLink>
  );
  const market = visibleMarketTabs(sections);
  const controls = items.filter((item) =>
    ["workbench", "remote-desktop"].includes(item.key),
  );
  const consoleEntry =
    controls.find((item) => item.key === "workbench") ?? controls[0];
  const more = [
    ...items.filter((item) => item.key === "knowledge-bases"),
    ...(consoleEntry ? [{ ...consoleEntry, key: "workbench" }] : []),
  ];
  const menu = (group: typeof items) => ({
    items: group.map((item) => ({
      key: item.path,
      label: t(workBuddyLabelKey(item.key, item.labelKey)),
      icon: item.icon,
      onClick: () => onNavigate(item.path),
    })),
  });
  return (
    <nav
      className="conversation-list-tabs wb-navigation"
      aria-label={t("workbuddy.workspace")}
    >
      {renderLink("/home", t("workbuddy.newTask"), Home)}
      {renderLink("/chat", t("workbuddy.assistants"), Bot)}
      {renderLink("/projects", t("workbuddy.projects"), FolderKanban, true)}
      <Dropdown
        menu={{
          items: market.map((tab) => ({
            key: tab.id,
            label: t(tab.label),
            onClick: () => {
              setMarketMenuOpen(false);
              onNavigate(tab.path);
            },
          })),
        }}
        trigger={isMobile ? ["click"] : ["hover"]}
        open={marketMenuOpen}
        onOpenChange={setMarketMenuOpen}
        placement="topRight"
      >
        <button
          type="button"
          aria-label={t("workbuddy.market.title")}
          aria-haspopup="menu"
          aria-expanded={marketMenuOpen}
          title={compact ? t("workbuddy.market.title") : undefined}
          className={`conversation-list-tab-button wb-navigation__item${
            marketTabForPath(pathname) ? " active" : ""
          }`}
          onKeyDown={(event) => {
            if (event.key === "ArrowDown") {
              event.preventDefault();
              setMarketMenuOpen(true);
            }
          }}
          onClick={() => {
            if (isMobile) return;
            setMarketMenuOpen(false);
            if (market[0])
              onNavigate(
                market.find((tab) => tab.id === "experts")?.path ??
                  market[0].path,
              );
          }}
        >
          <Sparkles size={16} aria-hidden="true" />
          {!compact && (
            <span className="conversation-list-tab-button-label">
              {t("workbuddy.market.title")}
            </span>
          )}
        </button>
      </Dropdown>
      {renderLink("/tasks", t("nav.tasks"), Timer)}
      {renderLink("/space", t("workbuddy.space"), Boxes, true)}
      <Dropdown
        menu={{
          items: [
            ...(onOpenFiles
              ? [
                  {
                    key: "workspace-files",
                    label: t("workbuddy.files"),
                    icon: <Files size={16} />,
                    disabled: !filesAvailable,
                    onClick: onOpenFiles,
                  },
                ]
              : []),
            ...menu(more).items,
          ],
        }}
        trigger={["click"]}
        placement="bottomRight"
      >
        <button
          type="button"
          title={compact ? t("workbuddy.moreCapabilities") : undefined}
          className={`conversation-list-tab-button wb-navigation__item${
            [...more, ...controls].some((item) =>
              pathname.startsWith(item.path),
            )
              ? " active"
              : ""
          }`}
        >
          <MoreHorizontal size={16} aria-hidden="true" />
          {!compact && (
            <>
              <span>{t("workbuddy.moreCapabilities")}</span>
              <ChevronRight size={12} />
            </>
          )}
        </button>
      </Dropdown>
    </nav>
  );
}
