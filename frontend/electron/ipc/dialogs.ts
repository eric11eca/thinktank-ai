import fs from "fs";

import { ipcMain, dialog, BrowserWindow } from "electron";

import type { OpenFileOptions, SaveFileOptions } from "../../src/electron.d";

/**
 * Register dialog IPC handlers
 */
export function registerDialogHandlers(): void {
  // Open file dialog
  ipcMain.handle(
    "dialog:openFile",
    async (_event, options?: OpenFileOptions): Promise<string | null> => {
      const window = BrowserWindow.getFocusedWindow();
      if (!window) return null;

      const result = await dialog.showOpenDialog(window, {
        title: options?.title ?? "Open File",
        filters: options?.filters ?? [{ name: "All Files", extensions: ["*"] }],
        properties: options?.multiple
          ? ["openFile", "multiSelections"]
          : ["openFile"],
      });

      if (result.canceled || result.filePaths.length === 0) {
        return null;
      }

      return options?.multiple
        ? (result.filePaths as unknown as string)
        : result.filePaths[0]!;
    }
  );

  // Save file dialog
  ipcMain.handle(
    "dialog:saveFile",
    async (
      _event,
      data: string | ArrayBuffer,
      options?: SaveFileOptions
    ): Promise<boolean> => {
      const window = BrowserWindow.getFocusedWindow();
      if (!window) return false;

      const result = await dialog.showSaveDialog(window, {
        title: options?.title ?? "Save File",
        defaultPath: options?.defaultPath,
        filters: options?.filters ?? [{ name: "All Files", extensions: ["*"] }],
      });

      if (result.canceled || !result.filePath) {
        return false;
      }

      try {
        if (typeof data === "string") {
          fs.writeFileSync(result.filePath, data, "utf-8");
        } else {
          fs.writeFileSync(result.filePath, Buffer.from(data));
        }
        return true;
      } catch (error) {
        console.error("Failed to save file:", error);
        return false;
      }
    }
  );
}
