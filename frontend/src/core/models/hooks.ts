import { useEffect, useMemo, useRef } from "react";
import { useMutation, useQueries, useQuery } from "@tanstack/react-query";

import { useLocalSettings } from "../settings";
import { getLocalSettings } from "../settings/local";

import { getProviderKeyStatus, loadProviderModels, validateProviderKey } from "./api";
import type { ProviderId, ProviderModel, RuntimeModelSpec } from "./types";

export function useProviderModels(
  provider: ProviderId,
  hasKey: boolean,
  enabled: boolean,
) {
  const queryOptions = {
    staleTime: Infinity,
    gcTime: Infinity,
    retry: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    refetchOnMount: false,
  } as const;
  return useQuery({
    queryKey: ["provider-models", provider],
    queryFn: () => loadProviderModels(provider),
    enabled: enabled && hasKey,
    ...queryOptions,
  });
}

export function useValidateProviderKey() {
  return useMutation({
    mutationFn: async ({
      provider,
    }: {
      provider: ProviderId;
    }) => {
      return validateProviderKey(provider);
    },
  });
}

export function useModels({ enabled = true }: { enabled?: boolean } = {}) {
  const [settings, setSettings] = useLocalSettings();
  const syncedRef = useRef(false);
  const providerEntries = Object.entries(settings.models.providers) as Array<
    [ProviderId, (typeof settings.models.providers)[ProviderId]]
  >;

  useEffect(() => {
    if (syncedRef.current) {
      return;
    }
    syncedRef.current = true;
    Promise.all(
      providerEntries.map(async ([providerId]) => {
        try {
          const status = await getProviderKeyStatus(providerId);
          return [providerId, status.has_key] as const;
        } catch {
          return [providerId, undefined] as const;
        }
      }),
    ).then((results) => {
      const latest = getLocalSettings();
      const updates: Record<ProviderId, Partial<(typeof latest.models.providers)[ProviderId]>> =
        {} as Record<ProviderId, Partial<(typeof latest.models.providers)[ProviderId]>>;
      for (const [providerId, hasKey] of results) {
        if (typeof hasKey === "boolean") {
          updates[providerId] = {
            ...latest.models.providers[providerId],
            has_key: hasKey,
          };
        }
      }
      if (Object.keys(updates).length > 0) {
        setSettings("models", {
          providers: {
            ...latest.models.providers,
            ...updates,
          },
          enabled_models: latest.models.enabled_models,
        });
      }
    });
  }, [providerEntries, setSettings, settings.models.providers]);

  const providerQueries = useQueries({
    queries: providerEntries.map(([providerId, config]) => ({
      queryKey: ["provider-models", providerId],
      queryFn: () => loadProviderModels(providerId),
      enabled: enabled && config.enabled && config.has_key,
      staleTime: Infinity,
      gcTime: Infinity,
      retry: false,
      refetchOnWindowFocus: false,
      refetchOnReconnect: false,
      refetchOnMount: false,
    })),
  });

  const { models, isLoading, error } = useMemo(() => {
    const enabledMap = settings.models.enabled_models ?? {};
    const combined = providerQueries.flatMap((query) => query.data?.models ?? []);
    const filtered = combined
      .filter((model) => {
      const providerEnabled = settings.models.providers[model.provider]?.enabled;
      return providerEnabled && enabledMap[model.id] !== false;
      })
      .sort((a, b) => a.display_name.localeCompare(b.display_name));
    return {
      models: filtered,
      isLoading: providerQueries.some((query) => query.isLoading),
      error: providerQueries.find((query) => query.error)?.error,
    };
  }, [providerQueries, settings.models.enabled_models, settings.models.providers]);

  return { models, isLoading, error };
}

export function getRuntimeModelSpec(
  model: ProviderModel | undefined,
): RuntimeModelSpec | undefined {
  if (!model) {
    return undefined;
  }
  return {
    provider: model.provider,
    model_id: model.model_id,
    tier: model.tier ?? undefined,
    supports_vision: model.supports_vision,
  };
}
