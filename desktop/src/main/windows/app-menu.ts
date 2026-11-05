import type { MenuItemConstructorOptions } from "electron";

/**
 * Windows application menu. Caption buttons sit on the transparent title bar;
 * this menu stays at the leading edge.
 *
 * Submenu entries use Electron roles so the labels, accelerators, and the
 * edit commands follow the OS locale. Only the four top-level names and
 * About are ours.
 */

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

export function windowsApplicationMenu(
  locale: string,
  onAbout: () => void,
): MenuItemConstructorOptions[] {
  const labels = windowsAppMenuLabels(locale);
  return [
    {
      label: labels.file,
      submenu: [{ role: "close" }, { type: "separator" }, { role: "quit" }],
    },
    {
      label: labels.edit,
      submenu: [
        { role: "undo" },
        { role: "redo" },
        { type: "separator" },
        { role: "cut" },
        { role: "copy" },
        { role: "paste" },
        { role: "delete" },
        { type: "separator" },
        { role: "selectAll" },
      ],
    },
    {
      label: labels.view,
      submenu: [
        { role: "reload" },
        { role: "forceReload" },
        { role: "toggleDevTools" },
        { type: "separator" },
        { role: "resetZoom" },
        { role: "zoomIn" },
        { role: "zoomOut" },
        { type: "separator" },
        { role: "togglefullscreen" },
      ],
    },
    {
      label: labels.help,
      submenu: [{ label: labels.about, click: onAbout }],
    },
  ];
}
