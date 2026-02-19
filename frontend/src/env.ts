/**
 * Environment variables for Vite + Electron
 * Replaces @t3-oss/env-nextjs with Vite-compatible approach
 */

interface Env {
  VITE_BACKEND_BASE_URL: string;
  VITE_LANGGRAPH_BASE_URL: string;
  VITE_STATIC_WEBSITE_ONLY: string;
  NODE_ENV: string;
  IS_ELECTRON: boolean;
}

function getEnv(): Env {
  const isElectron =
    typeof window !== "undefined" && window.electronAPI !== undefined;

  return {
    VITE_BACKEND_BASE_URL: import.meta.env.VITE_BACKEND_BASE_URL ?? "",
    VITE_LANGGRAPH_BASE_URL: import.meta.env.VITE_LANGGRAPH_BASE_URL ?? "",
    VITE_STATIC_WEBSITE_ONLY: import.meta.env.VITE_STATIC_WEBSITE_ONLY ?? "",
    NODE_ENV: import.meta.env.MODE,
    IS_ELECTRON: isElectron,
  };
}

export const env = getEnv();
