from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_RULE_PATH = ROOT / "config" / "semi_recommend_pool_rules.json"
DEFAULT_CANDIDATE_PATH = ROOT / "run" / "semi_recommend_pool_candidates.json"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def contains_any(text: str | None, keywords: list[str]) -> list[str]:
    t = str(text or "").lower()
    return [k for k in keywords if k and k.lower() in t]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rules-path", default=str(DEFAULT_RULE_PATH))
    parser.add_argument("--candidate-path", default=str(DEFAULT_CANDIDATE_PATH))
    parser.add_argument("--max-print", type=int, default=30)
    args = parser.parse_args()

    rules_path = Path(args.rules_path)
    candidate_path = Path(args.candidate_path)

    rules = load_json(rules_path)
    payload = load_json(candidate_path)

    gate = rules.get("risk_gate") or {}
    if gate.get("enabled") is False:
        print(json.dumps({
            "gate": "semi_pool_risk_gate",
            "status": "skipped",
            "reason": "risk_gate.disabled"
        }, ensure_ascii=False))
        return 0

    title_terms: list[str] = []
    for key in gate.get("check_title_against") or ["blocked_title_keywords"]:
        title_terms.extend([str(x) for x in rules.get(key, [])])

    category_terms: list[str] = []
    for key in gate.get("check_category_against") or ["blocked_category_keywords"]:
        category_terms.extend([str(x) for x in rules.get(key, [])])

    title_terms = list(dict.fromkeys([x for x in title_terms if x]))
    category_terms = list(dict.fromkeys([x for x in category_terms if x]))

    violations = []
    for row in payload.get("candidates", []):
        title_hits = contains_any(row.get("title"), title_terms)
        category_hits = contains_any(row.get("category_name"), category_terms)
        if title_hits or category_hits:
            violations.append({
                "id": row.get("id"),
                "jd_sku_id": row.get("jd_sku_id"),
                "title": row.get("title"),
                "category_name": row.get("category_name"),
                "title_hits": title_hits,
                "category_hits": category_hits,
            })

    max_violations = int(gate.get("max_violations", 0))
    result = {
        "gate": "semi_pool_risk_gate",
        "rules_path": str(rules_path),
        "candidate_path": str(candidate_path),
        "candidate_count": len(payload.get("candidates", [])),
        "title_term_count": len(title_terms),
        "category_term_count": len(category_terms),
        "violation_count": len(violations),
        "max_violations": max_violations,
        "status": "success" if len(violations) <= max_violations else "failed",
        "violations": violations[: args.max_print],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))

    return 0 if result["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
