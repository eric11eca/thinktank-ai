from __future__ import annotations

import hashlib
import re
import time
from collections.abc import Iterable
from dataclasses import dataclass

import httpx
from pydantic import BaseModel, ConfigDict, Field

DEFAULT_TIMEOUT_SECONDS = 12.0
CACHE_TTL_SECONDS = 300.0


class ProviderModelInfo(BaseModel):
    id: str = Field(..., description="Stable unique identifier for the model option")
    provider: str = Field(..., description="Provider identifier")
    model_id: str = Field(..., description="Provider model identifier")
    display_name: str = Field(..., description="Display name for UI")
    description: str | None = Field(default=None, description="Optional model description")
    supports_thinking: bool = Field(default=False, description="Whether model supports thinking mode")
    supports_vision: bool = Field(default=False, description="Whether model supports vision inputs")
    tier: str | None = Field(default=None, description="Optional tier identifier")
    tier_label: str | None = Field(default=None, description="Human-readable tier label")
    model_config = ConfigDict(extra="forbid")


class ProviderCatalogError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProviderModelTier:
    id: str
    label: str
    supports_thinking: bool


_MODEL_CACHE: dict[str, tuple[float, list[ProviderModelInfo]]] = {}

SUPPORTED_PROVIDERS = {
    "openai",
    "anthropic",
    "gemini",
    "deepseek",
    "kimi",
    "zai",
    "minimax",
    "epfl-rcp",
}

OPENAI_DEPRECATED_MODELS = {
    "gpt-4-0314",
    "gpt-4-1106-preview",
    "gpt-4-0125-preview",
    "gpt-3.5-turbo-instruct",
    "gpt-3.5-turbo-1106",
    "babbage-002",
    "davinci-002",
    "dall-e-2",
    "dall-e-3",
}

ANTHROPIC_DEPRECATED_MODELS = {
    "claude-3-7-sonnet-20250219",
}

ANTHROPIC_THINKING_MODELS = {
    "claude-haiku-4-5-20251001",
    "claude-3-7-sonnet-20250219",
    "claude-sonnet-4-20250514",
    "claude-sonnet-4-5-20250929",
    "claude-sonnet-4-6",
    "claude-opus-4-20250514",
    "claude-opus-4-1-20250805",
    "claude-opus-4-5-20251101",
    "claude-opus-4-6",
}

ANTHROPIC_ADAPTIVE_THINKING_MODELS = {
    "claude-opus-4-6",
}

OPENAI_TIER_MODEL = "gpt-5.2"

OPENAI_GPT5_TIERS = [
    ProviderModelTier(id="reasoning-low", label="Reasoning: Low", supports_thinking=True),
    ProviderModelTier(id="reasoning-medium", label="Reasoning: Medium", supports_thinking=True),
    ProviderModelTier(id="reasoning-high", label="Reasoning: High", supports_thinking=True),
    ProviderModelTier(id="reasoning-extra-high", label="Reasoning: Extra High", supports_thinking=True),
]

ZAI_MODELS = [
    "glm-5",
    "glm-4.7",
    "glm-4.7-flashx",
    "glm-4.7-flash",
    "glm-4.6",
    "glm-4.5",
    "glm-4.5-x",
    "glm-4.5-air",
    "glm-4.5-airx",
    "glm-4.5-flash",
    "glm-4-32b-0414-128k",
    "glm-4.6v",
]

ZAI_THINKING_MODELS = {
    "glm-5",
    "glm-4.7",
    "glm-4.6",
    "glm-4.5",
}

MINIMAX_MODELS = [
    "MiniMax-M2.5",
    "MiniMax-M2.5-highspeed",
    "MiniMax-M2.1",
    "MiniMax-M2.1-highspeed",
    "MiniMax-M2",
    "M2-her",
]

EPFL_RCP_MODELS = [
    "Qwen/Qwen3-235B-A22B-Thinking-2507",
    "openai/gpt-oss-120b",
    "moonshotai/Kimi-K2.5",
    "deepseek-ai/DeepSeek-V3.2",
    "swiss-ai/Apertus-8B-Instruct-2509",
    "zai-org/GLM-4.7",
]

ZAI_BASE_URL = "https://api.z.ai/api/paas/v4"
MINIMAX_BASE_URL = "https://api.minimax.io/v1"
EPFL_RCP_BASE_URL = "https://inference-rcp.epfl.ch/v1"


