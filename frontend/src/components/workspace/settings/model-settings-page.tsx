"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Item,
  ItemContent,
  ItemDescription,
  ItemTitle,
} from "@/components/ui/item";
import { Switch } from "@/components/ui/switch";
import { useI18n } from "@/core/i18n/hooks";
import {
  deleteProviderKey,
  getProviderKeyStatus,
  setProviderKey,
} from "@/core/models/api";
import { useProviderModels, useValidateProviderKey } from "@/core/models/hooks";
import type { ProviderId, ProviderModel } from "@/core/models/types";
import { useLocalSettings } from "@/core/settings";
import { getLocalSettings } from "@/core/settings/local";
import { env } from "@/env";
import { cn } from "@/lib/utils";

import { SettingsSection } from "./settings-section";

const PROVIDER_LABELS: Record<
  ProviderId,
  { title: string; description: string }
> = {
  openai: {
    title: "OpenAI",
    description: "OpenAI API models (latest non-deprecated).",
  },
  anthropic: {
    title: "Anthropic",
    description: "Claude models from Anthropic.",
  },
  gemini: {
    title: "Gemini",
    description: "Google Gemini API models.",
  },
  deepseek: {
    title: "DeepSeek",
    description: "DeepSeek chat and reasoning models.",
  },
  kimi: {
    title: "Kimi",
    description: "Moonshot Kimi models.",
  },
  zai: {
    title: "Z.ai",
    description: "Z.ai GLM models (curated list).",
  },
  minimax: {
    title: "Minimax",
    description: "MiniMax M2 series models (curated list).",
  },
};

export function ModelSettingsPage() {
  const { t } = useI18n();
  const [settings, setSettings] = useLocalSettings();
  const providers = useMemo(
    () =>
      Object.entries(settings.models.providers) as Array<
        [ProviderId, (typeof settings.models.providers)[ProviderId]]
      >,
    [settings.models.providers],
  );

  return (
    <SettingsSection
      title={t.settings.models.title}
      description={t.settings.models.description}
    >
      <div className="flex w-full flex-col gap-4">
        {providers.map(([providerId, providerConfig]) => (
          <ProviderSection
            key={providerId}
            providerId={providerId}
            providerConfig={providerConfig}
            setSettings={setSettings}
          />
        ))}
      </div>
    </SettingsSection>
  );
}

