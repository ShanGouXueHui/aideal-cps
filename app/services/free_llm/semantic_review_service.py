from __future__ import annotations

from typing import Any
import json

from app.services.free_llm.router_service import complete_free_llm_json

RISK_WORDS = [
    "处方", "处方药", "otc", "药用", "药品", "皮肤用药", "成人用品", "情趣",
    "农药", "杀虫", "兽药", "白酒", "红酒", "啤酒", "威士忌", "洋酒",
    "防狼", "电击", "喷雾", "辣椒水", "维修", "上门", "本地服务",
]

LOW_QUALITY_WORDS = [
    "试用", "试用装", "体验", "体验装", "拉新", "拉新装", "新人到手0.01",
    "尝鲜", "尝鲜装", "旅行装", "便携装", "随机发", "小样",
]


def _has_risk(text: str) -> bool:
    lower = str(text or "").lower()
    return any(w.lower() in lower for w in RISK_WORDS)


def _clean_categories(categories: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in categories:
        val = str(item or "").strip()
        if not val or val in seen:
            continue
        if _has_risk(val):
            continue
        seen.add(val)
        out.append(val)
    return out


def _clean_normalized_category_keywords(values: list[Any], source_categories: list[str]) -> list[str]:
    source_categories = [str(x or "").strip() for x in source_categories if str(x or "").strip()]
    source_text = "|".join(source_categories)
    generic_block = {
        "商品", "用品", "日用", "家用", "家庭", "清洁", "护理", "套装", "组合", "其他",
        "专用", "京东", "自营", "官方", "旗舰", "旗舰店",
    }

    out: list[str] = []
    seen: set[str] = set()
    for raw in values or []:
        val = str(raw or "").strip()
        val = val.replace("类目", "").replace("品类", "").replace("商品", "").strip(" /｜|，,、")
        if not val:
            continue
        if len(val) < 2 or len(val) > 14:
            continue
        if val in generic_block:
            continue
        if _has_risk(val):
            continue

        # 必须能从原始京东类目中找到语义锚点，避免模型凭空扩类目。
        anchored = any((val in cat) or (cat and cat in val) for cat in source_categories)
        if not anchored:
            # 允许少量稳定同义归一：例如“厨房纸巾”->“厨房纸”，“牙线/牙线棒/牙签”->“牙线”
            anchored = val in source_text

        if not anchored:
            continue
        if val in seen:
            continue
        seen.add(val)
        out.append(val)
    return out


def review_proactive_categories_with_free_llm(
    *,
    categories: list[str],
    top_rows: list[dict[str, Any]],
    rejected: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base_categories = _clean_categories(categories)
    rows = []
    for row in top_rows[:80]:
        title = str(row.get("title") or "")
        category = str(row.get("category_name") or "")
        if _has_risk(title) or _has_risk(category):
            continue
        rows.append(
            {
                "title": title[:90],
                "category": category,
                "price": row.get("price"),
                "coupon_price": row.get("coupon_price"),
                "estimated_commission": row.get("estimated_commission"),
                "sales_volume": row.get("sales_volume"),
                "score": row.get("score"),
            }
        )

    system_prompt = (
        "你是电商导购商品池质检员，只做保守筛选。"
        "目标：从已通过硬合规规则的候选类目中，保留适合微信服务号主动推荐的日用、家庭、母婴、宠物、食品基础消费品类。"
        "不能新增无关类目；可以把候选类目归一成更短、更干净的中文关键词，例如“厨房纸巾”可归一为“厨房纸”，“牙线/牙线棒/牙签”可归一为“牙线”；归一关键词必须来自候选类目的语义。"
        "必须拦截：药品/医疗强功效、成人情趣、酒类、农药杀虫、防身武器、本地维修上门、明显试用拉新小样。"
        "输出严格 JSON。"
    )
    user_prompt = json.dumps(
        {
            "candidate_categories": base_categories,
            "sample_products": rows,
            "rejected_summary": rejected or {},
            "output_schema": {
                "allow_categories": ["只能从 candidate_categories 中选择"],
                "block_categories": ["只能从 candidate_categories 中选择"],
                "normalized_include_keywords": ["可选；输出更短、更干净、可用于模糊匹配的中文类目关键词"],
                "notes": ["简短说明"]
            }
        },
        ensure_ascii=False,
    )

    llm_result = complete_free_llm_json(
        task="catalog_whitelist_review",
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )

    if llm_result.get("status") != "success":
        return {
            "status": "fallback_heuristic",
            "reason": llm_result.get("error", "free_llm_unavailable"),
            "include_category_keywords": base_categories,
            "llm_errors": llm_result.get("errors", []),
        }

    payload = llm_result.get("json")
    if not isinstance(payload, dict):
        return {
            "status": "fallback_heuristic",
            "reason": "llm_json_not_object",
            "include_category_keywords": base_categories,
        }

    normalized = payload.get("normalized_include_keywords")
    normalized_categories = _clean_normalized_category_keywords(normalized if isinstance(normalized, list) else [], base_categories)

    allow = payload.get("allow_categories")
    block = payload.get("block_categories")
    allow_set = {str(x).strip() for x in allow if str(x).strip()} if isinstance(allow, list) else set(base_categories)
    block_set = {str(x).strip() for x in block if str(x).strip()} if isinstance(block, list) else set()

    final_categories: list[str] = []
    for cat in base_categories:
        if cat in block_set:
            continue
        if allow_set and cat not in allow_set:
            continue
        if _has_risk(cat):
            continue
        final_categories.append(cat)

    if len(normalized_categories) >= 8:
        final_categories = normalized_categories
    elif len(final_categories) < 8:
        final_categories = base_categories

    return {
        "status": "success",
        "provider": llm_result.get("provider"),
        "model": llm_result.get("model"),
        "include_category_keywords": final_categories,
        "blocked_categories": [x for x in base_categories if x not in final_categories],
        "normalized_include_keywords": normalized_categories,
        "notes": payload.get("notes", []),
        "latency_ms": llm_result.get("latency_ms"),
    }


def review_proactive_products_with_free_llm(
    *,
    top_rows: list[dict[str, Any]],
    max_rows: int = 80,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    row_ids: set[int] = set()
    heuristic_blocked_ids: set[int] = set()

    for row in top_rows[:max_rows]:
        try:
            pid = int(row.get("id"))
        except Exception:
            continue

        title = str(row.get("title") or "")
        category = str(row.get("category_name") or "")
        text = f"{title} {category}"

        row_ids.add(pid)
        if _has_risk(text) or any(w.lower() in text.lower() for w in LOW_QUALITY_WORDS):
            heuristic_blocked_ids.add(pid)

        rows.append(
            {
                "id": pid,
                "title": title[:120],
                "category": category,
                "price": row.get("price"),
                "coupon_price": row.get("coupon_price"),
                "estimated_commission": row.get("estimated_commission"),
                "sales_volume": row.get("sales_volume"),
                "score": row.get("score"),
            }
        )

    if not rows:
        return {
            "status": "skipped",
            "reason": "no_rows",
            "blocked_product_ids": [],
            "heuristic_blocked_product_ids": [],
        }

    system_prompt = (
        "你是微信服务号电商导购商品池质检员，只做保守审核。"
        "任务：从候选商品中识别不适合主动推荐的商品。"
        "必须拦截：药品/医疗强功效、成人情趣、酒类、农药杀虫、防身武器、本地维修上门、明显试用拉新小样、单包单支低质引流。"
        "注意：成人牙刷不是成人用品，不得仅因“成人”二字拦截；普通日化、纸品、宠物用品、基础食品可以保留。"
        "只能输出输入列表中的商品 id，不得编造 id。输出严格 JSON。"
    )
    user_prompt = json.dumps(
        {
            "candidate_products": rows,
            "heuristic_blocked_product_ids": sorted(heuristic_blocked_ids),
            "output_schema": {
                "block_product_ids": ["只能来自 candidate_products.id"],
                "keep_product_ids": ["可选，只能来自 candidate_products.id"],
                "notes": ["简短说明"]
            }
        },
        ensure_ascii=False,
    )

    llm_result = complete_free_llm_json(
        task="catalog_whitelist_review",
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )

    if llm_result.get("status") != "success":
        return {
            "status": "fallback_heuristic",
            "reason": llm_result.get("error", "free_llm_unavailable"),
            "blocked_product_ids": sorted(heuristic_blocked_ids),
            "heuristic_blocked_product_ids": sorted(heuristic_blocked_ids),
            "llm_errors": llm_result.get("errors", []),
        }

    payload = llm_result.get("json")
    if not isinstance(payload, dict):
        return {
            "status": "fallback_heuristic",
            "reason": "llm_json_not_object",
            "blocked_product_ids": sorted(heuristic_blocked_ids),
            "heuristic_blocked_product_ids": sorted(heuristic_blocked_ids),
        }

    llm_blocked: set[int] = set()
    raw_blocked = payload.get("block_product_ids")
    if isinstance(raw_blocked, list):
        for x in raw_blocked:
            try:
                pid = int(x)
            except Exception:
                continue
            if pid in row_ids:
                llm_blocked.add(pid)

    final_blocked = sorted(heuristic_blocked_ids | llm_blocked)

    return {
        "status": "success",
        "provider": llm_result.get("provider"),
        "model": llm_result.get("model"),
        "blocked_product_ids": final_blocked,
        "llm_blocked_product_ids": sorted(llm_blocked),
        "heuristic_blocked_product_ids": sorted(heuristic_blocked_ids),
        "notes": payload.get("notes", []),
        "latency_ms": llm_result.get("latency_ms"),
    }

