from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from src.models.provider_catalog import SUPPORTED_PROVIDERS
from src.security.api_key_store import delete_api_key, has_api_key, set_api_key

router = APIRouter(prefix="/api", tags=["providers"])


class ProviderKeyRequest(BaseModel):
    api_key: str = Field(..., description="API key for the provider")
    device_id: str | None = Field(default=None, description="Device identifier for key storage")


class ProviderKeyStatusResponse(BaseModel):
    provider: str = Field(..., description="Provider identifier")
    has_key: bool = Field(..., description="Whether a key is stored for this device")


def _resolve_device_id(device_id: str | None, header_device_id: str | None) -> str | None:
    if device_id:
        return device_id
    return header_device_id


def _normalize_provider(provider: str) -> str:
    normalized = provider.lower()
    if normalized not in SUPPORTED_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")
    return normalized


@router.put(
    "/providers/{provider}/key",
    response_model=ProviderKeyStatusResponse,
    summary="Store Provider API Key",
    description="Store or update a provider API key for this device.",
)
async def store_provider_key(
    provider: str,
    request: ProviderKeyRequest,
    device_id: str | None = Header(default=None, alias="x-device-id"),
) -> ProviderKeyStatusResponse:
    normalized = _normalize_provider(provider)
    resolved_device_id = _resolve_device_id(request.device_id, device_id)
    if not resolved_device_id:
        raise HTTPException(status_code=400, detail="Missing device_id.")
    try:
        set_api_key(resolved_device_id, normalized, request.api_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ProviderKeyStatusResponse(provider=normalized, has_key=True)


@router.get(
    "/providers/{provider}/key",
    response_model=ProviderKeyStatusResponse,
    summary="Get Provider API Key Status",
    description="Return whether a provider API key is stored for this device.",
)
async def get_provider_key_status(
    provider: str,
    device_id: str | None = Header(default=None, alias="x-device-id"),
) -> ProviderKeyStatusResponse:
    normalized = _normalize_provider(provider)
    if not device_id:
        raise HTTPException(status_code=400, detail="Missing device_id.")
    return ProviderKeyStatusResponse(
        provider=normalized,
        has_key=has_api_key(device_id, normalized),
    )


@router.delete(
    "/providers/{provider}/key",
    response_model=ProviderKeyStatusResponse,
    summary="Delete Provider API Key",
    description="Delete a provider API key for this device.",
)
async def delete_provider_key(
    provider: str,
    device_id: str | None = Header(default=None, alias="x-device-id"),
) -> ProviderKeyStatusResponse:
    normalized = _normalize_provider(provider)
    if not device_id:
        raise HTTPException(status_code=400, detail="Missing device_id.")
    delete_api_key(device_id, normalized)
    return ProviderKeyStatusResponse(provider=normalized, has_key=False)
