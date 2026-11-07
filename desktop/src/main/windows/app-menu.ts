import type { MenuItemConstructorOptions } from "electron";

/**
 * Windows application menu. The transparent caption overlay hides the native
 * menu bar, so the page draws the four titles and their submenus. The native
 * menu stays installed so its accelerators still fire.
 *
 * Submenu roles keep the real commands (copy, reload, quit). The labels the
 * page shows are ours, because a role's `label` stays English until the OS
 * paints the native menu.
 */

const WINDOWS_MENU_COMMANDS = [
  "close",
  "quit",
  "undo",
  "redo",
  "cut",
  "copy",
  "paste",
  "delete",
  "selectAll",
  "reload",
  "forceReload",
  "toggleDevTools",
  "resetZoom",
  "zoomIn",
  "zoomOut",
  "togglefullscreen",
  "about",
] as const;

export type WindowsMenuCommandId = (typeof WINDOWS_MENU_COMMANDS)[number];

/** A command id the page is allowed to run, or null. */
export function windowsMenuCommandId(value: unknown): WindowsMenuCommandId | null {
  if (typeof value !== "string") return null;
  return WINDOWS_MENU_COMMANDS.includes(value as WindowsMenuCommandId)
    ? (value as WindowsMenuCommandId)
    : null;
}

export interface WindowsMenuCommand {
  kind: "command";
  id: WindowsMenuCommandId;
  label: string;
  accelerator: string | null;
}

export interface WindowsMenuSeparator {
  kind: "separator";
}

export type WindowsMenuEntry = WindowsMenuCommand | WindowsMenuSeparator;

export interface WindowsMenuModel {
  titles: [string, string, string, string];
  menus: [WindowsMenuEntry[], WindowsMenuEntry[], WindowsMenuEntry[], WindowsMenuEntry[]];
}

export interface WindowsAppMenuLabels {
  file: string;
  edit: string;
  view: string;
  help: string;
  about: string;
}

export function windowsAppMenuLabels(locale: string): WindowsAppMenuLabels {
  if (locale.toLowerCase().startsWith("zh")) {
    return {
      file: "文件",
      edit: "编辑",
      view: "视图",
      help: "帮助",
      about: "关于 Octop",
    };
  }
  return {
    file: "File",
    edit: "Edit",
    view: "View",
    help: "Help",
    about: "About Octop",
  };
}

function command(
  id: WindowsMenuCommandId,
  label: string,
  accelerator: string | null,
): WindowsMenuCommand {
  return { kind: "command", id, label, accelerator };
}

/** What the page draws. One list per top-level menu, in title order. */
export function windowsMenuModel(locale: string): WindowsMenuModel {
  const labels = windowsAppMenuLabels(locale);
  const zh = locale.toLowerCase().startsWith("zh");
  const text = (zhLabel: string, enLabel: string) => (zh ? zhLabel : enLabel);
  return {
    titles: [labels.file, labels.edit, labels.view, labels.help],
    menus: [
      [
        command("close", text("关闭", "Close"), "Ctrl+W"),
        { kind: "separator" },
        command("quit", text("退出", "Exit"), null),
      ],
      [
        command("undo", text("撤销", "Undo"), "Ctrl+Z"),
        command("redo", text("重做", "Redo"), "Ctrl+Y"),
        { kind: "separator" },
        command("cut", text("剪切", "Cut"), "Ctrl+X"),
        command("copy", text("复制", "Copy"), "Ctrl+C"),
        command("paste", text("粘贴", "Paste"), "Ctrl+V"),
        command("delete", text("删除", "Delete"), "Delete"),
        { kind: "separator" },
        command("selectAll", text("全选", "Select All"), "Ctrl+A"),
      ],
      [
        command("reload", text("重新加载", "Reload"), "Ctrl+R"),
        command("forceReload", text("强制重新加载", "Force Reload"), "Ctrl+Shift+R"),
        command("toggleDevTools", text("开发者工具", "Toggle Developer Tools"), "Ctrl+Shift+I"),
        { kind: "separator" },
        command("resetZoom", text("实际大小", "Actual Size"), "Ctrl+0"),
        command("zoomIn", text("放大", "Zoom In"), "Ctrl++"),
        command("zoomOut", text("缩小", "Zoom Out"), "Ctrl+-"),
        { kind: "separator" },
        command("togglefullscreen", text("切换全屏", "Toggle Full Screen"), "F11"),
      ],
      [command("about", labels.about, null)],
    ],
  };
}

export function windowsApplicationMenu(
  locale: string,
  onAbout: () => void,
): MenuItemConstructorOptions[] {
  const model = windowsMenuModel(locale);
  return model.titles.map((label, index) => ({
    label,
    submenu: (model.menus[index] ?? []).map((entry): MenuItemConstructorOptions => {
      if (entry.kind === "separator") return { type: "separator" };
      if (entry.id === "about") return { id: entry.id, label: entry.label, click: onAbout };
      return { id: entry.id, role: entry.id };
    }),
  }));
}
