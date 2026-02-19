import path from "path";
import { fileURLToPath } from "url";

import { app, BrowserWindow, shell } from "electron";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

import { createMenu } from "./menu";
import { setupAutoUpdater } from "./updater";
import { registerIPCHandlers } from "./ipc";

// Keep a global reference of the window object
let mainWindow: BrowserWindow | null = null;

// Determine if running in development
const isDev = process.env.NODE_ENV === "development";

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 900,
    minHeight: 600,
    webPreferences: {
      preload: path.join(__dirname, "preload.mjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
    // macOS native title bar
    titleBarStyle: process.platform === "darwin" ? "hiddenInset" : "default",
    trafficLightPosition: { x: 16, y: 16 },
    // Windows frame
    frame: process.platform !== "darwin",
    backgroundColor: "#1a1a1a",
    show: false, // Show when ready to prevent flash
  });

  // Show window when ready
  mainWindow.once("ready-to-show", () => {
    mainWindow?.show();
  });

  // Load the app
  if (isDev && process.env.VITE_DEV_SERVER_URL) {
    mainWindow.loadURL(process.env.VITE_DEV_SERVER_URL);
    mainWindow.webContents.openDevTools();
  } else {
    mainWindow.loadFile(path.join(__dirname, "../renderer/index.html"));
  }

  // Open external links in default browser
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith("http://") || url.startsWith("https://")) {
      shell.openExternal(url);
    }
    return { action: "deny" };
  });

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

// Initialize app
app.whenReady().then(() => {
  // Set up menu
  createMenu();

  // Register IPC handlers
  registerIPCHandlers();

  // Create main window
  createWindow();

  // Set up auto-updater (production only)
  if (!isDev) {
    setupAutoUpdater();
  }

  // macOS: Re-create window when clicking dock icon
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

// Quit when all windows are closed (except on macOS)
app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});

// Security: Prevent new window creation
app.on("web-contents-created", (_, contents) => {
  contents.on("will-navigate", (event, url) => {
    // Prevent navigation to external URLs
    const parsedUrl = new URL(url);
    if (parsedUrl.origin !== "file://") {
      event.preventDefault();
      shell.openExternal(url);
    }
  });
});

// Export for IPC handlers
export function getMainWindow(): BrowserWindow | null {
  return mainWindow;
}
