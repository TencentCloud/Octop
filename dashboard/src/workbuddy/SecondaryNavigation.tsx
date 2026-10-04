import { resolveSelectedKey } from "../routes";
import { NavLink, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { navSectionLabel } from "../layouts/sidebarNav";
import {
  CONTROL_KEYS,
  MANAGEMENT_KEYS,
  filterNavigation,
  useWorkBuddyNavigation,
  workBuddyLabelKey,
} from "./navigationModel";

export default function SecondaryNavigation() {
  const { pathname } = useLocation();
  const { t } = useTranslation();
  const { catalog, sections } = useWorkBuddyNavigation();
  // Hidden/customized items stay out of menus, but a permitted deep link must still have context.
  const selectedKey = resolveSelectedKey(pathname);
  const active = catalog
    .flatMap((section) => section.items)
    .find(
      (item) =>
        item.key === selectedKey ||
        pathname === item.path ||
        pathname.startsWith(item.path + "/"),
    );
  const keys =
    active && MANAGEMENT_KEYS.has(active.key)
      ? MANAGEMENT_KEYS
      : active && CONTROL_KEYS.has(active.key)
      ? CONTROL_KEYS
      : null;
  if (!keys) return null;
  const groups = filterNavigation(sections, keys);
  const heading =
    keys === MANAGEMENT_KEYS
      ? t("workbuddy.systemManagement")
      : keys === CONTROL_KEYS
      ? t("nav.control")
      : t("nav.experts");
  return (
    <aside className="wb-secondary-navigation" aria-label={heading}>
      <h2>{heading}</h2>
      <nav>
        {groups.map((group, index) => (
          <div key={group.id ?? index}>
            {group.id && <p>{navSectionLabel(group, t)}</p>}
            {group.items.map((item) => (
              <NavLink
                key={item.key}
                to={item.path}
                className={({ isActive }) =>
                  `wb-secondary-navigation__item${
                    isActive || item.key === active?.key ? " active" : ""
                  }`
                }
              >
                {item.icon}
                <span>{t(workBuddyLabelKey(item.key, item.labelKey))}</span>
              </NavLink>
            ))}
          </div>
        ))}
      </nav>
    </aside>
  );
}
