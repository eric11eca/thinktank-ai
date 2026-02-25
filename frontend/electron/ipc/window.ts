import { ipcMain } from "electron";

import { getMainWindow } from "../main";

/**
 * Register window control IPC handlers
 */
export function registerWindowHandlers(): void {
  ipcMain.handle("window:minimize", () => {
    const window = getMainWindow();
    window?.minimize();
  });

  ipcMain.handle("window:maximize", () => {
    const window = getMainWindow();
    if (window) {
      if (window.isMaximized()) {
        window.unmaximize();
      } else {
        window.maximize();
      }
    }
  });

  ipcMain.handle("window:close", () => {
    const window = getMainWindow();
    window?.close();
  });

  ipcMain.handle("window:isMaximized", () => {
    const window = getMainWindow();
    return window?.isMaximized() ?? false;
  });

  // Listen for maximize/unmaximize events and notify renderer
  const setupWindowEvents = () => {
    const window = getMainWindow();
    if (!window) return;

    window.on("maximize", () => {
      window.webContents.send("window:maximized");
    });

    window.on("unmaximize", () => {
      window.webContents.send("window:unmaximized");
    });
  };

  // Set up events when window is created
  setTimeout(setupWindowEvents, 100);
}
