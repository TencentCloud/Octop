import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { test } from "node:test";

const require = createRequire(import.meta.url);
const less = require("less") as {
  render: (
    input: string,
    options?: { filename?: string },
  ) => Promise<{ css: string }>;
};

test("Linux 窗口按钮是方的，关闭悬停变红", async () => {
  const rendered = await less.render(
    readFileSync(new URL("./linux-window-controls.module.less", import.meta.url), "utf8"),
    { filename: "linux-window-controls.module.less" },
  );
  const css = rendered.css;
  assert.match(css, /\.controls button \{[^}]*border-radius:\s*0/);
  assert.match(css, /\.close:hover[\s\S]*background:\s*#e81123/);
  assert.doesNotMatch(css, /border-radius:\s*50%/);
  for (const page of ["splash", "error"]) {
    const source = readFileSync(new URL(`./${page}.tsx`, import.meta.url), "utf8");
    assert.match(source, /LinuxWindowControls/);
  }
});
