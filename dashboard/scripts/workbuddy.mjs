import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const action = process.argv[2];
if (action !== "dev" && action !== "build")
  throw new Error("Use workbuddy.mjs dev|build");
const root = new URL("../", import.meta.url);
const env = { ...process.env, VITE_UI_VARIANT: "workbuddy" };
function run(relative, args) {
  return new Promise((resolve, reject) => {
    const child = spawn(
      process.execPath,
      [fileURLToPath(new URL(relative, root)), ...args],
      { cwd: fileURLToPath(root), env, stdio: "inherit" },
    );
    child.on("error", reject);
    child.on("exit", (code, signal) => resolve(signal ? 1 : code ?? 1));
  });
}
if (action === "build") {
  const code = await run("node_modules/typescript/bin/tsc", ["-b"]);
  if (code) process.exit(code);
}
process.exitCode = await run(
  "node_modules/vite/bin/vite.js",
  action === "build" ? ["build"] : ["--host"],
);
