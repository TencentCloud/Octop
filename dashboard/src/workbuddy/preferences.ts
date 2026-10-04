import { useSyncExternalStore } from "react";

export const WORKBUDDY_APPEARANCE_KEY = "octop:workbuddy:appearance-v1";
export const WORKBUDDY_ASSISTANT_PIN_KEY =
  "octop:workbuddy:assistant-pinned-v1";
export const WORKBUDDY_NAV_COLLAPSED_KEY = "octop:workbuddy:nav-collapsed-v1";
const EVENT = "octop:workbuddy-preferences";
const memory = new Map<string, string>();
function read(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return memory.get(key) ?? null;
  }
}
function write(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    memory.set(key, value);
  }
  window.dispatchEvent(new Event(EVENT));
}
function subscribe(listener: () => void) {
  window.addEventListener(EVENT, listener);
  window.addEventListener("storage", listener);
  return () => {
    window.removeEventListener(EVENT, listener);
    window.removeEventListener("storage", listener);
  };
}
export function resolveAssistantPinned(
  stored: string | null,
  legacyOpen: string | null,
  legacyLayout: string | null,
): boolean {
  if (stored !== null) return stored === "true";
  if (legacyOpen !== null) return legacyOpen === "true";
  return legacyLayout !== "minimal";
}
const getPinned = () =>
  resolveAssistantPinned(
    read(WORKBUDDY_ASSISTANT_PIN_KEY),
    read("octop:chat-sidebar:open"),
    read("octop:layout-mode"),
  );
export function useAssistantPanelPreference(): [
  boolean,
  (pinned: boolean) => void,
] {
  const value = useSyncExternalStore(subscribe, getPinned, () => true);
  return [value, (next) => write(WORKBUDDY_ASSISTANT_PIN_KEY, String(next))];
}
const getCustom = () => read(WORKBUDDY_APPEARANCE_KEY) === "custom";
export function useWorkBuddyAppearance(): [boolean, (custom: boolean) => void] {
  const value = useSyncExternalStore(subscribe, getCustom, () => false);
  return [
    value,
    (next) => write(WORKBUDDY_APPEARANCE_KEY, next ? "custom" : "standard"),
  ];
}
