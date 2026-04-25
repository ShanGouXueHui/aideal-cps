from __future__ import annotations

import json
import time
from typing import Any
from urllib import request, error

from app.services.free_llm.provider_registry_service import get_secret


class FreeLLMHttpError(Exception):
    pass


def _join_url(base_url: str, path: str) -> str:
    base = str(base_url or "").rstrip("/")
    suffix = str(path or "").strip()
    if not suffix:
        return base
    if not suffix.startswith("/"):
        suffix = "/" + suffix
    return base + suffix


def _headers(provider: dict[str, Any]) -> dict[str, str]:
    token = get_secret(str(provider.get("env_key", "")), provider.get("env_aliases") or [])
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if provider.get("name") == "openrouter":
        headers["HTTP-Referer"] = "https://aidealfy.cn"
        headers["X-Title"] = "AIdeal CPS"
    return headers


def get_json(provider: dict[str, Any], path: str, *, timeout: int = 18) -> dict[str, Any]:
    url = _join_url(str(provider.get("base_url", "")), path)
    req = request.Request(url, headers=_headers(provider), method="GET")
    start = time.time()
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            data = json.loads(raw) if raw else {}
            if isinstance(data, dict):
                data["_latency_ms"] = int((time.time() - start) * 1000)
                return data
            return {"data": data, "_latency_ms": int((time.time() - start) * 1000)}
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500]
        raise FreeLLMHttpError(f"HTTP {exc.code}: {body}") from exc
    except Exception as exc:
        raise FreeLLMHttpError(str(exc)) from exc


def post_chat_completion(
    provider: dict[str, Any],
    *,
    model: str,
    messages: list[dict[str, str]],
    temperature: float = 0.0,
    max_tokens: int = 400,
    timeout: int = 24,
    response_format: dict[str, Any] | None = None,
    extra_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    if response_format:
        payload["response_format"] = response_format

    if isinstance(extra_payload, dict) and extra_payload:
        # FREE_LLM_EXTRA_PAYLOAD_GATE
        # Provider-specific non-secret controls, e.g. OpenRouter reasoning/thinking.
        # Never allow caller to override routing-critical fields.
        for key, value in extra_payload.items():
            if key in {"model", "messages", "stream"}:
                continue
            payload[key] = value

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    url = _join_url(str(provider.get("base_url", "")), "/chat/completions")
    req = request.Request(url, data=body, headers=_headers(provider), method="POST")
    start = time.time()
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            data = json.loads(raw) if raw else {}
            if isinstance(data, dict):
                data["_latency_ms"] = int((time.time() - start) * 1000)
            return data
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:800]
        raise FreeLLMHttpError(f"HTTP {exc.code}: {body}") from exc
    except Exception as exc:
        raise FreeLLMHttpError(str(exc)) from exc


def extract_text(response: dict[str, Any]) -> str:
    choices = response.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0] if isinstance(choices[0], dict) else {}
        msg = first.get("message") if isinstance(first.get("message"), dict) else {}
        content = msg.get("content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    parts.append(item["text"])
            return "\n".join(parts).strip()
    text = response.get("text")
    return str(text or "").strip()
