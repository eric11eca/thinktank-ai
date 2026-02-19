import { env } from "@/env";

export function getBackendBaseURL() {
  if (env.VITE_BACKEND_BASE_URL) {
    return env.VITE_BACKEND_BASE_URL;
  }
  return "";
}

export function getLangGraphBaseURL() {
  if (env.VITE_LANGGRAPH_BASE_URL) {
    return env.VITE_LANGGRAPH_BASE_URL;
  }
  // LangGraph SDK requires a full URL, construct it from current origin
  if (typeof window !== "undefined") {
    return `${window.location.origin}/api/langgraph`;
  }
  // Fallback for Electron
  return "http://localhost:2024";
}
