import { getBackendBaseURL } from "../config";

import type { ProviderId, ProviderModel } from "./types";

function withDeviceHeaders(deviceId: string | undefined): Record<string, string> {
  const headers: Record<string, string> = {};
  if (deviceId) {
    headers["x-device-id"] = deviceId;
  }
  return headers;
}

export async function loadProviderModels(
  provider: ProviderId,
  deviceId: string | undefined,
) {
  const res = await fetch(`${getBackendBaseURL()}/api/providers/${provider}/models`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...withDeviceHeaders(deviceId) },
    body: JSON.stringify({}),
  });
  if (!res.ok) {
    throw new Error(`Failed to load ${provider} models (${res.status})`);
  }
  const data = (await res.json()) as { provider: ProviderId; models: ProviderModel[] };
  return data;
}

export async function validateProviderKey(
  provider: ProviderId,
  deviceId: string | undefined,
) {
  const res = await fetch(`${getBackendBaseURL()}/api/providers/${provider}/validate`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...withDeviceHeaders(deviceId) },
    body: JSON.stringify({}),
  });
  if (!res.ok) {
    throw new Error(`Failed to validate ${provider} API key (${res.status})`);
  }
  return (await res.json()) as {
    provider: ProviderId;
    valid: boolean;
    message: string;
  };
}

export async function getProviderKeyStatus(
  provider: ProviderId,
  deviceId: string | undefined,
) {
  const res = await fetch(`${getBackendBaseURL()}/api/providers/${provider}/key`, {
    headers: withDeviceHeaders(deviceId),
  });
  if (!res.ok) {
    throw new Error(`Failed to load ${provider} key status (${res.status})`);
  }
  return (await res.json()) as { provider: ProviderId; has_key: boolean };
}

export async function setProviderKey(
  provider: ProviderId,
  apiKey: string,
  deviceId: string | undefined,
) {
  const res = await fetch(`${getBackendBaseURL()}/api/providers/${provider}/key`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...withDeviceHeaders(deviceId) },
    body: JSON.stringify({ api_key: apiKey }),
  });
  if (!res.ok) {
    throw new Error(`Failed to store ${provider} API key (${res.status})`);
  }
  return (await res.json()) as { provider: ProviderId; has_key: boolean };
}

export async function deleteProviderKey(
  provider: ProviderId,
  deviceId: string | undefined,
) {
  const res = await fetch(`${getBackendBaseURL()}/api/providers/${provider}/key`, {
    method: "DELETE",
    headers: withDeviceHeaders(deviceId),
  });
  if (!res.ok) {
    throw new Error(`Failed to remove ${provider} API key (${res.status})`);
  }
  return (await res.json()) as { provider: ProviderId; has_key: boolean };
}
