from __future__ import annotations

import ast
import json
import os
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus

BASE_DIR = Path(__file__).resolve().parents[2]
RULES_PATH = BASE_DIR / "config" / "wechat_recommend_rules.json"
RUNTIME_SERVICE_PATH = BASE_DIR / "app" / "services" / "wechat_recommend_runtime_service.py"

DEFAULT_PUBLIC_BASE_URL = "https://aidealfy.cn"

DEFAULT_RULES = {
    "urls": {
        "public_base_url": DEFAULT_PUBLIC_BASE_URL,
        "promotion_redirect_path": "/api/promotion/redirect",
        "recommend_h5_path_template": "/api/h5/recommend/{product_id}",
    },
    "text_labels": {
        "price": "到手参考",
        "shop": "店铺",
        "reason": "理由",
        "buy": "查看链接",
        "detail": "图文详情",
    },
    "copy": {
        "find_hint": "你可以直接回复想买的商品，比如：卫生纸、洗衣液、宝宝湿巾、京东自营。",
        "title_prefix_find": "先给你放 1 个当前更适合直接看的商品：",
        "title_prefix_today": "今天先给你挑 3 个当前商品池里更稳、更值的商品：",
        "today_empty_hint": "近7天你已看完当前推荐池，先翻翻历史记录，或稍后再来。",
        "today_next_hint": "再点一次“今日推荐”，继续下一组。",
    },
    "today_recommend": {
        "scene": "today_recommend",
        "batch_size": 3,
        "dedup_days": 7,
        "fallback_enabled": True,
        "fallback_limit": 24,
        "price_refresh_before_recommend": True,
        "strict_no_repeat_before_exhaustion": True,
        "allow_partial_batch_when_pool_exhausted": True,
    },
    "pool_rules": {
        "require_basis_price_type": 1,
        "require_short_url": True,
    },
    "shop_rules": {
        "flagship_keywords": [
            "旗舰店",
            "官方旗舰店",
            "京东自营旗舰店",
            "自营旗舰店",
            "官方店",
            "品牌店",
            "专卖店",
            "专营店",
        ],
        "self_operated_keywords": [
            "京东自营",
            "京东自营旗舰店",
            "自营",
        ],
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for key, value in (override or {}).items():
        if isinstance(result.get(key), dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


@lru_cache(maxsize=1)
def load_wechat_recommend_config() -> dict:
    return _deep_merge(DEFAULT_RULES, _read_json(RULES_PATH))


def load_wechat_recommend_rules() -> dict:
    return load_wechat_recommend_config()


def _rules() -> dict:
    return load_wechat_recommend_config()


def get_public_base_url() -> str:
    env_url = (os.getenv("PUBLIC_BASE_URL") or "").strip().rstrip("/")
    if env_url:
        return env_url
    rules = _rules()
    url_cfg = rules.get("urls") or {}
    cfg_url = (
        url_cfg.get("public_base_url")
        or rules.get("public_base_url")
        or DEFAULT_PUBLIC_BASE_URL
    )
    return str(cfg_url).strip().rstrip("/")


def build_promotion_redirect_url(
    *,
    wechat_openid: str,
    product_id: int,
    scene: str,
    slot: int | str,
) -> str:
    rules = _rules()
    url_cfg = rules.get("urls") or {}
    path = str(url_cfg.get("promotion_redirect_path") or "/api/promotion/redirect").strip()
    if not path.startswith("/"):
        path = "/" + path
    return (
        f"{get_public_base_url()}{path}"
        f"?wechat_openid={quote_plus(str(wechat_openid))}"
        f"&product_id={int(product_id)}"
        f"&scene={quote_plus(str(scene))}"
        f"&slot={quote_plus(str(slot))}"
    )


def build_recommend_h5_url(
    *,
    product_id: int,
    scene: str,
    slot: int | str,
) -> str:
    rules = _rules()
    url_cfg = rules.get("urls") or {}
    tpl = str(url_cfg.get("recommend_h5_path_template") or "/api/h5/recommend/{product_id}").strip()
    if not tpl.startswith("/"):
        tpl = "/" + tpl
    path = tpl.format(product_id=int(product_id))
    return (
        f"{get_public_base_url()}{path}"
        f"?scene={quote_plus(str(scene))}"
        f"&slot={quote_plus(str(slot))}"
    )


def _text_label(name: str, default: str) -> str:
    return str((_rules().get("text_labels") or {}).get(name) or default)


def _copy(name: str, default: str):
    return (_rules().get("copy") or {}).get(name, default)


def _today(name: str, default):
    return (_rules().get("today_recommend") or {}).get(name, default)


def _pool(name: str, default):
    return (_rules().get("pool_rules") or {}).get(name, default)


def _shop(name: str, default):
    return (_rules().get("shop_rules") or {}).get(name, default)


# ===== stable exported labels =====
LABEL_PRICE = _text_label("price", "到手参考")
LABEL_SHOP = _text_label("shop", "店铺")
LABEL_REASON = _text_label("reason", "理由")
LABEL_BUY = _text_label("buy", "查看链接")
LABEL_DETAIL = _text_label("detail", "图文详情")

# ===== stable exported copy/constants =====
FIND_HINT = str(_copy("find_hint", "你可以直接回复想买的商品，比如：卫生纸、洗衣液、宝宝湿巾、京东自营。"))
TITLE_PREFIX_FIND = str(_copy("title_prefix_find", "先给你放 1 个当前更适合直接看的商品："))
TITLE_PREFIX_TODAY = str(_copy("title_prefix_today", "今天先给你挑 3 个当前商品池里更稳、更值的商品："))
TODAY_EMPTY_HINT = str(_copy("today_empty_hint", "近7天你已看完当前推荐池，先翻翻历史记录，或稍后再来。"))
TODAY_NEXT_HINT = str(_copy("today_next_hint", "再点一次“今日推荐”，继续下一组。"))

TODAY_RECOMMEND_SCENE = str(_today("scene", "today_recommend"))
TODAY_RECOMMEND_BATCH_SIZE = int(_today("batch_size", 3))
TODAY_RECOMMEND_DEDUP_DAYS = int(_today("dedup_days", 7))
TODAY_RECOMMEND_FALLBACK_ENABLED = bool(_today("fallback_enabled", True))
TODAY_RECOMMEND_FALLBACK_LIMIT = int(_today("fallback_limit", 24))
PRICE_REFRESH_BEFORE_RECOMMEND_ENABLED = bool(_today("price_refresh_before_recommend", True))
STRICT_NO_REPEAT_BEFORE_EXHAUSTION = bool(_today("strict_no_repeat_before_exhaustion", True))
ALLOW_PARTIAL_BATCH_WHEN_POOL_EXHAUSTED = bool(_today("allow_partial_batch_when_pool_exhausted", True))

REQUIRE_BASIS_PRICE_TYPE = int(_pool("require_basis_price_type", 1))
REQUIRE_SHORT_URL = bool(_pool("require_short_url", True))

FLAGSHIP_KEYWORDS = tuple(_shop("flagship_keywords", []))
SELF_OPERATED_KEYWORDS = tuple(_shop("self_operated_keywords", []))

DEFAULT_BASE_URL = get_public_base_url()


def _requested_exports_from_h5_service() -> set[str]:
    if not RUNTIME_SERVICE_PATH.exists():
        return set()
    try:
        tree = ast.parse(RUNTIME_SERVICE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return set()

    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "app.core.wechat_recommend_config":
            for alias in node.names:
                if alias.name != "*":
                    names.add(alias.name)
    return names


def _compat_default(name: str):
    upper = name.upper()

    if upper.startswith("LABEL_"):
        return name

    if upper.endswith("_KEYWORDS"):
        return tuple()

    if upper.endswith("_DAYS"):
        return 7

    if upper.endswith("_BATCH_SIZE"):
        return 3

    if upper.endswith("_LIMIT"):
        return 24

    if upper.endswith("_ENABLED"):
        return False

    if upper.endswith("_SCENE"):
        return "today_recommend"

    if upper.endswith("_HINT"):
        return ""

    if upper.startswith("TITLE_PREFIX_"):
        return ""

    if upper.endswith("_BASE_URL"):
        return get_public_base_url()

    return None


def _ensure_compat_exports() -> None:
    requested = _requested_exports_from_h5_service()
    g = globals()

    for name in requested:
        if name in g:
            continue

        if name == "load_wechat_recommend_rules":
            g[name] = load_wechat_recommend_rules
            continue
        if name == "load_wechat_recommend_config":
            g[name] = load_wechat_recommend_config
            continue
        if name == "build_promotion_redirect_url":
            g[name] = build_promotion_redirect_url
            continue
        if name == "build_recommend_h5_url":
            g[name] = build_recommend_h5_url
            continue
        if name == "get_public_base_url":
            g[name] = get_public_base_url
            continue

        g[name] = _compat_default(name)


_ensure_compat_exports()
