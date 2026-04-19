from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import json
import os
import time
from typing import Any

from app.services.free_llm.http_client_service import post_chat_completion, extract_text
from app.services.free_llm.model_catalog_refresh_service import load_model_catalog, refresh_free_llm_model_catalog
from app.services.free_llm.provider_registry_service import (
    RUN_DIR,
    load_provider_registry,
    load_task_policy,
    provider_by_name,
    write_json,
)

HEALTH_PATH = RUN_DIR / "free_llm_health_snapshot.json"
ACTIVE_ROUTING_PATH = RUN_DIR / "free_llm_active_routing.json"


def _to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(value)
    except Exception:
        return default


def _looks_json(text: str) -> bool:
    stripped = str(text or "").strip()
    if not stripped:
        return False
    if "{" in stripped and "}" in stripped:
        return True
    if "[" in stripped and "]" in stripped:
        return True
    return False


def _task_score(task_cfg: dict[str, Any], candidate: dict[str, Any], health: dict[str, Any]) -> float:
    score = float(candidate.get("score", 0) or 0)

    if health.get("status") == "success":
        score += 50
    if health.get("json_ok"):
        score += 15

    latency = int(health.get("latency_ms", 999999) or 999999)
    if latency < 1200:
        score += 16
    elif latency < 2500:
        score += 12
    elif latency < 7000:
        score += 6
    elif latency > 18000:
        score -= 12

    preferred = task_cfg.get("preferred_providers") or []
    if candidate.get("provider") in preferred:
        score += max(0, 18 - preferred.index(candidate.get("provider")) * 2)

    cost_tier = candidate.get("cost_tier")
    if cost_tier == "free":
        score += 8
    elif cost_tier == "free_or_trial":
        score += 3
    elif cost_tier == "paid_fallback":
        score -= 100

    return round(score, 4)


def _default_probe_profiles() -> dict[str, dict[str, Any]]:
    return {
        "quick": {
            "max_models_per_provider": 3,
            "timeout_seconds": 8,
            "success_target": 6,
            "total_timeout_seconds": 90,
        },
        "background": {
            "max_models_per_provider": 6,
            "timeout_seconds": 10,
            "success_target": 12,
            "total_timeout_seconds": 420,
        },
        "full": {
            "max_models_per_provider": 40,
            "timeout_seconds": 15,
            "success_target": None,
            "total_timeout_seconds": 1800,
        },
    }


def _probe_settings(registry: dict[str, Any], mode: str) -> dict[str, Any]:
    mode = str(mode or "quick").strip() or "quick"
    defaults = _default_probe_profiles()
    profiles = registry.get("health_probe_profiles")
    if not isinstance(profiles, dict):
        profiles = {}

    cfg = dict(defaults.get(mode, defaults["quick"]))
    if isinstance(profiles.get(mode), dict):
        cfg.update(profiles[mode])

    # Backward-compatible top-level overrides.
    if mode == "quick":
        cfg["max_models_per_provider"] = _to_int(
            registry.get("health_probe_max_models_per_provider"),
            _to_int(cfg.get("max_models_per_provider"), 3),
        )
        cfg["timeout_seconds"] = _to_int(
            registry.get("default_timeout_seconds"),
            _to_int(cfg.get("timeout_seconds"), 8),
        )

    cfg["mode"] = mode
    cfg["max_models_per_provider"] = max(1, _to_int(cfg.get("max_models_per_provider"), 3))
    cfg["timeout_seconds"] = max(3, _to_int(cfg.get("timeout_seconds"), 8))

    success_target = cfg.get("success_target")
    cfg["success_target"] = None if success_target in (None, "", 0, "0") else max(1, _to_int(success_target, 0))

    total_timeout = cfg.get("total_timeout_seconds")
    cfg["total_timeout_seconds"] = None if total_timeout in (None, "", 0, "0") else max(30, _to_int(total_timeout, 90))
    return cfg


def _candidate_sort_key(candidate: dict[str, Any]) -> tuple[float, str]:
    return (float(candidate.get("score", 0) or 0), str(candidate.get("model") or ""))