function ProviderSection({
  providerId,
  providerConfig,
  setSettings,
}: {
  providerId: ProviderId;
  providerConfig: {
    enabled: boolean;
    has_key: boolean;
    api_key?: string;
    last_validated_at?: string;
    last_validation_status?: "valid" | "invalid" | "unknown";
    last_validation_message?: string;
  };
  setSettings: ReturnType<typeof useLocalSettings>[1];
}) {
  const { t } = useI18n();
  const providerMeta = PROVIDER_LABELS[providerId];
  const legacyKeyUploadedRef = useRef(false);
  const [pendingKey, setPendingKey] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const validationMutation = useValidateProviderKey();
  const modelsQuery = useProviderModels(
    providerId,
    providerConfig.has_key,
    providerConfig.enabled,
  );

  const updateProvider = useCallback(
    (updates: Partial<typeof providerConfig>) => {
      const latest = getLocalSettings();
      const latestProviders = latest.models.providers;
      const currentProvider =
        latestProviders[providerId] ?? providerConfig ?? { enabled: false, has_key: false };
      setSettings("models", {
        providers: {
          ...latestProviders,
          [providerId]: {
            ...currentProvider,
            ...updates,
          },
        },
        enabled_models: latest.models.enabled_models,
      });
    },
    [providerConfig, providerId, setSettings],
  );

  const handleProviderToggle = useCallback(
    (enabled: boolean) => {
      updateProvider({ enabled });
    },
    [updateProvider],
  );

  const handleValidate = useCallback(async () => {
    setIsSaving(true);
    try {
      if (pendingKey.trim()) {
        await setProviderKey(providerId, pendingKey.trim());
        setPendingKey("");
        updateProvider({ has_key: true });
      }
      const result = await validationMutation.mutateAsync({
        provider: providerId,
      });
      updateProvider({
        last_validated_at: new Date().toISOString(),
        last_validation_status: result.valid ? "valid" : "invalid",
        last_validation_message: result.message,
      });
      if (result.valid) {
        void modelsQuery.refetch();
      }
    } finally {
      setIsSaving(false);
    }
  }, [modelsQuery, pendingKey, providerId, updateProvider, validationMutation]);

  const handleRemoveKey = useCallback(async () => {
    setIsSaving(true);
    try {
      await deleteProviderKey(providerId);
      updateProvider({
        has_key: false,
        last_validated_at: undefined,
        last_validation_status: "unknown",
        last_validation_message: undefined,
      });
    } finally {
      setIsSaving(false);
    }
  }, [modelsQuery, providerId, updateProvider]);

  useEffect(() => {
    if (legacyKeyUploadedRef.current) {
      return;
    }
    const legacyKey = providerConfig.api_key?.trim();
    if (!legacyKey) {
      return;
    }
    legacyKeyUploadedRef.current = true;
    setProviderKey(providerId, legacyKey)
      .then(() => {
        updateProvider({
          api_key: undefined,
          has_key: true,
        });
      })
      .catch(() => {
        legacyKeyUploadedRef.current = false;
      });
  }, [providerConfig.api_key, providerConfig.enabled, providerId, updateProvider]);

  useEffect(() => {
    if (!providerConfig.enabled) {
      return;
    }
    getProviderKeyStatus(providerId)
      .then((status) => {
        updateProvider({ has_key: status.has_key });
      })
      .catch(() => {
        // Ignore status errors; keep last known state.
      });
  }, [providerConfig.enabled, providerId, updateProvider]);

  return (
    <Item className="w-full" variant="outline">
      <ItemContent>
        <ItemTitle className="flex items-center justify-between gap-3">
          <span>{providerMeta.title}</span>
          <Switch
            checked={providerConfig.enabled}
            disabled={env.VITE_STATIC_WEBSITE_ONLY === "true"}
            onCheckedChange={handleProviderToggle}
          />
        </ItemTitle>
        <ItemDescription>{providerMeta.description}</ItemDescription>
        {providerConfig.enabled && (
          <div className="mt-4 flex w-full flex-col gap-3">
            <div className="flex flex-col gap-2">
              <label className="text-sm font-medium">{t.settings.models.apiKeyLabel}</label>
              <div className="flex flex-col gap-2 md:flex-row">
                <Input
                  value={pendingKey}
                  type="password"
                  placeholder={t.settings.models.apiKeyPlaceholder}
                  onChange={(event) => setPendingKey(event.target.value)}
                />
                <Button
                  type="button"
                  variant="outline"
                  className="md:w-40"
                  disabled={
                    validationMutation.isPending ||
                    isSaving ||
                    (!pendingKey.trim() && !providerConfig.has_key) ||
                    env.VITE_STATIC_WEBSITE_ONLY === "true"
                  }
                  onClick={handleValidate}
                >
                  {t.settings.models.validate}
                </Button>
                {providerConfig.has_key && (
                  <Button
                    type="button"
                    variant="ghost"
                    className="md:w-32"
                    disabled={isSaving || env.VITE_STATIC_WEBSITE_ONLY === "true"}
                    onClick={handleRemoveKey}
                  >
                    {t.common.remove}
                  </Button>
                )}
              </div>
              {providerConfig.has_key && (
                <div className="text-muted-foreground text-xs">
                  {t.settings.models.apiKeyStored}
                </div>
              )}
              {providerConfig.last_validation_message && (
                <div
                  className={cn(
                    "text-xs",
                    providerConfig.last_validation_status === "valid"
                      ? "text-emerald-600"
                      : "text-rose-500",
                  )}
                >
                  {providerConfig.last_validation_message}
                </div>
              )}
            </div>
            <ProviderModelsList
              providerConfig={providerConfig}
              models={modelsQuery.data?.models ?? []}
              isLoading={modelsQuery.isLoading}
              error={modelsQuery.error instanceof Error ? modelsQuery.error : undefined}
            />
          </div>
        )}
      </ItemContent>
    </Item>
  );
}

function ProviderModelsList({
  providerConfig,
  models,
  isLoading,
  error,
}: {
  providerConfig: {
    has_key: boolean;
  };
  models: ProviderModel[];
  isLoading: boolean;
  error: Error | undefined;
}) {
  const { t } = useI18n();
  const [settings, setSettings] = useLocalSettings();
  const enabledModels = settings.models.enabled_models;

  const toggleModel = useCallback(
    (modelId: string, enabled: boolean) => {
      const latest = getLocalSettings();
      const latestEnabledModels = latest.models.enabled_models ?? {};
      setSettings("models", {
        providers: latest.models.providers,
        enabled_models: {
          ...latestEnabledModels,
          [modelId]: enabled,
        },
      });
    },
    [setSettings],
  );

  if (!providerConfig.has_key) {
    return (
      <div className="text-muted-foreground text-sm">
        {t.settings.models.enterApiKeyHint}
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="text-muted-foreground text-sm">{t.common.loading}</div>
    );
  }

  if (error) {
    return <div className="text-sm text-rose-500">{error.message}</div>;
  }

  if (models.length === 0) {
    return (
      <div className="text-muted-foreground text-sm">
        {t.settings.models.noModelsHint}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="text-sm font-medium">{t.settings.models.modelsLabel}</div>
      <div className="flex flex-col gap-2">
        {models.map((model) => {
          const enabled = enabledModels[model.id] ?? true;
          return (
            <Item key={model.id} className="w-full border border-border/50">
              <ItemContent>
                <ItemTitle className="text-sm">{model.display_name}</ItemTitle>
                {model.tier_label && (
                  <ItemDescription className="text-xs">
                    {model.tier_label}
                  </ItemDescription>
                )}
              </ItemContent>
              <div className="flex items-center">
                <Switch
                  checked={enabled}
                  onCheckedChange={(checked) => toggleModel(model.id, checked)}
                />
              </div>
            </Item>
          );
        })}
      </div>
    </div>
  );
}
