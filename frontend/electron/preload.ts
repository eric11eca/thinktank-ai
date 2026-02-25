import { contextBridge, ipcRenderer } from "electron";

import type { ElectronAPI, AppConfig, OpenFileOptions, SaveFileOptions } from "../src/electron.d";

/**
 * Preload script - runs in a sandboxed context with access to Node.js
 * Exposes a secure API to the renderer process via contextBridge
 */

const electronAPI: ElectronAPI = {
  // Platform info
  platform: process.platform,

  // Generic IPC methods
  invoke: <T = unknown>(channel: string, ...args: unknown[]): Promise<T> => {
    // Whitelist of allowed channels
    const allowedChannels = [
      "config:get",
      "config:save",
      "dialog:openFile",
      "dialog:saveFile",
      "window:minimize",
      "window:maximize",
      "window:close",
      "window:isMaximized",
      "threads:search",
      "threads:delete",
      "threads:updateState",
      "update:check",
      "update:download",
      "update:install",
    ];

    if (!allowedChannels.includes(channel)) {
      return Promise.reject(new Error(`IPC channel "${channel}" is not allowed`));
    }

    return ipcRenderer.invoke(channel, ...args);
  },

  on: (channel: string, callback: (...args: unknown[]) => void): (() => void) => {
    // Whitelist of allowed event channels
    const allowedEventChannels = [
      "update:available",
      "update:progress",
      "update:downloaded",
      "update:error",
      "window:maximized",
      "window:unmaximized",
    ];

    if (!allowedEventChannels.includes(channel)) {
      console.warn(`IPC event channel "${channel}" is not allowed`);
      return () => undefined;
    }

    const listener = (_event: Electron.IpcRendererEvent, ...args: unknown[]) => {
      callback(...args);
    };

    ipcRenderer.on(channel, listener);

    // Return cleanup function
    return () => {
      ipcRenderer.removeListener(channel, listener);
    };
  },

  // Configuration
  getConfig: (): Promise<AppConfig> => {
    return ipcRenderer.invoke("config:get");
  },

  saveConfig: (config: Partial<AppConfig>): Promise<void> => {
    return ipcRenderer.invoke("config:save", config);
  },

  // File operations
  openFile: (options?: OpenFileOptions): Promise<string | string[] | null> => {
    return ipcRenderer.invoke("dialog:openFile", options);
  },

  saveFile: (data: string | ArrayBuffer, options?: SaveFileOptions): Promise<boolean> => {
    return ipcRenderer.invoke("dialog:saveFile", data, options);
  },

  // Window controls
  minimize: (): void => {
    void ipcRenderer.invoke("window:minimize");
  },

  maximize: (): void => {
    void ipcRenderer.invoke("window:maximize");
  },

  close: (): void => {
    void ipcRenderer.invoke("window:close");
  },

  isMaximized: (): Promise<boolean> => {
    return ipcRenderer.invoke("window:isMaximized");
  },

  // App info
  getVersion: (): string => {
    return process.env.npm_package_version ?? "0.1.0";
  },

  // Auto-updater
  checkForUpdates: (): Promise<void> => {
    return ipcRenderer.invoke("update:check");
  },

  downloadUpdate: (): Promise<void> => {
    return ipcRenderer.invoke("update:download");
  },

  installUpdate: (): void => {
    void ipcRenderer.invoke("update:install");
  },
};

// Expose to renderer
contextBridge.exposeInMainWorld("electronAPI", electronAPI);
