from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = PROJECT_ROOT / "config" / "free_llm_provider_registry.json"
TASK_POLICY_PATH = PROJECT_ROOT / "config" / "free_llm_task_policy.json"
ENV_PATH = PROJECT_ROOT / ".env"
FREE_LLM_ENV_PATH = PROJECT_ROOT / ".freeLLM"
RUN_DIR = PROJECT_ROOT / "run"
LOG_DIR = PROJECT_ROOT / "logs"


def _parse_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return out

    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key:
            out[key] = val
    return out


def env_map() -> dict[str, str]:
    out: dict[str, str] = {}
    out.update(_parse_env_file(ENV_PATH))
    out.update(_parse_env_file(FREE_LLM_ENV_PATH))
    out.update({k: v for k, v in os.environ.items() if isinstance(v, str)})
    return out


def get_secret(env_key: str, aliases: list[str] | None = None) -> str:
    envs = env_map()
    keys = [env_key] + list(aliases or [])
    for key in keys:
        val = str(envs.get(key, "") or "").strip()
        if val:
            return val
    return ""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def load_provider_registry() -> dict[str, Any]:
    return _load_json(CONFIG_PATH)


def load_task_policy() -> dict[str, Any]:
    return _load_json(TASK_POLICY_PATH)




def _parse_datetime_utc(value: str) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _resolve_datetime_setting(provider: dict[str, Any], direct_key: str, env_key: str, alias_key: str = "") -> datetime | None:
    envs = env_map()
    candidates: list[str] = []

    direct_val = provider.get(direct_key)
    if direct_val:
        candidates.append(str(direct_val))

    env_name = str(provider.get(env_key) or "").strip()
    if env_name:
        candidates.append(str(envs.get(env_name, "") or ""))

    aliases = provider.get(alias_key) if alias_key else None
    if isinstance(aliases, list):
        for item in aliases:
            key = str(item or "").strip()
            if key:
                candidates.append(str(envs.get(key, "") or ""))

    for item in candidates:
        dt = _parse_datetime_utc(item)
        if dt:
            return dt
    return None


def _provider_temporarily_available(provider: dict[str, Any]) -> bool:
    # FREE_LLM_PROVIDER_AVAILABILITY_GATE
    now = datetime.now(timezone.utc)

    disabled_until = _resolve_datetime_setting(
        provider,
        "disabled_until",
        "disabled_until_env",
        "disabled_until_alias_envs",
    )
    if disabled_until and now < disabled_until:
        return False

    trial_expires_at = _resolve_datetime_setting(
        provider,
        "trial_expires_at",
        "trial_expires_at_env",
        "trial_expires_at_alias_envs",
    )
    if trial_expires_at and now >= trial_expires_at:
        return False

    return True


def _with_env_overrides(provider: dict[str, Any]) -> dict[str, Any]:
    item = dict(provider)
    base_url_env = str(item.get("base_url_env") or "").strip()
    if base_url_env:
        val = str(env_map().get(base_url_env, "") or "").strip().rstrip("/")
        if val:
            item["base_url"] = val
    return item


def enabled_providers(*, include_premium: bool = False) -> list[dict[str, Any]]:
    cfg = load_provider_registry()
    if not cfg.get("enabled", True):
        return []
    providers = cfg.get("providers")
    if not isinstance(providers, list):
        return []
    out: list[dict[str, Any]] = []
    for provider in providers:
        if not isinstance(provider, dict):
            continue
        if not provider.get("enabled", True):
            continue
        if provider.get("premium_only") and not include_premium:
            continue
        if not _provider_temporarily_available(provider):
            continue  # FREE_LLM_PROVIDER_AVAILABILITY_GATE_CALL
        if not get_secret(str(provider.get("env_key", "")), provider.get("env_aliases") or []):
            continue
        out.append(_with_env_overrides(provider))
    return out


def provider_by_name(name: str, *, include_premium: bool = True) -> dict[str, Any] | None:
    for provider in enabled_providers(include_premium=include_premium):
        if provider.get("name") == name:
            return _with_env_overrides(provider)
    return None


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
