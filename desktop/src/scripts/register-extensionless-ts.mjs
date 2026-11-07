import { register } from "node:module";

// Node's type stripper keeps ESM specifiers literal, so `pnpm test` would
// fail on the extensionless imports that `tsc` (moduleResolution bundler)
// and electron-vite accept. This hook appends `.ts` before those loads.
register("./resolve-extensionless-ts.mjs", import.meta.url);
