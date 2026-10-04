import type { HTMLAttributes } from "react";

/** Layout-only root; state and navigation remain owned by Octop MainLayout. */
export default function ShellFrame({
  className = "",
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return <div {...props} className={`wb-app-shell ${className}`} />;
}
