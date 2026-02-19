import { ipcMain } from "electron";

import { checkForUpdates, downloadUpdate, installUpdate } from "../updater";

/**
 * Register auto-updater IPC handlers
 */
export function registerUpdateHandlers(): void {
  ipcMain.handle("update:check", async () => {
    await checkForUpdates();
  });

  ipcMain.handle("update:download", async () => {
    await downloadUpdate();
  });

  ipcMain.handle("update:install", () => {
    installUpdate();
  });
}
