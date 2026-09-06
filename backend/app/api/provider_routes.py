"""Provider/settings/models endpoints (C4) — thin HTTP layer.

Split out of ``routes.py`` to keep that file focused on task lifecycle
endpoints. Auth, validation, and HTTP mapping only; provider config assembly
lives in ``app.pipeline.context``.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends

from app.auth import TokenData, get_current_user
from app.config import PROVIDER_PRESETS
from app.crypto import decrypt_api_key, encrypt_api_key
from app.db import get_all_provider_configs, save_provider_config
from app.schemas import (
    ModelItem,
    ModelsRequest,
    ModelsResponse,
    ProviderConfigResponse,
    ProviderPreset,
    ProvidersResponse,
    SettingsRequest,
    SettingsResponse,
)

CurrentUser = Annotated[TokenData, Depends(get_current_user)]

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/models", response_model=ModelsResponse)
async def list_models(req: ModelsRequest, user: CurrentUser):
    """Proxy /v1/models call to avoid exposing API key to the frontend."""
    try:
        from openai import AsyncClient

        async with AsyncClient(api_key=req.api_key, base_url=req.api_base) as client:
            page = await client.models.list()
            models = [
                ModelItem(id=m.id, object=m.object, created=m.created, owned_by=m.owned_by)
                for m in page.data
            ]
            return ModelsResponse(models=models)
    except Exception as e:
        logger.warning(f"Failed to list models for {req.api_base}: {e}")
        return ModelsResponse(models=[], error="MODELS_FETCH_FAILED")


@router.get("/providers", response_model=ProvidersResponse)
async def get_providers(user: CurrentUser):
    """Return preset provider/model lists for ASR and LLM."""
    return ProvidersResponse(
        asr=[ProviderPreset(**p) for p in PROVIDER_PRESETS["asr"]],
        llm=[ProviderPreset(**p) for p in PROVIDER_PRESETS["llm"]],
    )


@router.get("/settings", response_model=SettingsResponse)
async def get_settings(user: CurrentUser):
    """Return current user provider settings (API keys masked)."""
    configs = await get_all_provider_configs(user.user_id)
    return SettingsResponse(**_masked_settings(configs))


@router.put("/settings", response_model=SettingsResponse)
async def update_settings(req: SettingsRequest, user: CurrentUser):
    """Save user provider settings (API keys encrypted)."""
    existing_configs = await get_all_provider_configs(user.user_id)

    for category in ("asr", "llm"):
        cfg = getattr(req, category)
        if cfg is None:
            continue

        # If user didn't provide a new key, keep the existing one
        if cfg.api_key:
            api_key_encrypted = encrypt_api_key(cfg.api_key)
        else:
            existing = existing_configs.get(category, {})
            api_key_encrypted = existing.get("api_key_encrypted", "")

        await save_provider_config(
            user_id=user.user_id,
            category=category,
            provider=cfg.provider,
            model=cfg.model,
            api_key_encrypted=api_key_encrypted,
            api_base=cfg.api_base,
        )

    # Return updated settings (re-read to get masked keys)
    configs = await get_all_provider_configs(user.user_id)
    return SettingsResponse(**_masked_settings(configs))


def _mask_api_key(key: str) -> str:
    """Return masked API key showing only last 4 characters."""
    if len(key) <= 4:
        return "****"
    return "*" * (len(key) - 4) + key[-4:]


def _masked_settings(configs: dict) -> dict:
    """Build the settings response body with masked API keys."""
    result: dict = {}
    for category in ("asr", "llm"):
        cfg = configs.get(category)
        if cfg and cfg.get("provider"):
            api_key_masked = ""
            if cfg.get("api_key_encrypted"):
                try:
                    decrypted = decrypt_api_key(cfg["api_key_encrypted"])
                    api_key_masked = _mask_api_key(decrypted)
                except Exception:
                    api_key_masked = "****"
            result[category] = ProviderConfigResponse(
                provider=cfg["provider"],
                model=cfg["model"],
                api_key_masked=api_key_masked,
                api_base=cfg["api_base"],
            )
    return result
