import { ConfigProvider } from "antd";
import { useCallback, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

/** Retained pages keep drafts, but their portalled dialogs must follow page visibility. */
export default function RetainedSurface({
  active,
  children,
}: {
  active: boolean;
  children: ReactNode;
}) {
  const [host, setHost] = useState<HTMLDivElement | null>(null);
  const getContainer = useCallback(() => host!, [host]);
  return (
    <>
      {createPortal(
        <div ref={setHost} hidden={!active} className="wb-surface-portals" />,
        document.body,
      )}
      {host && (
        <ConfigProvider getPopupContainer={getContainer}>
          {children}
        </ConfigProvider>
      )}
    </>
  );
}
