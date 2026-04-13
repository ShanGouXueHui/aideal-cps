from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.core.free_model_pool_config import free_model_pool_settings, state_file_path


UTC = timezone.utc


def now_utc() -> datetime:
    return datetime.now(UTC)


def iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


@dataclass
class ProviderRecord:
    provider_id: str
    model_name: str
    base_url: str
    api_key_env: str
    enabled: bool = True
    priority: int = 100
    consecutive_failures: int = 0
    total_success: int = 0
    total_failures: int = 0
    avg_latency_ms: float | None = None
    last_error: str | None = None
    disabled_until: str | None = None
    last_checked_at: str | None = None

    def is_available(self, now: datetime) -> bool:
        if not self.enabled:
            return False
        cooldown = parse_dt(self.disabled_until)
        if cooldown and cooldown > now:
            return False
        return True

    def mark_success(self, latency_ms: float | None = None) -> None:
        self.consecutive_failures = 0
        self.total_success += 1
        self.last_error = None
        self.disabled_until = None
        self.last_checked_at = iso(now_utc())
        if latency_ms is not None:
            if self.avg_latency_ms is None:
                self.avg_latency_ms = latency_ms
            else:
                self.avg_latency_ms = round((self.avg_latency_ms * 0.7) + (latency_ms * 0.3), 2)

    def mark_failure(self, error: str) -> None:
        self.consecutive_failures += 1
        self.total_failures += 1
        self.last_error = error
        self.last_checked_at = iso(now_utc())
        if self.consecutive_failures >= free_model_pool_settings.FREE_MODEL_POOL_FAIL_THRESHOLD:
            disabled_until = now_utc() + timedelta(seconds=free_model_pool_settings.FREE_MODEL_POOL_COOLDOWN_SECONDS)
            self.disabled_until = iso(disabled_until)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProviderRecord":
        return cls(**data)


class FreeModelPool:
    def __init__(self, state_path: Path | None = None) -> None:
        self.state_path = state_path or state_file_path()
        self.providers: list[ProviderRecord] = []

    def ensure_parent(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> None:
        if not self.state_path.exists():
            self.providers = []
            return
        raw = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.providers = [ProviderRecord.from_dict(item) for item in raw.get("providers", [])]

    def save(self) -> None:
        self.ensure_parent()
        payload = {"providers": [asdict(p) for p in self.providers]}
        self.state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def seed_defaults(self, providers: list[dict[str, Any]]) -> None:
        if self.providers:
            return
        self.providers = [ProviderRecord(**item) for item in providers]
        self.save()

    def upsert(self, provider: ProviderRecord) -> None:
        for idx, item in enumerate(self.providers):
            if item.provider_id == provider.provider_id:
                self.providers[idx] = provider
                self.save()
                return
        self.providers.append(provider)
        self.save()

    def list_available(self) -> list[ProviderRecord]:
        current = now_utc()
        candidates = [p for p in self.providers if p.is_available(current)]
        return sorted(
            candidates,
            key=lambda p: (
                -p.priority,
                p.consecutive_failures,
                p.avg_latency_ms if p.avg_latency_ms is not None else 999999,
                p.total_failures,
            ),
        )

    def pick_best(self) -> ProviderRecord | None:
        available = self.list_available()
        return available[0] if available else None

    def mark_success(self, provider_id: str, latency_ms: float | None = None) -> None:
        for item in self.providers:
            if item.provider_id == provider_id:
                item.mark_success(latency_ms=latency_ms)
                self.save()
                return
        raise ValueError(f"provider not found: {provider_id}")

    def mark_failure(self, provider_id: str, error: str) -> None:
        for item in self.providers:
            if item.provider_id == provider_id:
                item.mark_failure(error=error)
                self.save()
                return
        raise ValueError(f"provider not found: {provider_id}")

    def export_summary(self) -> list[dict[str, Any]]:
        return [asdict(p) for p in self.providers]


def build_default_free_model_pool() -> FreeModelPool:
    pool = FreeModelPool()
    pool.load()
    pool.seed_defaults(
        [
            {
                "provider_id": "openrouter_qwen_free",
                "model_name": "qwen/qwen3-32b:free",
                "base_url": "https://openrouter.ai/api/v1",
                "api_key_env": "OPENROUTER_API_KEY",
                "priority": 100,
            },
            {
                "provider_id": "openrouter_deepseek_free",
                "model_name": "deepseek/deepseek-chat-v3:free",
                "base_url": "https://openrouter.ai/api/v1",
                "api_key_env": "OPENROUTER_API_KEY",
                "priority": 90,
            },
            {
                "provider_id": "openrouter_minimax_free",
                "model_name": "minimax/minimax-m1:free",
                "base_url": "https://openrouter.ai/api/v1",
                "api_key_env": "OPENROUTER_API_KEY",
                "priority": 80,
            },
        ]
    )
    return pool
