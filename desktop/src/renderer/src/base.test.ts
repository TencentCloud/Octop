import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const css = readFileSync(new URL("./base.css", import.meta.url), "utf8")
  .replace(/\/\*[\s\S]*?\*\//g, "");
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
    height: "58px",
    "pointer-events": "none",
    "user-select": "none",
    "-webkit-app-region": "drag",
    "app-region": "drag",
  });
  for (const page of ["splash", "error"]) {
    const source = readFileSync(new URL(`./${page}.tsx`, import.meta.url), "utf8");
    assert.match(source, /import "\.\/base\.css";/);
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

test("正文和错误详情不被整页禁选规则影响", () => {
  for (const { selectors, declarations } of rules) {
    if (selectors.includes("body::before")) continue;
    assert.notEqual(declarations["user-select"], "none");
    assert.notEqual(declarations["-webkit-user-select"], "none");
  }
});
