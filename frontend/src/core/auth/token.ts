const ACCESS_TOKEN_KEY = "thinktank.access_token";

let _memoryToken: string | null = null;

export function getAccessToken(): string | null {
  if (_memoryToken) return _memoryToken;
  if (typeof window === "undefined") return null;
  return localStorage.getItem(ACCESS_TOKEN_KEY);
}

export function setAccessToken(token: string): void {
  _memoryToken = token;
  if (typeof window !== "undefined") {
    localStorage.setItem(ACCESS_TOKEN_KEY, token);
  }
}

export function clearAccessToken(): void {
  _memoryToken = null;
  if (typeof window !== "undefined") {
    localStorage.removeItem(ACCESS_TOKEN_KEY);
  }
}

/**
 * Decode a JWT payload without verification (for reading expiry client-side).
 */
function decodeJwtPayload(token: string): Record<string, unknown> | null {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return null;
    const payload = atob(parts[1]!.replace(/-/g, "+").replace(/_/g, "/"));
    return JSON.parse(payload) as Record<string, unknown>;
  } catch {
    return null;
  }
}

/**
 * Check if a JWT token is expired or will expire within the given margin.
 */
export function isTokenExpired(
  token: string,
  marginSeconds = 120,
): boolean {
  const payload = decodeJwtPayload(token);
  if (!payload || typeof payload.exp !== "number") return true;
  const nowSeconds = Math.floor(Date.now() / 1000);
  return payload.exp - marginSeconds <= nowSeconds;
}