def _cache_key(provider: str, api_key: str | None, base_url: str | None) -> str:
    key_material = api_key or "no-key"
    hashed = hashlib.sha256(key_material.encode("utf-8")).hexdigest()
    return f"{provider}:{hashed}:{base_url or ''}"


def _get_cached_models(cache_key: str) -> list[ProviderModelInfo] | None:
    cached = _MODEL_CACHE.get(cache_key)
    if cached is None:
        return None
    timestamp, models = cached
    if time.time() - timestamp > CACHE_TTL_SECONDS:
        _MODEL_CACHE.pop(cache_key, None)
        return None
    return models


def _set_cached_models(cache_key: str, models: list[ProviderModelInfo]) -> None:
    _MODEL_CACHE[cache_key] = (time.time(), models)


def _format_display_name(model_id: str) -> str:
    if model_id.startswith("gpt-"):
        return f"GPT-{model_id[4:]}"
    if model_id.startswith("claude-"):
        return model_id.replace("claude-", "Claude ").replace("-", " ").title()
    if model_id.startswith("gemini-"):
        return model_id.replace("gemini-", "Gemini ").replace("-", " ").title()
    if model_id.startswith("deepseek-"):
        return model_id.replace("deepseek-", "DeepSeek ").replace("-", " ").title()
    if model_id.startswith("kimi-"):
        return model_id.replace("kimi-", "Kimi ").replace("-", " ").title()
    if model_id.startswith("glm-"):
        return model_id.replace("glm-", "GLM-").upper()
    return model_id.replace("-", " ").title()


def _supports_vision(model_id: str) -> bool:
    lowered = model_id.lower()
    if "vision" in lowered:
        return True
    if lowered.endswith(("v", "v-preview")):
        return True
    if lowered.startswith(("gpt-4o", "gpt-4.1", "gpt-4.5")):
        return True
    return False


def _openai_model_matches_constraints(model_id: str) -> bool:
    lowered = model_id.lower()
    return "gpt-5.2" in lowered and "codex" not in lowered


def _anthropic_model_matches_constraints(model_id: str) -> bool:
    lowered = model_id.lower()
    return "4.6" in lowered or "4-6" in lowered


def _build_model_id(provider: str, model_id: str, tier: str | None) -> str:
    return f"{provider}:{model_id}:{tier or 'standard'}"


def _openai_model_allowed(model_id: str) -> bool:
    if model_id in OPENAI_DEPRECATED_MODELS:
        return False
    lowered = model_id.lower()
    if any(keyword in lowered for keyword in ("embedding", "audio", "image", "whisper", "tts", "transcribe")):
        return False
    if lowered.startswith("gpt-"):
        return True
    return bool(re.match(r"^o\\d", lowered))


async def _fetch_openai_models(api_key: str) -> list[ProviderModelInfo]:
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS) as client:
        response = await client.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        response.raise_for_status()
        payload = response.json()
    models = []
    for item in payload.get("data", []):
        model_id = item.get("id")
        if not model_id or not _openai_model_allowed(model_id):
            continue
        if not _openai_model_matches_constraints(model_id):
            continue
        display_name = _format_display_name(model_id)
        if model_id == OPENAI_TIER_MODEL:
            for tier in OPENAI_GPT5_TIERS:
                models.append(
                    ProviderModelInfo(
                        id=_build_model_id("openai", model_id, tier.id),
                        provider="openai",
                        model_id=model_id,
                        display_name=f"{display_name} ({tier.label})",
                        supports_thinking=tier.supports_thinking,
                        supports_vision=_supports_vision(model_id),
                        tier=tier.id,
                        tier_label=tier.label,
                    )
                )
            continue
        models.append(
            ProviderModelInfo(
                id=_build_model_id("openai", model_id, None),
                provider="openai",
                model_id=model_id,
                display_name=display_name,
                supports_thinking=True,
                supports_vision=_supports_vision(model_id),
            )
        )
    return sorted(models, key=lambda model: model.display_name)


