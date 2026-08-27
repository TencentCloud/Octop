import { Modal } from "antd";
import type { HookAPI } from "antd/es/modal/useModal";

/**
 * Theme-aware modal API bound from antd `<App>` via App.useApp().
 * Prefer this over `Modal.confirm` (static methods ignore ConfigProvider theme).
 */
let bound: HookAPI | null = null;

export function bindAntdModal(api: HookAPI): void {
  bound = api;
}

export function unbindAntdModal(): void {
  bound = null;
}

function resolve(): HookAPI {
  return bound ?? (Modal as unknown as HookAPI);
}

export const modal: HookAPI = new Proxy({} as HookAPI, {
  get(_target, prop, _receiver) {
    const api = resolve();
    const value = Reflect.get(api, prop, api);
    return typeof value === "function" ? value.bind(api) : value;
  },
});
