import { getBackendBaseURL } from "../config";

import { clearAccessToken, getAccessToken, setAccessToken } from "./token";
import type { TokenResponse, UserResponse } from "./types";

const AUTH_BASE = () => `${getBackendBaseURL()}/api/auth`;

export async function registerUser(
  email: string,
  password: string,
  displayName?: string,
): Promise<TokenResponse> {
  const res = await fetch(`${AUTH_BASE()}/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({
      email,
      password,
      display_name: displayName ?? null,
    }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Registration failed" }));
    throw new Error(err.detail ?? "Registration failed");
  }

  const data = (await res.json()) as TokenResponse;
  setAccessToken(data.access_token);
  return data;
}

export async function loginUser(
  email: string,
  password: string,
): Promise<TokenResponse> {
  const res = await fetch(`${AUTH_BASE()}/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ email, password }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Login failed" }));
    throw new Error(err.detail ?? "Invalid email or password");
  }

  const data = (await res.json()) as TokenResponse;
  setAccessToken(data.access_token);
  return data;
}

export async function refreshToken(): Promise<string | null> {
  try {
    const res = await fetch(`${AUTH_BASE()}/refresh`, {
      method: "POST",
      credentials: "include",
    });

    if (!res.ok) {
      clearAccessToken();
      return null;
    }

    const data = (await res.json()) as { access_token: string };
    setAccessToken(data.access_token);
    return data.access_token;
  } catch {
    clearAccessToken();
    return null;
  }
}

export async function fetchCurrentUser(): Promise<UserResponse | null> {
  const token = getAccessToken();
  if (!token) return null;

  try {
    const res = await fetch(`${AUTH_BASE()}/me`, {
      headers: { Authorization: `Bearer ${token}` },
    });

    if (!res.ok) return null;
    return (await res.json()) as UserResponse;
  } catch {
    return null;
  }
}

export async function logoutUser(): Promise<void> {
  const token = getAccessToken();
  try {
    await fetch(`${AUTH_BASE()}/logout`, {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      credentials: "include",
    });
  } catch {
    // Ignore errors during logout
  }
  clearAccessToken();
}
