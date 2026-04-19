from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import re

from app.services.free_llm.http_client_service import get_json
from app.services.free_llm.provider_registry_service import (
    RUN_DIR,
    enabled_providers,
    load_provider_registry,
    write_json,
)

CATALOG_PATH = RUN_DIR / "free_llm_model_catalog.json"

BAD_MODEL_PATTERNS = [
    "embed", "embedding", "rerank", "reward", "tts", "audio", "whisper",
    "image", "vision", "vl", "sdxl", "stable-diffusion", "moderation",
]


def _is_zero_price(value: Any) -> bool:
    try:
        return float(value or 0) == 0
    except Exception:
        return False


def _model_is_free(model_id: str, raw: dict[str, Any] | None = None) -> bool:
    mid = str(model_id or "").lower()
    if ":free" in mid or mid.endswith("/free") or "free" in mid:
        return True
    raw = raw or {}
    pricing = raw.get("pricing")
    if isinstance(pricing, dict):
        values = [pricing.get("prompt"), pricing.get("completion"), pricing.get("request")]
        if values and all(_is_zero_price(x) for x in values if x is not None):
            return True
    return False


def _reject_model(model_id: str) -> bool:
    mid = str(model_id or "").lower()
    if not mid or len(mid) > 180:
        return True
    return any(pat in mid for pat in BAD_MODEL_PATTERNS)


def _score_model(provider: dict[str, Any], model_id: str, raw: dict[str, Any] | None = None) -> float:
    mid = str(model_id or "").lower()
    score = 20.0

    if _model_is_free(model_id, raw):
        score += 35
    if any(x in mid for x in ["qwen", "deepseek", "glm", "gemini", "llama", "mistral", "nemotron"]):
        score += 20
    if any(x in mid for x in ["flash", "turbo", "lite", "nano", "mini", "8b", "7b", "4b"]):
        score += 10
    if any(x in mid for x in ["instruct", "chat"]):
        score += 8
    if any(x in mid for x in ["70b", "72b", "120b", "405b"]):
        score -= 8
    if provider.get("premium_only"):
        score -= 100
    if provider.get("name") in {"gemini", "openrouter", "zhipu", "bailian"}:
        score += 6

    return round(score, 4)


def _extract_models(response: dict[str, Any]) -> list[dict[str, Any]]:
    data = response.get("data")
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    models = response.get("models")
    if isinstance(models, list):
        return [x for x in models if isinstance(x, dict)]
    return []


def _candidate_from(provider: dict[str, Any], model_id: str, *, source: str, raw: dict[str, Any] | None = None) -> dict[str, Any] | None:
    if _reject_model(model_id):
        return None
    free_only = bool(provider.get("free_only"))
    if free_only and not _model_is_free(model_id, raw):
        return None

    return {
        "provider": provider.get("name"),
        "model": model_id,
        "source": source,
        "score": _score_model(provider, model_id, raw),
        "cost_tier": provider.get("cost_tier", "unknown"),
        "is_free": _model_is_free(model_id, raw),
        "base_url": provider.get("base_url"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def refresh_free_llm_model_catalog() -> dict[str, Any]:
    cfg = load_provider_registry()
    max_per_provider = int(cfg.get("max_models_per_provider", 40) or 40)

    all_candidates: list[dict[str, Any]] = []
    provider_summaries: list[dict[str, Any]] = []

    for provider in enabled_providers(include_premium=True):
        seen: set[str] = set()
        provider_candidates: list[dict[str, Any]] = []
        provider_name = str(provider.get("name") or "")

        for model_id in provider.get("seed_models") or []:
            mid = str(model_id).strip()
            if not mid or mid in seen:
                continue
            seen.add(mid)
            candidate = _candidate_from(provider, mid, source="seed")
            if candidate:
                provider_candidates.append(candidate)

        discover_error = ""
        discovered_count = 0
        if provider.get("discover_models", True):
            try:
                response = get_json(provider, str(provider.get("models_path") or "/models"), timeout=18)
                for raw in _extract_models(response):
                    mid = str(raw.get("id") or raw.get("name") or "").strip()
                    if not mid or mid in seen:
                        continue
                    seen.add(mid)
                    discovered_count += 1
                    candidate = _candidate_from(provider, mid, source="discovered", raw=raw)
                    if candidate:
                        provider_candidates.append(candidate)
            except Exception as exc:
                discover_error = str(exc)[:500]

        provider_candidates = sorted(provider_candidates, key=lambda x: float(x.get("score", 0)), reverse=True)[:max_per_provider]
        all_candidates.extend(provider_candidates)
        provider_summaries.append(
            {
                "provider": provider_name,
                "enabled": True,
                "seed_count": len(provider.get("seed_models") or []),
                "discovered_count": discovered_count,
                "candidate_count": len(provider_candidates),
                "discover_error": discover_error,
            }
        )

    payload = {
        "status": "success",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "strategy": "discover_filter_score_candidates_then_health_probe",
        "provider_summaries": provider_summaries,
        "candidate_count": len(all_candidates),
        "candidates": sorted(all_candidates, key=lambda x: float(x.get("score", 0)), reverse=True),
    }
    write_json(CATALOG_PATH, payload)
    return payload


def load_model_catalog() -> dict[str, Any]:
    try:
        return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
