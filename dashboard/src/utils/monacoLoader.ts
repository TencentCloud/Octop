/**
 * Serve Monaco from the app origin instead of the jsDelivr CDN that
 * `@monaco-editor/loader` defaults to, so the editor works without internet.
 * Build only: the dev server cannot serve the AMD tree.
 */
import { loader } from "@monaco-editor/react";

/** Absolute URL of the Monaco tree copied by `vite.config.ts`. */
export const monacoVsPath = new URL(
  `${import.meta.env.BASE_URL}monaco/vs`,
  window.location.origin,
).href;

/** Redirect the loader in built apps; dev keeps the CDN default. */
export function configureMonacoLoader(dev: boolean): void {
  if (dev) return;
  loader.config({ paths: { vs: monacoVsPath } });
}

configureMonacoLoader(import.meta.env.DEV);
