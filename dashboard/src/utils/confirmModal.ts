import { Modal } from "antd";
import type { ModalFuncProps } from "antd";

const MOBILE_BREAKPOINT = 768;

function detectMobile(): boolean {
  return typeof window !== "undefined" && window.innerWidth < MOBILE_BREAKPOINT;
}

/** Mobile-friendly wrapper around antd `Modal.confirm` (stacked full-width buttons). */
export function showConfirmModal(
  props: ModalFuncProps,
  options?: { isMobile?: boolean },
): void {
  const isMobile = options?.isMobile ?? detectMobile();

  Modal.confirm({
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
