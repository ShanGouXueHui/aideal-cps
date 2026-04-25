from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import Any

from app.core.db import SessionLocal
from app.services.wechat_recommend_runtime_service import _active_recommend_products


def _text(x: Any) -> str:
    return str(x or "").strip()


def _norm(x: Any) -> str:
    return _text(x).lower()


def _haystack(p: Any) -> str:
    return " ".join(
        [
            _norm(getattr(p, "title", "")),
            _norm(getattr(p, "category_name", "")),
            _norm(getattr(p, "shop_name", "")),
            _norm(getattr(p, "ai_tags", "")),
        ]
    )


def _keyword_source(p: Any) -> str:
    tags = _text(getattr(p, "ai_tags", ""))
    values = []
    for part in re.split(r"[|,，;；\s]+", tags):
        if ":" in part:
            values.append(part.split(":", 1)[1])
    return " ".join(values)


def _match_any(text: str, keys: list[str]) -> bool:
    return any(k and k.lower() in text for k in keys)


STRICT_SOURCE_ONLY_DIMS = {
    "用途_吃喝",
    "用途_party装饰",
    "用途_cosplay_安全受控",
    "用途_实用工具",
    "用途_学习投资",
    "用途_数码小件",
}


DIMENSIONS = {
    "人群_男性": ["男士洗面奶", "男士洗发水", "男士沐浴露", "剃须刀", "剃须泡沫", "男士洁面", "刮胡刀"],
    "人群_女性": ["女士洗面奶", "护手霜", "润唇膏", "身体乳", "防晒霜", "卫生巾", "女性护理"],
    "人群_学生少男少女": ["中性笔", "笔记本", "作业本", "文具盒", "书包", "错题本", "学生", "儿童玩具"],

    "方面_学习": ["中性笔", "笔记本", "作业本", "文具盒", "书包", "错题本", "计算器", "学习用品", "财经书籍", "商业书籍", "投资理财书籍"],
    "方面_生活": ["洗衣液", "牙膏", "抽纸", "纸巾", "洗洁精", "洗手液", "沐浴露", "洗发水", "保鲜膜", "猫砂", "大米", "食用油"],
    "方面_工作商业": ["办公用品", "文件夹", "订书机", "回形针", "打印纸", "鼠标垫", "商务笔记本", "商业书籍", "文件袋"],

    "频率_高频消耗": ["洗衣液", "牙膏", "抽纸", "纸巾", "卫生纸", "洗洁精", "洗手液", "大米", "食用油", "猫粮", "狗粮", "宝宝湿巾"],
    "频率_中低频耐用品": ["剃须刀", "书包", "计算器", "订书机", "工具箱", "手电筒", "充电宝", "插线板", "运动水杯"],

    "用途_吃喝": ["牛奶", "酸奶", "咖啡", "茶叶", "茶饮料", "乌龙茶", "饮料", "矿泉水", "零食", "坚果", "方便速食", "面条", "调味品", "酱油", "醋", "大米", "食用油"],
    "用途_玩乐玩具": ["玩具", "积木", "拼图", "桌游", "遥控车", "儿童玩具", "动漫周边"],
    "用途_party装饰": ["派对用品", "派对装饰", "生日装饰", "生日帽", "气球", "节日装饰", "装饰摆件", "小夜灯"],
    "用途_cosplay_安全受控": ["儿童演出服", "动漫周边", "角色扮演服装", "cosplay服装"],
    "用途_实用工具": ["螺丝刀", "螺丝刀套装", "卷尺", "工具箱", "手电筒", "理线器", "粘钩", "挂钩", "胶带", "收纳工具"],
    "用途_学习投资": ["财经书籍", "商业书籍", "投资理财书籍", "投资书籍", "金融书籍", "经济学书籍", "理财入门书籍", "巴菲特书籍", "商业案例书籍"],
    "用途_数码小件": ["数据线", "充电器", "充电宝", "手机支架", "耳机", "插线板", "电池"],
    "用途_运动户外": ["运动水杯", "跳绳", "瑜伽垫", "运动毛巾", "雨伞", "雨衣", "运动护膝", "运动护腕", "弹力带", "握力器", "瑜伽砖", "运动袜", "运动背包", "健身小器材"],
}


RISK_KEYS = [
    "随机", "盲盒", "试用", "体验", "尝鲜", "预售", "预链接",
    "医用", "药用", "治疗", "术后", "无菌", "成人尿裤", "成人纸尿裤",
    "内衣", "内裤", "防身", "防狼", "维修", "上门服务", "联系客服", "咨询客服",
    "情趣", "性感", "诱惑", "透视", "低胸", "兔女郎", "成人用品",
]


def main() -> None:
    db = SessionLocal()
    try:
        rows = _active_recommend_products(db)

        coverage = defaultdict(list)
        for p in rows:
            src = _keyword_source(p)
            full = _haystack(p)
            # 先用 ai_tags 里的关键词来源匹配；不足时再用标题/类目/店铺补充
            for dim, keys in DIMENSIONS.items():
                if dim in STRICT_SOURCE_ONLY_DIMS:
                    matched = _match_any(src, keys)
                else:
                    matched = _match_any(src, keys) or _match_any(full, keys)
                if matched:
                    coverage[dim].append(p)

        result = {
            "active_recommend_count": len(rows),
            "coverage": {},
            "missing_or_weak_dimensions": [],
            "bad_tail_count": 0,
            "bad_tail_samples": [],
            "quality_field_count": 0,
            "return_rate_columns_detected": ["commission_rate", "good_comments_share", "comment_count"],
            "notes": [
                "维度审计优先使用 ai_tags 关键词来源，减少“山茶花”等标题误判。",
                "cosplay/角色扮演为安全受控维度，不建议主动泛推；仅安全儿童演出服、动漫周边、派对装饰允许进入。",
                "投资仅覆盖书籍/学习材料，不覆盖金融理财产品。",
            ],
        }

        for dim, products in coverage.items():
            samples = []
            for p in products[:5]:
                samples.append(
                    {
                        "id": getattr(p, "id", None),
                        "title": getattr(p, "title", None),
                        "category_name": getattr(p, "category_name", None),
                        "ai_tags": getattr(p, "ai_tags", None),
                    }
                )
            result["coverage"][dim] = {
                "total": len(products),
                "samples": samples,
            }

        for dim in DIMENSIONS:
            total = len(coverage.get(dim, []))
            threshold = 3
            if dim in ("用途_实用工具", "用途_学习投资", "用途_运动户外"):
                threshold = 5
            if dim == "用途_cosplay_安全受控":
                threshold = 1
            if total < threshold:
                result["missing_or_weak_dimensions"].append(dim)

        bad = []
        quality_count = 0
        for p in rows:
            full = _haystack(p)
            if getattr(p, "good_comments_share", None) is not None or getattr(p, "comment_count", None) is not None:
                quality_count += 1
            if any(k.lower() in full for k in RISK_KEYS):
                bad.append(
                    {
                        "id": getattr(p, "id", None),
                        "title": getattr(p, "title", None),
                        "category_name": getattr(p, "category_name", None),
                        "ai_tags": getattr(p, "ai_tags", None),
                    }
                )

        result["bad_tail_count"] = len(bad)
        result["bad_tail_samples"] = bad[:20]
        result["quality_field_count"] = quality_count

        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    finally:
        db.close()


if __name__ == "__main__":
    main()
