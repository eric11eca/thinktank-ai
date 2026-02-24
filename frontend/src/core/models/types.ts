export type ProviderId =
  | "openai"
  | "anthropic"
  | "gemini"
  | "deepseek"
  | "kimi"
  | "zai"
  | "minimax";

export interface ProviderModel {
  id: string;
  provider: ProviderId;
  model_id: string;
  display_name: string;
  description?: string | null;
  supports_thinking?: boolean;
  supports_vision?: boolean;
  tier?: string | null;
  tier_label?: string | null;
}

export interface RuntimeModelSpec {
  provider: ProviderId;
  model_id: string;
  tier?: string | null;
  api_key?: string;

  supports_vision?: boolean;
}
