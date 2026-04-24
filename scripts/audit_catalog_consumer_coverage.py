from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from sqlalchemy import text

from app.core.db import SessionLocal
from app.models.product import Product
from app.services.wechat_recommend_runtime_service import _active_recommend_products


DIMENSIONS = {
    "人群_男性": ["男士", "剃须", "男"],
    "人群_女性": ["女士", "女", "卫生巾", "护手霜", "身体乳", "防晒"],
    "人群_学生少男少女": ["学生", "中性笔", "笔记本", "作业本", "书包", "文具", "计算器", "错题本"],
    "方面_学习": ["学习", "文具", "中性笔", "笔记本", "作业本", "书包", "计算器", "打印纸", "财经书籍", "商业书籍"],
    "方面_生活": ["洗衣", "抽纸", "纸巾", "洗洁精", "垃圾袋", "保鲜", "水杯", "猫砂", "牙膏", "洗手液"],
    "方面_工作商业": ["办公", "文件夹", "订书机", "便利贴", "鼠标垫", "键盘", "商务", "商业书籍"],
    "频率_高频消耗": ["洗衣", "纸", "牙膏", "洗洁精", "垃圾袋", "牛奶", "饮料", "咖啡", "零食", "大米", "食用油"],
    "用途_吃喝": ["牛奶", "酸奶", "咖啡", "茶", "饮料", "矿泉水", "零食", "坚果", "方便速食", "大米", "食用油", "调味"],
    "用途_玩乐玩具": ["玩具", "积木", "拼图", "桌游", "遥控车"],
    "用途_party装饰": ["派对", "生日", "气球", "装饰", "小夜灯"],
    "用途_cosplay": ["cosplay", "角色扮演"],
    "用途_实用工具": ["数据线", "充电器", "插线板", "电池", "收纳", "雨伞", "雨衣"],
    "用途_投资学习": ["投资理财书籍", "财经书籍", "商业书籍"],
    "用途_运动户外": ["跳绳", "瑜伽", "运动", "户外", "雨伞", "雨衣"],
}

BAD_TAIL_WORDS = [
    "随机", "颜色随机", "香型随机", "新老随机", "盲盒", "试用", "体验", "尝鲜",
    "预售", "预链接", "联系客服", "咨询客服", "拍一发", "定制",
    "医用", "药用", "治疗", "消炎", "术后", "无菌", "外科",
    "成人尿裤", "成人纸尿裤", "内衣", "内裤", "防身", "防狼",
    "维修", "上门服务", "流量卡", "电话卡",
]


def hit(text_value: str, words: list[str]) -> bool:
    return any(w.lower() in text_value.lower() for w in words)


def main() -> None:
    db = SessionLocal()
    try:
        rows = _active_recommend_products(db)

        coverage = defaultdict(lambda: {"total": 0, "samples": []})
        for p in rows:
            text_value = " ".join([
                str(getattr(p, "title", "") or ""),
                str(getattr(p, "category_name", "") or ""),
                str(getattr(p, "ai_tags", "") or ""),
            ])
            for dim, words in DIMENSIONS.items():
                if hit(text_value, words):
                    coverage[dim]["total"] += 1
                    if len(coverage[dim]["samples"]) < 5:
                        coverage[dim]["samples"].append({
                            "id": getattr(p, "id", None),
                            "title": getattr(p, "title", None),
                            "category_name": getattr(p, "category_name", None),
                        })

        bad_tail = []
        for p in rows:
            text_value = " ".join([
                str(getattr(p, "title", "") or ""),
                str(getattr(p, "category_name", "") or ""),
            ])
            if hit(text_value, BAD_TAIL_WORDS):
                bad_tail.append({
                    "id": getattr(p, "id", None),
                    "jd_sku_id": getattr(p, "jd_sku_id", None),
                    "title": getattr(p, "title", None),
                    "category_name": getattr(p, "category_name", None),
                })

        db_columns = [c["Field"] for c in db.execute(text("SHOW COLUMNS FROM products")).mappings().all()]
        return_columns = [
            c for c in db_columns
            if any(k in c.lower() for k in ["return", "refund", "after", "comment", "rate"])
        ]

        summary = {
            "active_recommend_count": len(rows),
            "coverage": dict(coverage),
            "missing_or_weak_dimensions": [
                dim for dim in DIMENSIONS
                if coverage[dim]["total"] < 5
            ],
            "bad_tail_count": len(bad_tail),
            "bad_tail_samples": bad_tail[:50],
            "return_rate_columns_detected": return_columns,
            "return_rate_note": "如果这里为空，说明当前 products 表没有真实退货率/退款率/好评率字段，只能先按标题/类目/商家健康分代理过滤。",
        }

        Path("run").mkdir(exist_ok=True)
        Path("run/catalog_consumer_coverage_report.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        print(json.dumps(summary, ensure_ascii=False, indent=2))

        if bad_tail:
            raise SystemExit("BAD_TAIL_REMAINS")
    finally:
        db.close()


if __name__ == "__main__":
    main()
