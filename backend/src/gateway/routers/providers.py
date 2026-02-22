from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from src.models.provider_catalog import ProviderCatalogError, ProviderModelInfo, list_provider_models, validate_provider_key
from src.security.api_key_store import get_api_key

router = APIRouter(prefix="/api", tags=["providers"])


class ProviderModelsRequest(BaseModel):
    api_key: str | None = Field(default=None, description="API key for the provider")
    base_url: str | None = Field(default=None, description="Override base URL for provider calls")
    device_id: str | None = Field(default=None, description="Device identifier for stored keys")


class ProviderModelsResponse(BaseModel):
    provider: str = Field(..., description="Provider identifier")
    models: list[ProviderModelInfo] = Field(default_factory=list, description="Available models for the provider")


class ProviderValidationResponse(BaseModel):
    provider: str = Field(..., description="Provider identifier")
    valid: bool = Field(..., description="Whether the API key is valid")
    message: str = Field(..., description="Validation message")


@router.post(
    "/providers/{provider}/models",
    response_model=ProviderModelsResponse,
    summary="List Provider Models",
    description="Fetch the latest available models from a specific provider.",
)
async def get_provider_models(
    provider: str,
    request: ProviderModelsRequest,
    device_id: str | None = Header(default=None, alias="x-device-id"),
) -> ProviderModelsResponse:
    try:
        normalized = provider.lower()
        resolved_device_id = request.device_id or device_id
        api_key = request.api_key
        if not api_key and resolved_device_id:
            api_key = get_api_key(resolved_device_id, normalized)
        models = await list_provider_models(normalized, api_key, request.base_url)
        return ProviderModelsResponse(provider=normalized, models=models)
    except ProviderCatalogError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to list models for {provider}: {exc}") from exc


@router.post(
    "/providers/{provider}/validate",
    response_model=ProviderValidationResponse,
    summary="Validate Provider API Key",
    description="Validate an API key for a specific provider.",
)
async def validate_provider(
    provider: str,
    request: ProviderModelsRequest,
    device_id: str | None = Header(default=None, alias="x-device-id"),
) -> ProviderValidationResponse:
    normalized = provider.lower()
    resolved_device_id = request.device_id or device_id
    api_key = request.api_key
    if not api_key and resolved_device_id:
        api_key = get_api_key(resolved_device_id, normalized)
    valid, message = await validate_provider_key(normalized, api_key, request.base_url)
    return ProviderValidationResponse(provider=normalized, valid=valid, message=message)
