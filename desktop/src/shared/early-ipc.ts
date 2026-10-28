/**
 * Channels the shell's own pages may use.
 *
 * Deliberately its own module rather than a slice of {@link IPC_CHANNELS}:
 * a sandboxed preload can only require ``electron`` and Node built-ins, so it
 * cannot load a Rollup *shared chunk*. Keeping these constants in a module that
 * only ``preload/early.ts`` imports lets the bundler inline them, which keeps
 * every preload entry a single self-contained file.
 *
 * The Dashboard bridge must never grow a "restart the app" method, so the split
 * also encodes that: only the shell's splash / fatal-error pages talk on these.
 */
export const EARLY_IPC = {
  restart: "octop:early-restart",
} as const;
