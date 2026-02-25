import { app, Menu, shell, type MenuItemConstructorOptions } from "electron";

import { getMainWindow } from "./main";

/**
 * Creates the native application menu
 */
export function createMenu(): void {
  const isMac = process.platform === "darwin";

  const template: MenuItemConstructorOptions[] = [
    // App menu (macOS only)
    ...(isMac
      ? [
          {
            label: app.name,
            submenu: [
              { role: "about" as const },
              { type: "separator" as const },
              {
                label: "Preferences...",
                accelerator: "CmdOrCtrl+,",
                click: () => {
                  getMainWindow()?.webContents.send("menu:preferences");
                },
              },
              { type: "separator" as const },
              { role: "services" as const },
              { type: "separator" as const },
              { role: "hide" as const },
              { role: "hideOthers" as const },
              { role: "unhide" as const },
              { type: "separator" as const },
              { role: "quit" as const },
            ],
          },
        ]
      : []),

    // File menu
    {
      label: "File",
      submenu: [
        {
          label: "New Chat",
          accelerator: "CmdOrCtrl+N",
          click: () => {
            getMainWindow()?.webContents.send("menu:newChat");
          },
        },
        { type: "separator" },
        {
          label: "Export Chat...",
          accelerator: "CmdOrCtrl+Shift+E",
          click: () => {
            getMainWindow()?.webContents.send("menu:exportChat");
          },
        },
        { type: "separator" },
        isMac ? { role: "close" } : { role: "quit" },
      ],
    },

    // Edit menu
    {
      label: "Edit",
      submenu: [
        { role: "undo" },
        { role: "redo" },
        { type: "separator" },
        { role: "cut" },
        { role: "copy" },
        { role: "paste" },
        ...(isMac
          ? [
              { role: "pasteAndMatchStyle" as const },
              { role: "delete" as const },
              { role: "selectAll" as const },
            ]
          : [
              { role: "delete" as const },
              { type: "separator" as const },
              { role: "selectAll" as const },
            ]),
      ],
    },

    // View menu
    {
      label: "View",
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
        { type: "separator" },
        {
          label: "Toggle Sidebar",
          accelerator: "CmdOrCtrl+B",
          click: () => {
            getMainWindow()?.webContents.send("menu:toggleSidebar");
          },
        },
      ],
    },

    // Window menu
    {
      label: "Window",
      submenu: [
        { role: "minimize" },
        { role: "zoom" },
        ...(isMac
          ? [
              { type: "separator" as const },
              { role: "front" as const },
              { type: "separator" as const },
              { role: "window" as const },
            ]
          : [{ role: "close" as const }]),
      ],
    },

    // Help menu
    {
      role: "help",
      submenu: [
        {
          label: "Documentation",
          click: () => {
            void shell.openExternal("https://github.com/thinktank-ai/thinktank-ai");
          },
        },
        {
          label: "Report Issue",
          click: () => {
            void shell.openExternal("https://github.com/thinktank-ai/thinktank-ai/issues");
          },
        },
        { type: "separator" },
        {
          label: "Keyboard Shortcuts",
          accelerator: "CmdOrCtrl+?",
          click: () => {
            getMainWindow()?.webContents.send("menu:keyboardShortcuts");
          },
        },
      ],
    },
  ];

  const menu = Menu.buildFromTemplate(template);
  Menu.setApplicationMenu(menu);
}
