/**
 * Type declarations for Electron IPC API
 * Exposed via contextBridge in preload.ts
 */

export interface ElectronAPI {
  /** Current platform (darwin, win32, linux) */
  platform: NodeJS.Platform;

  /** Invoke an IPC handler and return result */
  invoke: <T = unknown>(channel: string, ...args: unknown[]) => Promise<T>;

  /** Listen to IPC events from main process */
  on: (channel: string, callback: (...args: unknown[]) => void) => () => void;

  /** Get application configuration */
  getConfig: () => Promise<AppConfig>;

  /** Save application configuration */
  saveConfig: (config: Partial<AppConfig>) => Promise<void>;

  /** Open file dialog and return selected path(s) */
  openFile: (options?: OpenFileOptions) => Promise<string | string[] | null>;

  /** Save file dialog */
  saveFile: (
    data: string | ArrayBuffer,
    options?: SaveFileOptions
  ) => Promise<boolean>;

  /** Window controls */
  minimize: () => void;
  maximize: () => void;
  close: () => void;
  isMaximized: () => Promise<boolean>;

  /** App info */
  getVersion: () => string;

  /** Check for updates */
  checkForUpdates: () => Promise<void>;
  downloadUpdate: () => Promise<void>;
  installUpdate: () => void;
}

export interface AppConfig {
  backendBaseUrl: string;
  langgraphBaseUrl: string;
  theme: "light" | "dark" | "system";
  locale: "en-US" | "zh-CN";
}

export interface OpenFileOptions {
  title?: string;
  filters?: Array<{ name: string; extensions: string[] }>;
  multiple?: boolean;
}

export interface SaveFileOptions {
  title?: string;
  defaultPath?: string;
  filters?: Array<{ name: string; extensions: string[] }>;
}

declare global {
  interface Window {
    electronAPI?: ElectronAPI;
  }
}

export {};
