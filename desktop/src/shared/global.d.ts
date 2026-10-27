import type { OctopDesktopBridge } from "./preload/index";

declare global {
  interface Window {
    octopDesktop?: OctopDesktopBridge;
  }
}

export {};
