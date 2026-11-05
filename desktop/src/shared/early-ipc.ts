/**
 * Channels the shell's own pages may use.
 *
 * Deliberately its own module rather than a slice of {@link IPC_CHANNELS}:
 * a sandboxed preload can only require ``electron`` and Node built-ins, so it
 * cannot load a Rollup *shared chunk*. Keeping these constants in their own
 * module lets the bundler inline them, which keeps every preload entry a
 * single self-contained file.
 *
 * The Dashboard bridge (``octopDesktop``) must never grow a "restart the app"
 * method. The failure page calls ``octopShell.restart`` instead. The splash
 * window uses the Dashboard preload so it can stay open and load the page.
 */
export const EARLY_IPC = {
  restart: "octop:early-restart",
} as const;
