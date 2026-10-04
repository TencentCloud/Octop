/** Temporary rollout switch. Legacy remains the default until visual acceptance. */
export const WORKBUDDY_UI = import.meta.env.VITE_UI_VARIANT === "workbuddy";

if (typeof document !== "undefined") {
  document.documentElement.dataset.ui = WORKBUDDY_UI ? "workbuddy" : "legacy";
}
