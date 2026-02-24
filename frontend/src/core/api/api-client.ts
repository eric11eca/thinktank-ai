import { Client as LangGraphClient } from "@langchain/langgraph-sdk/client";

import { getAccessToken } from "@/core/auth/token";

import { getLangGraphBaseURL } from "../config";

let _singleton: LangGraphClient | null = null;
let _currentToken: string | null = null;

export function getAPIClient(): LangGraphClient {
  const token = getAccessToken();
  // Recreate client when token changes (login/refresh/logout)
  if (_singleton === null || _currentToken !== token) {
    _currentToken = token;
    _singleton = new LangGraphClient({
      apiUrl: getLangGraphBaseURL(),
      defaultHeaders: token ? { Authorization: `Bearer ${token}` } : {},
    });
  }
  return _singleton;
}

export function resetAPIClient(): void {
  _singleton = null;
  _currentToken = null;
}
