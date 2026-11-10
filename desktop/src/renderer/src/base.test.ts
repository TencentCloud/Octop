import assert from "node:assert/strict";
import { createHash } from "node:crypto";
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

const rendered = await less.render(
  readFileSync(new URL("./base.less", import.meta.url), "utf8"),
  { filename: "base.less" },
);
const css = rendered.css.replace(/\/\*[\s\S]*?\*\//g, "");
const rules = [...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)].map((match) => ({
  selectors: match[1]!.split(",").map((selector) => selector.trim()),
  declarations: Object.fromEntries(
    match[2]!.split(";").filter((declaration) => declaration.trim()).map((declaration) => {
      const colon = declaration.indexOf(":");
      return [declaration.slice(0, colon).trim(), declaration.slice(colon + 1).trim()];
    }),
  ),
}));

test("启动页与错误页仅在固定顶部全宽 58px 内允许拖动", () => {
  const dragRules = rules.filter(({ declarations }) =>
    declarations["-webkit-app-region"] === "drag" || declarations["app-region"] === "drag",
  );
  assert.equal(dragRules.length, 1, "不能恢复整页拖动区域");
  const drag = dragRules[0]!;
  assert.deepEqual(drag.selectors, ["body::before"]);
  assert.deepEqual(drag.declarations, {
    content: '""',
    position: "fixed",
    top: "0",
    left: "0",
    right: "0",
    "z-index": "2",
    height: "58px",
    "user-select": "none",
    "-webkit-app-region": "drag",
    "app-region": "drag",
  });
  for (const page of ["splash", "error"]) {
    const source = readFileSync(new URL(`./${page}.tsx`, import.meta.url), "utf8");
    assert.match(source, /import "\.\/base\.less";/);
  }
});

test("按钮、表单、详情和可编辑内容保持 no-drag", () => {
  for (const selector of [
    "button", "summary", "a", "input", "textarea", "select", "pre",
    '[role="button"]', "[contenteditable]",
  ]) {
    const rule = rules.find(({ selectors, declarations }) =>
      selectors.includes(selector) && declarations["app-region"] === "no-drag",
    );
    assert.ok(rule, `${selector} 必须允许正常交互`);
    assert.equal(rule.declarations["-webkit-app-region"], "no-drag");
  }
});

test("深色主题覆盖底色，浅色仍是默认", () => {
  const root = rules.find(({ selectors }) => selectors.includes(":root"));
  assert.ok(root);
  assert.equal(root.declarations["color-scheme"], "light");
  assert.equal(root.declarations["--page"], "#f5f6f8");
  assert.equal(root.declarations["--surface"], "#ffffff");
  assert.equal(root.declarations["--text"], "#111827");
  const dark = rules.find(({ selectors }) => selectors.includes('html[data-theme="dark"]'));
  assert.ok(dark);
  assert.equal(dark.declarations["color-scheme"], "dark");
  assert.equal(dark.declarations["--page"], "#0e0e0e");
  assert.equal(dark.declarations["--surface"], "#1e1e1e");
  assert.equal(dark.declarations["--text"], "rgba(255, 255, 255, 0.9)");
  assert.equal(dark.declarations["--brand"], "#f08b9a");
});

test("壳启动横版标与仪表盘是同一对图", () => {
  for (const name of ["logo_horizontal_dark.png", "logo_horizontal_white.png"]) {
    const shell = readFileSync(new URL(`./assets/${name}`, import.meta.url));
    const dashboard = readFileSync(
      new URL(`../../../../dashboard/public/${name}`, import.meta.url),
    );
    assert.deepEqual(shell, dashboard);
  }
});

test("启动页和错误页共用同一段主题脚本，且 CSP 哈希对得上", () => {
  const script = /<script id="octop-shell-theme">([\s\S]*?)<\/script>/;
  const splash = readFileSync(new URL("../splash.html", import.meta.url), "utf8");
  const error = readFileSync(new URL("../error.html", import.meta.url), "utf8");
  const splashBody = splash.match(script)?.[1];
  const errorBody = error.match(script)?.[1];
  assert.ok(splashBody);
  assert.equal(splashBody, errorBody);
  const hash = createHash("sha256").update(splashBody).digest("base64");
  assert.ok(splash.includes(`'sha256-${hash}'`));
  assert.ok(error.includes(`'sha256-${hash}'`));
});

test("正文和错误详情不被整页禁选规则影响", () => {
  for (const { selectors, declarations } of rules) {
    if (selectors.includes("body::before")) continue;
    assert.notEqual(declarations["user-select"], "none");
    assert.notEqual(declarations["-webkit-user-select"], "none");
  }
});
