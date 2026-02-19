import path from "path";
import fs from "fs";

import { app, ipcMain } from "electron";

import type { AppConfig } from "../../src/electron.d";

const CONFIG_FILE = path.join(app.getPath("userData"), "config.json");

const DEFAULT_CONFIG: AppConfig = {
  backendBaseUrl: "",
  langgraphBaseUrl: "http://localhost:2024",
  theme: "system",
  locale: "en-US",
};

/**
 * Load configuration from disk
 */
function loadConfig(): AppConfig {
  try {
    if (fs.existsSync(CONFIG_FILE)) {
      const data = fs.readFileSync(CONFIG_FILE, "utf-8");
      return { ...DEFAULT_CONFIG, ...JSON.parse(data) };
    }
  } catch (error) {
    console.error("Failed to load config:", error);
  }
  return DEFAULT_CONFIG;
}

/**
 * Save configuration to disk
 */
function saveConfig(config: AppConfig): void {
  try {
    const dir = path.dirname(CONFIG_FILE);
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }
    fs.writeFileSync(CONFIG_FILE, JSON.stringify(config, null, 2));
  } catch (error) {
    console.error("Failed to save config:", error);
    throw error;
  }
}

let currentConfig: AppConfig = DEFAULT_CONFIG;

/**
 * Register configuration IPC handlers
 */
export function registerConfigHandlers(): void {
  // Load config on startup
  currentConfig = loadConfig();

  ipcMain.handle("config:get", () => {
    return currentConfig;
  });

  ipcMain.handle("config:save", (_event, updates: Partial<AppConfig>) => {
    currentConfig = { ...currentConfig, ...updates };
    saveConfig(currentConfig);
  });
}

/**
 * Get current config (for use in main process)
 */
export function getConfig(): AppConfig {
  return currentConfig;
}
