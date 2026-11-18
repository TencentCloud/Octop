import assert from "node:assert/strict";
import { test } from "node:test";
import type { MenuItemConstructorOptions } from "electron";

import {
  windowsApplicationMenu,
  windowsAppMenuLabels,
  windowsMenuCommandId,
  windowsMenuModel,
} from "./app-menu";

function roles(item: MenuItemConstructorOptions): string[] {
  const submenu = item.submenu;
  assert.ok(Array.isArray(submenu));
  return submenu.flatMap((entry) => (entry.role ? [entry.role] : []));
}

test("菜单名跟随语言", () => {
  assert.deepEqual(windowsAppMenuLabels("zh-CN"), {
    file: "文件",
    edit: "编辑",
    view: "视图",
    help: "帮助",
    about: "关于 Octop",
  });
  assert.deepEqual(windowsAppMenuLabels("en-US"), {
    file: "File",
    edit: "Edit",
    view: "View",
    help: "Help",
    about: "About Octop",
  });
});

test("四个顶层菜单带上常规命令", () => {
  let abouts = 0;
  const menu = windowsApplicationMenu("zh-CN", () => {
    abouts += 1;
  });
  assert.deepEqual(
    menu.map((item) => item.label),
    ["文件", "编辑", "视图", "帮助"],
  );
  assert.deepEqual(roles(menu[0]!), ["close", "quit"]);
  assert.deepEqual(roles(menu[1]!), [
    "undo",
    "redo",
    "cut",
    "copy",
    "paste",
    "delete",
    "selectAll",
  ]);
  assert.deepEqual(roles(menu[2]!), [
    "reload",
    "forceReload",
    "toggleDevTools",
    "resetZoom",
    "zoomIn",
    "zoomOut",
    "togglefullscreen",
  ]);
  const help = menu[3]?.submenu;
  assert.ok(Array.isArray(help));
  assert.equal(help[0]?.label, "关于 Octop");
  help[0]?.click?.(
    {} as never,
    undefined,
    {} as never,
  );
  assert.equal(abouts, 1);
});

test("页面上的菜单带中文标签和快捷键", () => {
  const model = windowsMenuModel("zh-CN");
  assert.deepEqual(model.titles, ["文件", "编辑", "视图", "帮助"]);
  assert.deepEqual(model.menus[0], [
    { kind: "command", id: "close", label: "关闭", accelerator: "Ctrl+W" },
    { kind: "separator" },
    { kind: "command", id: "quit", label: "退出", accelerator: null },
  ]);
  assert.equal(model.menus[1][0]?.kind === "command" && model.menus[1][0].label, "撤销");
  assert.equal(model.menus[3][0]?.kind === "command" && model.menus[3][0].accelerator, null);
});

test("英文菜单用 Exit，不接受菜单以外的命令", () => {
  const file = windowsMenuModel("en-US").menus[0];
  assert.equal(file[2]?.kind === "command" && file[2].label, "Exit");
  assert.equal(windowsMenuCommandId("copy"), "copy");
  assert.equal(windowsMenuCommandId("about"), "about");
  assert.equal(windowsMenuCommandId("new-agent"), null);
  assert.equal(windowsMenuCommandId(0), null);
});
