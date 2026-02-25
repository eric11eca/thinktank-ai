import { autoUpdater } from "electron-updater";

import { getMainWindow } from "./main";

/**
 * Sets up the auto-updater for production builds
 * Uses electron-updater with GitHub releases
 */
export function setupAutoUpdater(): void {
  // Configure auto-updater
  autoUpdater.autoDownload = false;
  autoUpdater.autoInstallOnAppQuit = true;

  // Log updates
  autoUpdater.logger = console;

  // Update available
  autoUpdater.on("update-available", (info) => {
    const mainWindow = getMainWindow();
    mainWindow?.webContents.send("update:available", {
      version: info.version,
      releaseDate: info.releaseDate,
      releaseNotes: info.releaseNotes,
    });
  });

  // Download progress
  autoUpdater.on("download-progress", (progress) => {
    const mainWindow = getMainWindow();
    mainWindow?.webContents.send("update:progress", {
      percent: progress.percent,
      bytesPerSecond: progress.bytesPerSecond,
      total: progress.total,
      transferred: progress.transferred,
    });
  });

  // Update downloaded
  autoUpdater.on("update-downloaded", (info) => {
    const mainWindow = getMainWindow();
    mainWindow?.webContents.send("update:downloaded", {
      version: info.version,
      releaseDate: info.releaseDate,
      releaseNotes: info.releaseNotes,
    });
  });

  // Error handling
  autoUpdater.on("error", (error) => {
    const mainWindow = getMainWindow();
    mainWindow?.webContents.send("update:error", {
      message: error.message,
    });
    console.error("Auto-updater error:", error);
  });

  // Check for updates after startup (delay to not block initial load)
  setTimeout(() => {
    autoUpdater.checkForUpdates().catch((error) => {
      console.error("Failed to check for updates:", error);
    });
  }, 5000);
}

/**
 * Check for updates manually
 */
export async function checkForUpdates(): Promise<void> {
  await autoUpdater.checkForUpdates();
}

/**
 * Download the available update
 */
export async function downloadUpdate(): Promise<void> {
  await autoUpdater.downloadUpdate();
}

/**
 * Install the downloaded update and restart
 */
export function installUpdate(): void {
  autoUpdater.quitAndInstall(false, true);
}
