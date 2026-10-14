import type { ComponentProps } from "react";
import type { TFunction } from "i18next";
import type { MenuProps } from "antd";
import { ArrowDown, ArrowUp, Pin, PinOff } from "lucide-react";

/** Ordering controls shared by classic + minimal sidebar agent rows. */
export interface AgentOrdering {
  /** Whether this agent is currently pinned. */
  pinned: boolean;
  /** False while search / hidden-expert views disable ordering. */
  enabled: boolean;
  rowProps?: { "data-drag-item": string };
  handleProps?: ComponentProps<"span">;
  /** Extra row classes for dragging / drop-indicator feedback. */
  rowClassName?: string;
  onTogglePin: () => void;
  onMoveUp: () => void;
  onMoveDown: () => void;
}

/** ⋯ menu: pin/unpin + move up/down (the drag-free fallback path). */
export function agentOrderMenuItems(
  t: TFunction,
  ordering: AgentOrdering,
): MenuProps["items"] {
  return [
    {
      key: "pin",
      label: ordering.pinned ? t("chat.unpin") : t("chat.pin"),
      icon: ordering.pinned ? <PinOff size={14} /> : <Pin size={14} />,
      disabled: !ordering.enabled,
      onClick: ({ domEvent }) => {
        domEvent.stopPropagation();
        ordering.onTogglePin();
      },
    },
    {
      key: "moveUp",
      label: t("chat.moveUp"),
      icon: <ArrowUp size={14} />,
      disabled: !ordering.enabled,
      onClick: ({ domEvent }) => {
        domEvent.stopPropagation();
        ordering.onMoveUp();
      },
    },
    {
      key: "moveDown",
      label: t("chat.moveDown"),
      icon: <ArrowDown size={14} />,
      disabled: !ordering.enabled,
      onClick: ({ domEvent }) => {
        domEvent.stopPropagation();
        ordering.onMoveDown();
      },
    },
  ];
}
