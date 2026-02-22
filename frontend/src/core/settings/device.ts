import { uuid } from "@/core/utils/uuid";

const DEVICE_ID_KEY = "thinktank.device-id";

export function getDeviceId(): string | undefined {
  if (typeof window === "undefined") {
    return undefined;
  }
  const existing = localStorage.getItem(DEVICE_ID_KEY);
  if (existing) {
    return existing;
  }
  const created = uuid();
  localStorage.setItem(DEVICE_ID_KEY, created);
  return created;
}
