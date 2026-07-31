import { App } from "antd";
import { useEffect, type ReactNode } from "react";
import { bindAntdMessage, unbindAntdMessage } from "../utils/antdMessage";

/** Captures App.useApp() APIs for non-hook call sites (utils, hooks, callbacks). */
function AntdAppApiBinder() {
  const { message } = App.useApp();
  useEffect(() => {
    bindAntdMessage(message);
    return () => {
      unbindAntdMessage();
    };
  }, [message]);
  return null;
}

/** Wrap under ConfigProvider so message/modal/notification follow theme. */
export function AntdAppProvider({ children }: { children: ReactNode }) {
  return (
    <App>
      <AntdAppApiBinder />
      {children}
    </App>
  );
}
