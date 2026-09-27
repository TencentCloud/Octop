import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import type { SlashMenuGroup } from "../../../utils/slashCategories";

export type SlashPickerRow = {
  command: string;
  label: string;
  icon: LucideIcon;
  tone: string;
};

type SlashCommandMenuProps<T extends SlashPickerRow> = {
  groups: SlashMenuGroup<T>[] | null;
  flatItems: T[];
  activeIndex: number;
  disabled?: boolean;
  variant: "inline" | "popover";
  itemsGridClassName: string;
  itemClassName: string;
  activeClassName: string;
  categoryClassName: string;
  labelClassName: string;
  nameClassName?: string;
  cmdClassName: string;
  iconWrapClassName?: (tone: string) => string;
  onSelect: (command: string) => void;
  onHover: (index: number) => void;
  footer?: ReactNode;
};

const INLINE_ICON = 14;
const POPOVER_ICON = 14;

export default function SlashCommandMenu<T extends SlashPickerRow>({
  groups,
  flatItems,
  activeIndex,
  disabled,
  variant,
  itemsGridClassName,
  itemClassName,
  activeClassName,
  categoryClassName,
  labelClassName,
  nameClassName,
  cmdClassName,
  iconWrapClassName,
  onSelect,
  onHover,
  footer,
}: SlashCommandMenuProps<T>) {
  let index = 0;

  const renderRow = (item: T) => {
    const idx = index;
    index += 1;
    const Icon = item.icon;
    const active = idx === activeIndex;
    const iconSize = variant === "popover" ? POPOVER_ICON : INLINE_ICON;

    if (variant === "popover") {
      const toneClass = iconWrapClassName?.(item.tone) ?? "";
      return (
        <button
          key={`${item.command}-${idx}`}
          className={itemClassName}
          onClick={() => onSelect(item.command)}
          onMouseEnter={() => onHover(idx)}
          disabled={disabled}
          type="button"
          role="option"
          aria-selected={active}
        >
          <span className={toneClass}>
            <Icon size={iconSize} />
          </span>
          <span className={labelClassName}>
            <span className={nameClassName}>{item.label}</span>
            <span className={cmdClassName}>{item.command}</span>
          </span>
        </button>
      );
    }

    return (
      <button
        key={`${item.command}-${idx}`}
        className={`${itemClassName} ${active ? activeClassName : ""}`}
        onMouseDown={(e) => {
          e.preventDefault();
          onSelect(item.command);
        }}
        onMouseEnter={() => onHover(idx)}
        disabled={disabled}
        type="button"
        role="option"
        aria-selected={active}
        title={`${item.label} ${item.command}`}
      >
        <span className={labelClassName}>
          <Icon size={iconSize} />
          <span>{item.label}</span>
        </span>
        <span className={cmdClassName}>{item.command}</span>
      </button>
    );
  };

  const renderGrid = (items: T[]) => (
    <div
      id="octop-chat-pick-menu"
      className={itemsGridClassName}
      role="listbox"
    >
      {items.map((item) => renderRow(item))}
    </div>
  );

  return (
    <>
      {groups
        ? groups.map((group) => (
            <div key={group.category}>
              <div className={categoryClassName}>{group.label}</div>
              {renderGrid(group.items)}
            </div>
          ))
        : renderGrid(flatItems)}
      {footer}
    </>
  );
}
