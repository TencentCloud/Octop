import { message as staticMessage } from "antd";
import type { MessageInstance } from "antd/es/message/interface";

/**
 * Theme-aware message API bound from antd `<App>` via App.useApp().
 * Prefer this over `import { message } from "antd"` (static methods warn and
 * ignore ConfigProvider theme).
 */
let bound: MessageInstance | null = null;

export function bindAntdMessage(api: MessageInstance): void {
  bound = api;
}

export function unbindAntdMessage(): void {
  bound = null;
}

function resolve(): MessageInstance {
  return bound ?? staticMessage;
}

export const message: MessageInstance = new Proxy({} as MessageInstance, {
  get(_target, prop, _receiver) {
    const api = resolve();
    const value = Reflect.get(api, prop, api);
    return typeof value === "function" ? value.bind(api) : value;
  },
});