def refresh_free_llm_health(
    *,
    mode: str | None = None,
    max_models_per_provider: int | None = None,
    timeout_seconds: int | None = None,
    success_target: int | None = None,
    total_timeout_seconds: int | None = None,
) -> dict[str, Any]:
    registry = load_provider_registry()
    selected_mode = mode or os.getenv("FREE_LLM_PROBE_MODE") or "quick"
    settings = _probe_settings(registry, selected_mode)

    if max_models_per_provider is not None:
        settings["max_models_per_provider"] = max(1, int(max_models_per_provider))
    if timeout_seconds is not None:
        settings["timeout_seconds"] = max(3, int(timeout_seconds))
    if success_target is not None:
        settings["success_target"] = max(1, int(success_target))
    if total_timeout_seconds is not None:
        settings["total_timeout_seconds"] = max(30, int(total_timeout_seconds))

    max_per_provider = int(settings["max_models_per_provider"])
    timeout = int(settings["timeout_seconds"])
    target = settings.get("success_target")
    total_timeout = settings.get("total_timeout_seconds")

    started_monotonic = time.monotonic()
    deadline = (started_monotonic + int(total_timeout)) if total_timeout else None

    catalog = load_model_catalog()
    if not catalog.get("candidates"):
        catalog = refresh_free_llm_model_catalog()

    candidates = catalog.get("candidates") if isinstance(catalog.get("candidates"), list) else []
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for c in candidates:
        if isinstance(c, dict):
            grouped[str(c.get("provider") or "")].append(c)

    preferred_order = [
        "openrouter",
        "nvidia",
        "bailian",
        "gemini",
        "zhipu",
        "tencent_hunyuan",
        "huggingface",
        "qwen_premium",
    ]

    provider_names = sorted(
        grouped.keys(),
        key=lambda name: (preferred_order.index(name) if name in preferred_order else 999, name),
    )

    probe_results: list[dict[str, Any]] = []
    stopped_reason = ""

    for provider_name in provider_names:
        if deadline and time.monotonic() >= deadline:
            stopped_reason = "total_timeout_reached_before_provider"
            break

        provider = provider_by_name(provider_name, include_premium=True)
        if not provider:
            continue

        rows = sorted(grouped[provider_name], key=_candidate_sort_key, reverse=True)[:max_per_provider]
        for candidate in rows:
            if deadline and time.monotonic() >= deadline:
                stopped_reason = "total_timeout_reached"
                break

            if target and sum(1 for x in probe_results if x.get("status") == "success") >= int(target):
                stopped_reason = "success_target_reached"
                break

            model = str(candidate.get("model") or "")
            result = {
                "provider": provider_name,
                "model": model,
                "status": "failed",
                "latency_ms": None,
                "json_ok": False,
                "error": "",
                "candidate_score": candidate.get("score", 0),
                "cost_tier": candidate.get("cost_tier"),
            }

            try:
                response = post_chat_completion(
                    provider,
                    model=model,
                    messages=[
                        {"role": "system", "content": "你是接口探活器。只输出 JSON，不要解释。"},
                        {"role": "user", "content": "请严格输出：{\"ok\":true,\"label\":\"free_llm\"}"},
                    ],
                    temperature=0.0,
                    max_tokens=80,
                    timeout=timeout,
                )
                text = extract_text(response)
                result["latency_ms"] = response.get("_latency_ms")
                result["json_ok"] = _looks_json(text)
                result["status"] = "success" if text else "failed"
                result["text_preview"] = text[:120]
            except Exception as exc:
                result["error"] = str(exc)[:600]

            probe_results.append(result)

        if stopped_reason:
            break

    task_policy = load_task_policy()
    tasks = task_policy.get("tasks") if isinstance(task_policy.get("tasks"), dict) else {}
    routes: dict[str, list[dict[str, Any]]] = {}

    candidate_index = {
        (str(c.get("provider") or ""), str(c.get("model") or "")): c
        for c in candidates
        if isinstance(c, dict)
    }

    for task_name, task_cfg in tasks.items():
        task_routes: list[dict[str, Any]] = []
        for result in probe_results:
            if result.get("status") != "success":
                continue

            candidate = candidate_index.get((str(result.get("provider") or ""), str(result.get("model") or "")), {})
            task_routes.append(
                {
                    "provider": result.get("provider"),
                    "model": result.get("model"),
                    "score": _task_score(task_cfg if isinstance(task_cfg, dict) else {}, candidate, result),
                    "latency_ms": result.get("latency_ms"),
                    "json_ok": bool(result.get("json_ok")),
                    "cost_tier": result.get("cost_tier"),
                }
            )

        routes[task_name] = sorted(task_routes, key=lambda x: float(x.get("score", 0)), reverse=True)

    success_count = sum(1 for x in probe_results if x.get("status") == "success")
    elapsed_ms = int((time.monotonic() - started_monotonic) * 1000)

    provider_summary: dict[str, dict[str, Any]] = {}
    for row in probe_results:
        provider = str(row.get("provider") or "")
        item = provider_summary.setdefault(provider, {"probe_count": 0, "success_count": 0, "best_latency_ms": None})
        item["probe_count"] += 1
        if row.get("status") == "success":
            item["success_count"] += 1
            latency = row.get("latency_ms")
            if isinstance(latency, int):
                if item["best_latency_ms"] is None or latency < item["best_latency_ms"]:
                    item["best_latency_ms"] = latency

    payload = {
        "status": "success" if success_count > 0 else "failed",
        "mode": settings.get("mode"),
        "settings": settings,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_ms": elapsed_ms,
        "stopped_reason": stopped_reason,
        "probe_count": len(probe_results),
        "success_count": success_count,
        "provider_summary": provider_summary,
        "probe_results": probe_results,
        "routes": routes,
    }

    write_json(HEALTH_PATH, payload)
    if success_count > 0:
        write_json(ACTIVE_ROUTING_PATH, payload)

    return payload


def load_active_routing() -> dict[str, Any]:
    try:
        return json.loads(ACTIVE_ROUTING_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