async def _fetch_anthropic_models(api_key: str) -> list[ProviderModelInfo]:
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS) as client:
        response = await client.get(
            "https://api.anthropic.com/v1/models",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
        )
        response.raise_for_status()
        payload = response.json()
    models = []
    for item in payload.get("data", []):
        model_id = item.get("id")
        if not model_id or model_id in ANTHROPIC_DEPRECATED_MODELS:
            continue
        if not _anthropic_model_matches_constraints(model_id):
            continue
        display_name = item.get("display_name") or _format_display_name(model_id)
        models.append(
            ProviderModelInfo(
                id=_build_model_id("anthropic", model_id, None),
                provider="anthropic",
                model_id=model_id,
                display_name=display_name,
                supports_thinking=False,
                supports_vision=True,
            )
        )
        if model_id in ANTHROPIC_THINKING_MODELS:
            models.append(
                ProviderModelInfo(
                    id=_build_model_id("anthropic", model_id, "thinking"),
                    provider="anthropic",
                    model_id=model_id,
                    display_name=f"{display_name} (Thinking)",
                    supports_thinking=True,
                    supports_vision=True,
                    tier="thinking",
                    tier_label="Thinking",
                )
            )
    return sorted(models, key=lambda model: model.display_name)


async def _fetch_gemini_models(api_key: str) -> list[ProviderModelInfo]:
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS) as client:
        response = await client.get(
            "https://generativelanguage.googleapis.com/v1beta/models",
            params={"key": api_key},
        )
        response.raise_for_status()
        payload = response.json()
    models = []
    for item in payload.get("models", []):
        name = item.get("name", "")
        model_id = name.replace("models/", "")
        if not model_id or not model_id.startswith("gemini-"):
            continue
        supported = item.get("supportedGenerationMethods")
        if isinstance(supported, list) and "generateContent" not in supported:
            continue
        display_name = _format_display_name(model_id)
        models.append(
            ProviderModelInfo(
                id=_build_model_id("gemini", model_id, None),
                provider="gemini",
                model_id=model_id,
                display_name=display_name,
                supports_thinking=False,
                supports_vision=_supports_vision(model_id),
            )
        )
    return sorted(models, key=lambda model: model.display_name)


