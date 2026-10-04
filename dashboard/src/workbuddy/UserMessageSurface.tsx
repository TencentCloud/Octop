import type { HTMLAttributes } from "react";
import { sourceUserBubbleClass } from "./messageStyles";

export default function UserMessageSurface({
  className = "",
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      {...props}
      className={`${sourceUserBubbleClass} wb-user-message-text ${className}`}
    />
  );
}
