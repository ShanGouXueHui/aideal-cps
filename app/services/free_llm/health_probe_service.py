from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import json
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
    if latency < 2500:
        score += 12
    elif latency < 7000:
        score += 6
    elif latency > 18000:
        score -= 10
    preferred = task_cfg.get("preferred_providers") or []
    if candidate.get("provider") in preferred:
        score += max(0, 18 - preferred.index(candidate.get("provider")) * 2)
    if candidate.get("cost_tier") == "paid_fallback":
        score -= 100
    return round(score, 4)


def refresh_free_llm_health() -> dict[str, Any]:
    registry = load_provider_registry()
    max_per_provider = int(registry.get("health_probe_max_models_per_provider", 8) or 8)
    timeout = int(registry.get("default_timeout_seconds", 22) or 22)

    catalog = load_model_catalog()
    if not catalog.get("candidates"):
        catalog = refresh_free_llm_model_catalog()

    candidates = catalog.get("candidates") if isinstance(catalog.get("candidates"), list) else []
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for c in candidates:
        if isinstance(c, dict):
            grouped[str(c.get("provider") or "")].append(c)

    probe_results: list[dict[str, Any]] = []
    for provider_name, rows in grouped.items():
        provider = provider_by_name(provider_name, include_premium=True)
        if not provider:
            continue
        for candidate in rows[:max_per_provider]:
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
                        {"role": "user", "content": "请严格输出：{\"ok\":true,\"label\":\"free_llm\"}"}
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

    task_policy = load_task_policy()
    tasks = task_policy.get("tasks") if isinstance(task_policy.get("tasks"), dict) else {}
    routes: dict[str, list[dict[str, Any]]] = {}

    for task_name, task_cfg in tasks.items():
        task_routes: list[dict[str, Any]] = []
        for result in probe_results:
            if result.get("status") != "success":
                continue
            candidate = next(
                (
                    c for c in candidates
                    if c.get("provider") == result.get("provider") and c.get("model") == result.get("model")
                ),
                {},
            )
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

    payload = {
        "status": "success",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "probe_count": len(probe_results),
        "success_count": sum(1 for x in probe_results if x.get("status") == "success"),
        "probe_results": probe_results,
        "routes": routes,
    }
    write_json(HEALTH_PATH, payload)
    write_json(ACTIVE_ROUTING_PATH, payload)
    return payload


def load_active_routing() -> dict[str, Any]:
    try:
        return json.loads(ACTIVE_ROUTING_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