async def _fetch_deepseek_models(api_key: str) -> list[ProviderModelInfo]:
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS) as client:
        response = await client.get(
            "https://api.deepseek.com/models",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        response.raise_for_status()
        payload = response.json()
    models = []
    for item in payload.get("data", []):
        model_id = item.get("id")
        if not model_id:
            continue
        supports_thinking = model_id.endswith("reasoner")
        display_name = _format_display_name(model_id)
        models.append(
            ProviderModelInfo(
                id=_build_model_id("deepseek", model_id, None),
                provider="deepseek",
                model_id=model_id,
                display_name=display_name,
                supports_thinking=supports_thinking,
                supports_vision=False,
            )
        )
    return sorted(models, key=lambda model: model.display_name)


async def _fetch_kimi_models(api_key: str) -> list[ProviderModelInfo]:
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS) as client:
        response = await client.get(
            "https://api.moonshot.ai/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        response.raise_for_status()
        payload = response.json()
    models = []
    for item in payload.get("data", []):
        model_id = item.get("id")
        if not model_id:
            continue
        display_name = _format_display_name(model_id)
        if model_id == "kimi-k2.5":
            models.append(
                ProviderModelInfo(
                    id=_build_model_id("kimi", model_id, None),
                    provider="kimi",
                    model_id=model_id,
                    display_name=display_name,
                    supports_thinking=False,
                    supports_vision=_supports_vision(model_id),
                )
            )
            models.append(
                ProviderModelInfo(
                    id=_build_model_id("kimi", model_id, "thinking"),
                    provider="kimi",
                    model_id=model_id,
                    display_name=f"{display_name} (Thinking)",
                    supports_thinking=True,
                    supports_vision=_supports_vision(model_id),
                    tier="thinking",
                    tier_label="Thinking",
                )
            )
            continue
        supports_thinking = "thinking" in model_id
        models.append(
            ProviderModelInfo(
                id=_build_model_id("kimi", model_id, None),
                provider="kimi",
                model_id=model_id,
                display_name=display_name,
                supports_thinking=supports_thinking,
                supports_vision=_supports_vision(model_id),
            )
        )
    return sorted(models, key=lambda model: model.display_name)


def _manual_provider_models(
    provider: str,
    model_ids: Iterable[str],
    thinking_models: set[str] | None = None,
    *,
    add_thinking_tier: bool = True,
) -> list[ProviderModelInfo]:
    thinking_models = thinking_models or set()
    models = []
    for model_id in model_ids:
        display_name = _format_display_name(model_id)
        supports_thinking = model_id in thinking_models
        models.append(
            ProviderModelInfo(
                id=_build_model_id(provider, model_id, None),
                provider=provider,
                model_id=model_id,
                display_name=display_name,
                supports_thinking=supports_thinking,
                supports_vision=_supports_vision(model_id),
            )
        )
        if supports_thinking and add_thinking_tier:
            models.append(
                ProviderModelInfo(
                    id=_build_model_id(provider, model_id, "thinking"),
                    provider=provider,
                    model_id=model_id,
                    display_name=f"{display_name} (Thinking)",
                    supports_thinking=True,
                    supports_vision=_supports_vision(model_id),
                    tier="thinking",
                    tier_label="Thinking",
                )
            )
    return sorted(models, key=lambda model: model.display_name)


async def list_provider_models(provider: str, api_key: str | None, base_url: str | None = None) -> list[ProviderModelInfo]:
    provider = provider.lower()
    if provider not in SUPPORTED_PROVIDERS:
        raise ProviderCatalogError(f"Unsupported provider: {provider}")
    if provider in {"openai", "anthropic", "gemini", "deepseek", "kimi", "epfl-rcp"} and not api_key:
        raise ProviderCatalogError(f"Provider {provider} requires an API key to list models.")

    cache_key = _cache_key(provider, api_key, base_url)
    cached = _get_cached_models(cache_key)
    if cached is not None:
        return cached

    if provider == "openai":
        models = await _fetch_openai_models(api_key or "")
    elif provider == "anthropic":
        models = await _fetch_anthropic_models(api_key or "")
    elif provider == "gemini":
        models = await _fetch_gemini_models(api_key or "")
    elif provider == "deepseek":
        models = await _fetch_deepseek_models(api_key or "")
    elif provider == "kimi":
        models = await _fetch_kimi_models(api_key or "")
    elif provider == "zai":
        models = _manual_provider_models("zai", ZAI_MODELS, ZAI_THINKING_MODELS)
    elif provider == "minimax":
        models = _manual_provider_models("minimax", MINIMAX_MODELS, set())
    elif provider == "epfl-rcp":
        models = _manual_provider_models(
            "epfl-rcp",
            EPFL_RCP_MODELS,
            set(EPFL_RCP_MODELS),
            add_thinking_tier=False,
        )
    else:
        models = []

    _set_cached_models(cache_key, models)
    return models


async def validate_provider_key(provider: str, api_key: str | None, base_url: str | None = None) -> tuple[bool, str]:
    if not api_key:
        return False, "API key is required."
    provider = provider.lower()
    if provider not in SUPPORTED_PROVIDERS:
        return False, f"Unsupported provider: {provider}"
    if provider in {"zai", "minimax"}:
        probe_base = base_url or (ZAI_BASE_URL if provider == "zai" else MINIMAX_BASE_URL)
        probe_model = ZAI_MODELS[0] if provider == "zai" else MINIMAX_MODELS[0]
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    f"{probe_base.rstrip('/')}/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": probe_model,
                        "messages": [{"role": "user", "content": "ping"}],
                        "max_tokens": 1,
                    },
                )
                response.raise_for_status()
            return True, "API key is valid."
        except httpx.HTTPError as exc:
            return False, f"API request failed: {exc}"
    if provider == "epfl-rcp":
        probe_base = base_url or EPFL_RCP_BASE_URL
        probe_model = EPFL_RCP_MODELS[0]
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    f"{probe_base.rstrip('/')}/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": probe_model,
                        "messages": [{"role": "user", "content": "ping"}],
                        "max_tokens": 1,
                    },
                )
                response.raise_for_status()
            return True, "API key is valid."
        except httpx.HTTPError as exc:
            return False, f"API request failed: {exc}"
    try:
        await list_provider_models(provider, api_key, base_url)
        return True, "API key is valid."
    except httpx.HTTPError as exc:
        return False, f"API request failed: {exc}"
    except ProviderCatalogError as exc:
        return False, str(exc)
