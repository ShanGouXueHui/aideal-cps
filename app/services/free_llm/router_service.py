from __future__ import annotations

from datetime import datetime, timezone, timedelta
import json
import re
from pathlib import Path
from typing import Any

from app.services.free_llm.health_probe_service import load_active_routing, refresh_free_llm_health
from app.services.free_llm.http_client_service import post_chat_completion, extract_text
from app.services.free_llm.provider_registry_service import (
    LOG_DIR,
    RUN_DIR,
    load_task_policy,
    provider_by_name,
    write_json,
)

USAGE_LOG = LOG_DIR / "free_llm_usage.log"

ROUTE_STATE_PATH = RUN_DIR / "free_llm_route_runtime_state.json"
ROUTE_FAILURE_THRESHOLD = 2
ROUTE_COOLDOWN_SECONDS = 1800


def _route_key(task: str, provider: str, model: str) -> str:
    return f"{task}::{provider}::{model}"


def _load_route_state() -> dict[str, Any]:
    try:
        data = json.loads(ROUTE_STATE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_route_state(state: dict[str, Any]) -> None:
    try:
        write_json(ROUTE_STATE_PATH, state)
    except Exception:
        pass


def _parse_state_time(value: Any) -> datetime | None:
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


def _route_is_quarantined(task: str, route: dict[str, Any]) -> bool:
    # FREE_LLM_RUNTIME_QUARANTINE_GATE
    provider = str(route.get("provider") or "")
    model = str(route.get("model") or "")
    state = _load_route_state()
    item = state.get(_route_key(task, provider, model))
    if not isinstance(item, dict):
        return False
    disabled_until = _parse_state_time(item.get("disabled_until"))
    return bool(disabled_until and datetime.now(timezone.utc) < disabled_until)


def _record_route_success(task: str, provider: str, model: str) -> None:
    state = _load_route_state()
    key = _route_key(task, provider, model)
    state[key] = {
        "consecutive_failures": 0,
        "last_success_at": datetime.now(timezone.utc).isoformat(),
    }
    _save_route_state(state)


def _record_route_failure(task: str, provider: str, model: str, error: str = "") -> None:
    state = _load_route_state()
    key = _route_key(task, provider, model)
    item = state.get(key)
    if not isinstance(item, dict):
        item = {}
    failures = int(item.get("consecutive_failures") or 0) + 1
    item["consecutive_failures"] = failures
    item["last_failure_at"] = datetime.now(timezone.utc).isoformat()
    item["last_error"] = str(error or "")[:240]
    if failures >= ROUTE_FAILURE_THRESHOLD:
        item["disabled_until"] = (datetime.now(timezone.utc) + timedelta(seconds=ROUTE_COOLDOWN_SECONDS)).isoformat()
    state[key] = item
    _save_route_state(state)



def _append_usage(row: dict[str, Any]) -> None:
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with USAGE_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _extract_json(text: str) -> dict[str, Any] | list[Any] | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        pass

    match = re.search(r"```(?:json)?\\s*(.*?)```", raw, flags=re.S | re.I)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except Exception:
            pass

    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(raw[start:end + 1])
        except Exception:
            pass

    start = raw.find("[")
    end = raw.rfind("]")
    if start >= 0 and end > start:
        try:
            return json.loads(raw[start:end + 1])
        except Exception:
            pass
    return None


def _task_cfg(task: str) -> dict[str, Any]:
    policy = load_task_policy()
    tasks = policy.get("tasks") if isinstance(policy.get("tasks"), dict) else {}
    cfg = tasks.get(task) if isinstance(tasks.get(task), dict) else None
    if cfg:
        return cfg
    default_task = str(policy.get("default_task") or "fallback_chat")
    return tasks.get(default_task, {}) if isinstance(tasks.get(default_task), dict) else {}


def _routes_for_task(task: str, *, allow_premium: bool = False) -> list[dict[str, Any]]:
    active = load_active_routing()
    routes = active.get("routes") if isinstance(active.get("routes"), dict) else {}
    rows = routes.get(task) if isinstance(routes.get(task), list) else []

    if not rows:
        try:
            active = refresh_free_llm_health()
            routes = active.get("routes") if isinstance(active.get("routes"), dict) else {}
            rows = routes.get(task) if isinstance(routes.get(task), list) else []
        except Exception:
            rows = []

    if allow_premium:
        premium = [
            {"provider": "qwen_premium", "model": "qwen-plus", "score": -1, "cost_tier": "paid_fallback"},
            {"provider": "qwen_premium", "model": "qwen-max", "score": -2, "cost_tier": "paid_fallback"},
        ]
        rows = list(rows) + premium

    rows = [r for r in rows if not _route_is_quarantined(task, r)]  # FREE_LLM_RUNTIME_QUARANTINE_ROUTE_FILTER
    return rows


def _thinking_extra_payload(
    *,
    task: str,
    provider_name: str,
    model: str,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    thinking = cfg.get("thinking") if isinstance(cfg.get("thinking"), dict) else {}
    if not thinking or not thinking.get("enabled"):
        return {}

    providers = thinking.get("providers")
    if isinstance(providers, list) and providers:
        allowed = {str(x).strip() for x in providers if str(x).strip()}
        if provider_name not in allowed:
            return {}

    # Current safe implementation: only OpenRouter gets the standardized reasoning object.
    # Other OpenAI-compatible providers often have provider-specific switches; keep them off
    # until individually verified, otherwise one unsupported parameter can degrade fallback quality.
    if provider_name != "openrouter":
        return {}

    reasoning = thinking.get("reasoning")
    if not isinstance(reasoning, dict) or not reasoning:
        reasoning = {"effort": str(thinking.get("effort") or "medium"), "exclude": True}

    payload = {"reasoning": dict(reasoning)}
    return payload  # FREE_LLM_THINKING_PAYLOAD_GATE


def complete_free_llm(
    *,
    task: str,
    messages: list[dict[str, str]],
    user_gmv_rmb: float = 0.0,
    allow_premium: bool = False,
) -> dict[str, Any]:
    cfg = _task_cfg(task)
    premium_allowed = bool(allow_premium)
    if cfg.get("premium_fallback_enabled"):
        try:
            premium_allowed = premium_allowed or float(user_gmv_rmb or 0) >= float(cfg.get("premium_min_gmv_rmb", 1000) or 1000)
        except Exception:
            pass

    require_json = bool(cfg.get("require_json"))
    max_tokens = int(cfg.get("max_tokens", 600) or 600)
    temperature = float(cfg.get("temperature", 0.1) or 0.1)

    errors: list[dict[str, Any]] = []
    routes = _routes_for_task(task, allow_premium=premium_allowed)

    # JSON 任务优先使用已探活证明 json_ok 的模型，避免先打到“能回复但不稳定 JSON”的模型。
    if require_json:
        thinking_cfg = cfg.get("thinking") if isinstance(cfg.get("thinking"), dict) else {}
        thinking_provider_set = set()
        if thinking_cfg.get("enabled") and isinstance(thinking_cfg.get("providers"), list):
            thinking_provider_set = {str(x).strip() for x in thinking_cfg.get("providers") if str(x).strip()}

        def _route_sort_key(route: dict[str, Any]) -> tuple[int, int, float]:
            json_rank = 0 if route.get("json_ok") else 1
            provider_name_for_sort = str(route.get("provider") or "")
            # 后台 thinking 任务：在 json_ok 的前提下，优先试支持 thinking 的 provider；
            # 如果失败，原有自动切换机制会继续打下一个模型。
            thinking_rank = 0 if provider_name_for_sort in thinking_provider_set and route.get("json_ok") else 1
            try:
                score = float(route.get("score") or 0)
            except Exception:
                score = 0.0
            return (json_rank, thinking_rank, -score)

        routes = sorted(routes, key=_route_sort_key)

    for route in routes:
        provider_name = str(route.get("provider") or "")
        model = str(route.get("model") or "")
        provider = provider_by_name(provider_name, include_premium=True)
        if not provider or not model:
            continue
        extra_payload: dict[str, Any] = {}  # FREE_LLM_RUNTIME_QUARANTINE_EXTRA_PAYLOAD_INIT
        try:
            extra_payload = _thinking_extra_payload(
                task=task,
                provider_name=provider_name,
                model=model,
                cfg=cfg,
            )
            response = post_chat_completion(
                provider,
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=28,
                response_format={"type": "json_object"} if require_json else None,
                extra_payload=extra_payload,
            )
            text = extract_text(response)
            if require_json and _extract_json(text) is None:
                raise ValueError("model returned non-json response")
            result = {
                "status": "success",
                "provider": provider_name,
                "model": model,
                "text": text,
                "latency_ms": response.get("_latency_ms"),
                "cost_tier": route.get("cost_tier"),
                "thinking_enabled": bool(extra_payload),
            }
            _record_route_success(task, provider_name, model)  # FREE_LLM_RUNTIME_QUARANTINE_SUCCESS
            _append_usage({
                "ts": datetime.now(timezone.utc).isoformat(),
                "task": task,
                "status": "success",
                "provider": provider_name,
                "model": model,
                "latency_ms": response.get("_latency_ms"),
                "cost_tier": route.get("cost_tier"),
                "thinking_enabled": bool(extra_payload),
            })
            return result
        except Exception as exc:
            errors.append({"provider": provider_name, "model": model, "error": str(exc)[:500]})
            _record_route_failure(task, provider_name, model, str(exc))  # FREE_LLM_RUNTIME_QUARANTINE_FAILURE
            _append_usage({
                "ts": datetime.now(timezone.utc).isoformat(),
                "task": task,
                "status": "failed",
                "provider": provider_name,
                "model": model,
                "error": str(exc)[:300],
                "thinking_enabled": bool(extra_payload),
            })
            continue

    return {
        "status": "failed",
        "error": "no_available_model",
        "errors": errors[-8:],
    }


def complete_free_llm_json(
    *,
    task: str,
    system_prompt: str,
    user_prompt: str,
    user_gmv_rmb: float = 0.0,
    allow_premium: bool = False,
) -> dict[str, Any]:
    result = complete_free_llm(
        task=task,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        user_gmv_rmb=user_gmv_rmb,
        allow_premium=allow_premium,
    )
    if result.get("status") != "success":
        return result

    data = _extract_json(str(result.get("text") or ""))
    if data is None:
        result["status"] = "failed"
        result["error"] = "json_parse_failed"
        return result

    result["json"] = data
    return result
