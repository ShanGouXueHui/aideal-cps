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
        "不能新增输入之外的类目；只能删除不适合主动推荐的类目。"
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

    if len(final_categories) < 8:
        final_categories = base_categories

    return {
        "status": "success",
        "provider": llm_result.get("provider"),
        "model": llm_result.get("model"),
        "include_category_keywords": final_categories,
        "blocked_categories": [x for x in base_categories if x not in final_categories],
        "notes": payload.get("notes", []),
        "latency_ms": llm_result.get("latency_ms"),
    }
