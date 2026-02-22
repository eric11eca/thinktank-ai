from typing import Any

from langchain.chat_models import BaseChatModel
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ConfigDict, Field

from src.config import get_app_config
from src.reflection import resolve_class
from src.models.patched_deepseek import PatchedChatDeepSeek


class RuntimeModelSpec(BaseModel):
    provider: str = Field(..., description="Provider identifier")
    model_id: str = Field(..., description="Provider model identifier")
    api_key: str | None = Field(default=None, description="API key for provider")
    device_id: str | None = Field(default=None, description="Device identifier for stored keys")
    tier: str | None = Field(default=None, description="Optional tier identifier")
    base_url: str | None = Field(default=None, description="Optional base URL override")
    supports_vision: bool | None = Field(default=None, description="Whether the model supports vision")
    model_config = ConfigDict(extra="allow")


PROVIDER_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "deepseek": "https://api.deepseek.com/v1",
    "kimi": "https://api.moonshot.ai/v1",
    "zai": "https://api.z.ai/api/paas/v4",
    "minimax": "https://api.minimax.io/v1",
}

ANTHROPIC_ADAPTIVE_THINKING_MODELS = {"claude-opus-4-6"}


def _runtime_tier_settings(spec: RuntimeModelSpec, thinking_enabled: bool) -> dict[str, Any]:
    if not thinking_enabled or not spec.tier:
        return {}
    provider = spec.provider.lower()
    if provider == "openai" and spec.tier.startswith("reasoning-"):
        effort = spec.tier.replace("reasoning-", "")
        return {"reasoning": {"effort": effort, "summary": "auto"}}
    if provider == "anthropic" and spec.tier == "thinking":
        if spec.model_id in ANTHROPIC_ADAPTIVE_THINKING_MODELS:
            return {"thinking": {"type": "adaptive", "effort": "medium"}}
        return {"thinking": {"type": "enabled", "budget_tokens": 10000}}
    if provider in {"deepseek", "kimi", "zai"} and spec.tier == "thinking":
        return {"extra_body": {"thinking": {"type": "enabled"}}}
    if provider == "deepseek" and spec.model_id.endswith("reasoner"):
        return {"extra_body": {"thinking": {"type": "enabled"}}}
    return {}


def _create_runtime_model(spec: RuntimeModelSpec, thinking_enabled: bool, **kwargs) -> BaseChatModel:
    provider = spec.provider.lower()
    if provider not in {"openai", "anthropic", "gemini", "deepseek", "kimi", "zai", "minimax"}:
        raise ValueError(f"Unsupported provider: {spec.provider}") from None
    api_key = (spec.api_key or "").strip()
    if not api_key:
        if spec.device_id:
            from src.security.api_key_store import get_api_key

            stored = get_api_key(spec.device_id, provider)
            api_key = stored.strip() if stored else ""
    if not api_key:
        raise ValueError(f"Model {spec.model_id} requires a non-empty api_key.") from None

    settings: dict[str, Any] = {
        "model": spec.model_id,
        "api_key": api_key,
    }
    if provider in PROVIDER_BASE_URLS:
        settings["base_url"] = spec.base_url or PROVIDER_BASE_URLS[provider]
    settings.update(_runtime_tier_settings(spec, thinking_enabled))
    settings.update(kwargs)

    if provider == "anthropic":
        settings.setdefault("max_tokens", 4096)
        return ChatAnthropic(**settings)
    if provider == "deepseek":
        if spec.base_url or PROVIDER_BASE_URLS.get(provider):
            settings.setdefault("api_base", spec.base_url or PROVIDER_BASE_URLS[provider])
            settings.pop("base_url", None)
        settings.setdefault("max_tokens", 4096)
        return PatchedChatDeepSeek(**settings)

    return ChatOpenAI(**settings)


def create_chat_model(
    name: str | None = None,
    thinking_enabled: bool = False,
    runtime_model: dict[str, Any] | RuntimeModelSpec | None = None,
    **kwargs,
) -> BaseChatModel:
    """Create a chat model instance from the config.

    Args:
        name: The name of the model to create. If None, the first model in the config will be used.

    Returns:
        A chat model instance.
    """
    if runtime_model is not None:
        spec = runtime_model if isinstance(runtime_model, RuntimeModelSpec) else RuntimeModelSpec.model_validate(runtime_model)
        return _create_runtime_model(spec, thinking_enabled, **kwargs)

    config = get_app_config()
    if name is None:
        name = config.models[0].name
    model_config = config.get_model_config(name)
    if model_config is None:
        raise ValueError(f"Model {name} not found in config") from None
    model_class = resolve_class(model_config.use, BaseChatModel)
    model_settings_from_config = model_config.model_dump(
        exclude_none=True,
        exclude={
            "use",
            "name",
            "display_name",
            "description",
            "supports_thinking",
            "when_thinking_enabled",
            "supports_vision",
        },
    )
    api_key = model_settings_from_config.get("api_key")
    if isinstance(api_key, str):
        if api_key.startswith("$"):
            env_name = api_key[1:]
            raise ValueError(
                f"Model {name} requires environment variable {env_name} to be set. Add it to `.env` or export it before starting the server."
            ) from None
        if not api_key.strip():
            raise ValueError(
                f"Model {name} has an empty api_key. Add it to `.env` or export it before starting the server."
            ) from None
    for field in ("base_url", "api_base"):
        value = model_settings_from_config.get(field)
        if isinstance(value, str) and value.startswith("$"):
            env_name = value[1:]
            raise ValueError(
                f"Model {name} requires environment variable {env_name} to be set. Add it to `.env` or export it before starting the server."
            ) from None
    if thinking_enabled and model_config.when_thinking_enabled is not None:
        if not model_config.supports_thinking:
            raise ValueError(f"Model {name} does not support thinking. Set `supports_thinking` to true in the `config.yaml` to enable thinking.") from None
        model_settings_from_config.update(model_config.when_thinking_enabled)
    model_instance = model_class(**kwargs, **model_settings_from_config)
    return model_instance
