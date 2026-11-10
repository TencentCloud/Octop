import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

test("Linux 窗口按钮是方的，关闭悬停变红", () => {
  const css = readFileSync(new URL("./linux-window-controls.css", import.meta.url), "utf8");
  assert.match(css, /\.octop-linux-controls button \{[^}]*border-radius:\s*0/);
  assert.match(css, /\.octop-linux-controls-close:hover[\s\S]*background:\s*#e81123/);
  assert.doesNotMatch(css, /border-radius:\s*50%/);
  for (const page of ["splash", "error"]) {
    const source = readFileSync(new URL(`./${page}.tsx`, import.meta.url), "utf8");
    assert.match(source, /LinuxWindowControls/);
  }
});
