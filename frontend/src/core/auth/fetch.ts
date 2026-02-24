/**
 * Authenticated fetch wrapper that automatically injects JWT Authorization
 * headers and handles 401 responses with token refresh + retry.
 */

import { refreshToken } from "./api";
import { clearAccessToken, getAccessToken, isTokenExpired } from "./token";

export async function authFetch(
  url: string,
  options?: RequestInit,
): Promise<Response> {
  let token = getAccessToken();

  // Proactively refresh if token is about to expire
  if (token && isTokenExpired(token, 120)) {
    const newToken = await refreshToken();
    token = newToken;
  }

  const headers = new Headers(options?.headers);
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(url, { ...options, headers });

  // If 401, try refreshing the token and retrying once
  if (response.status === 401 && token) {
    const newToken = await refreshToken();
    if (newToken) {
      headers.set("Authorization", `Bearer ${newToken}`);
      return fetch(url, { ...options, headers });
    }

    // Refresh failed - clear token and redirect to login
    clearAccessToken();
    if (typeof window !== "undefined") {
      window.location.href = "/login";
    }
  }

  return response;
}
