from __future__ import annotations

from datetime import datetime, timezone
import json
import re
from pathlib import Path
from typing import Any

from app.services.free_llm.health_probe_service import load_active_routing, refresh_free_llm_health
from app.services.free_llm.http_client_service import post_chat_completion, extract_text
from app.services.free_llm.provider_registry_service import (
    LOG_DIR,
    load_task_policy,
    provider_by_name,
)

USAGE_LOG = LOG_DIR / "free_llm_usage.log"


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

    return rows


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
        def _route_sort_key(route: dict[str, Any]) -> tuple[int, float]:
            json_rank = 0 if route.get("json_ok") else 1
            try:
                score = float(route.get("score") or 0)
            except Exception:
                score = 0.0
            return (json_rank, -score)

        routes = sorted(routes, key=_route_sort_key)

    for route in routes:
        provider_name = str(route.get("provider") or "")
        model = str(route.get("model") or "")
        provider = provider_by_name(provider_name, include_premium=True)
        if not provider or not model:
            continue
        try:
            response = post_chat_completion(
                provider,
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=28,
                response_format={"type": "json_object"} if require_json else None,
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
            }
            _append_usage({
                "ts": datetime.now(timezone.utc).isoformat(),
                "task": task,
                "status": "success",
                "provider": provider_name,
                "model": model,
                "latency_ms": response.get("_latency_ms"),
                "cost_tier": route.get("cost_tier"),
            })
            return result
        except Exception as exc:
            errors.append({"provider": provider_name, "model": model, "error": str(exc)[:500]})
            _append_usage({
                "ts": datetime.now(timezone.utc).isoformat(),
                "task": task,
                "status": "failed",
                "provider": provider_name,
                "model": model,
                "error": str(exc)[:300],
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
