import type { ModalFuncProps } from "antd";
import { modal } from "./antdModal";

const MOBILE_BREAKPOINT = 768;

function detectMobile(): boolean {
  return typeof window !== "undefined" && window.innerWidth < MOBILE_BREAKPOINT;
}

/** Mobile-friendly wrapper around themed `modal.confirm` (stacked full-width buttons). */
export function showConfirmModal(
  props: ModalFuncProps,
  options?: { isMobile?: boolean },
): void {
  const isMobile = options?.isMobile ?? detectMobile();

  modal.confirm({
    centered: true,
    ...(isMobile
      ? {
          width: Math.min(400, Math.max(280, window.innerWidth - 32)),
          rootClassName: "octop-confirm-modal--mobile",
        }
      : {}),
    ...props,
  });
}
