from __future__ import annotations

import argparse
import json
import random
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import func

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.db import SessionLocal
from app.models.product import Product
from app.services.catalog_refresh_config_service import load_catalog_refresh_rules
from app.services.catalog_refresh_service import _product_payload_from_live_row
from app.services.jd_live_search_service import _build_short_link, _normalize_live_item, _pick_material_url
from app.services.jd_product_sync_service import upsert_product
from app.services.jd_union_client import (
    JDUnionClient,
    extract_goods_query_items,
    extract_jingfen_items,
)

RUN_DIR = ROOT / "run"
LOG_DIR = ROOT / "logs"
RUN_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)

STATUS_PATH = RUN_DIR / "bulk_catalog_expand_status.json"
INGEST_POLICY_PATH = ROOT / "config" / "catalog_ingest_policy.json"


EXTRA_KEYWORDS = [
    "洗衣液", "洗衣凝珠", "洗衣粉", "柔顺剂", "除菌液", "消毒液", "洗洁精", "洗碗块", "洗碗粉",
    "垃圾袋", "抽纸", "卷纸", "厨房纸", "湿厕纸", "湿巾", "棉柔巾", "洗脸巾", "保鲜袋", "保鲜膜",
    "收纳盒", "收纳袋", "水杯", "保温杯", "玻璃杯", "塑料杯", "饭盒", "保鲜盒", "毛巾", "浴巾",
    "牙膏", "牙刷", "漱口水", "牙线", "洗发水", "护发素", "发膜", "沐浴露", "洗手液",
    "男士洗面奶", "女士洗面奶", "洁面乳", "身体乳", "护手霜", "润唇膏", "防晒霜", "面霜",
    "卫生巾", "安睡裤", "纸尿裤", "尿不湿", "奶瓶清洗", "儿童面霜", "婴儿湿巾", "婴童护肤",
    "猫砂", "猫粮", "狗粮", "宠物尿垫", "宠物湿巾", "宠物零食",
    "大米", "食用油", "酱油", "醋", "调味品", "面条", "方便速食", "零食", "坚果",
    "牛奶", "酸奶", "咖啡", "挂耳咖啡", "即饮咖啡", "茶叶", "红茶", "绿茶", "饮料", "矿泉水",
    "中性笔", "笔记本", "打印纸", "文件夹", "订书机", "回形针", "便利贴", "计算器", "书包",
    "双肩包", "电脑包", "运动背包", "旅行包", "登山包",
    "剃须刀", "剃须泡沫", "男士沐浴露", "男士洗发水",
    "玩具", "积木", "拼图", "遥控车", "早教玩具", "儿童玩具", "桌游",
    "数据线", "充电器", "充电宝", "耳机", "插线板", "电池", "鼠标垫", "键盘清洁",
    "雨伞", "雨衣", "跳绳", "瑜伽垫", "运动水杯", "运动毛巾", "护膝", "护腕", "弹力带",
    "螺丝刀", "卷尺", "工具箱", "手电筒", "理线器", "粘钩", "挂钩", "胶带",
    "生日装饰", "派对装饰", "气球", "小夜灯",
]


@dataclass(frozen=True)
class FetchTask:
    kind: str
    source: str
    page_index: int
    page_size: int
    sort_name: str | None = None
    sort: str | None = None
    profile: str = ""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_status(payload: dict[str, Any]) -> None:
    payload = dict(payload)
    payload["updated_at"] = _now_iso()
    STATUS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _unique_keep_order(values: list[Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for v in values:
        s = str(v or "").strip()
        if not s:
            continue
        k = s.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(s)
    return out


def _load_keywords(limit: int | None = None) -> list[str]:
    try:
        rules = load_catalog_refresh_rules()
    except Exception:
        rules = {}
    keywords = list(rules.get("keyword_seeds") or []) + EXTRA_KEYWORDS
    out = _unique_keep_order(keywords)
    if limit and limit > 0:
        out = out[:limit]
    return out


def _load_elite_ids() -> list[int]:
    try:
        rules = load_catalog_refresh_rules()
    except Exception:
        rules = {}
    values = list(rules.get("elite_ids") or [])
    # 129 是当前已验证可用的京粉精选榜；其他 ID 只作为机会性探索，失败会被隔离记录，不中断扩池。
    values += [129, 1, 2, 10, 15, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32]
    out: list[int] = []
    seen: set[int] = set()
    for v in values:
        try:
            i = int(v)
        except Exception:
            continue
        if i in seen:
            continue
        seen.add(i)
        out.append(i)
    return out


def _sort_profiles() -> list[dict[str, str]]:
    return [
        {"profile": "sales_30d", "sort_name": "inOrderCount30Days", "sort": "desc"},
        {"profile": "commission_amount", "sort_name": "commission", "sort": "desc"},
    ]


def _build_tasks(
    *,
    keyword_limit: int,
    pages_per_keyword: int,
    page_size: int,
    include_elite: bool,
    elite_pages: int,
    max_requests: int,
) -> list[FetchTask]:
    tasks: list[FetchTask] = []
    profiles = _sort_profiles()
    keywords = _load_keywords(keyword_limit)

    for keyword in keywords:
        for profile in profiles:
            for page in range(1, pages_per_keyword + 1):
                tasks.append(
                    FetchTask(
                        kind="keyword",
                        source=keyword,
                        page_index=page,
                        page_size=page_size,
                        sort_name=profile["sort_name"],
                        sort=profile["sort"],
                        profile=profile["profile"],
                    )
                )

    if include_elite:
        for elite_id in _load_elite_ids():
            for profile in profiles:
                for page in range(1, elite_pages + 1):
                    tasks.append(
                        FetchTask(
                            kind="elite",
                            source=str(elite_id),
                            page_index=page,
                            page_size=page_size,
                            sort_name=profile["sort_name"],
                            sort=profile["sort"],
                            profile=profile["profile"],
                        )
                    )

    random.shuffle(tasks)
    if max_requests and max_requests > 0:
        tasks = tasks[:max_requests]
    return tasks



def _load_ingest_policy(path: Path = INGEST_POLICY_PATH) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception as exc:
        print(json.dumps({"event": "ingest_policy_load_failed", "path": str(path), "error": repr(exc)[:300]}, ensure_ascii=False), flush=True)
        return {}


def _bulk_short_link_policy(args: Any) -> dict[str, Any]:
    raw = _load_ingest_policy(Path(getattr(args, "ingest_policy_path", INGEST_POLICY_PATH)))
    bulk = raw.get("bulk_catalog_expand") if isinstance(raw.get("bulk_catalog_expand"), dict) else {}
    policy = bulk.get("short_link_on_ingest") if isinstance(bulk.get("short_link_on_ingest"), dict) else {}
    return policy

def _count_products() -> int:
    db = SessionLocal()
    try:
        return int(db.query(func.count(Product.id)).scalar() or 0)
    finally:
        db.close()


def _safe_upsert_raw_candidate(db, item: dict[str, Any], *, task: FetchTask, dry_run: bool, client: JDUnionClient | None = None, short_link_policy: dict[str, Any] | None = None) -> str:
    material_url = _pick_material_url(item)
    live_row = _normalize_live_item(item, short_url=None)

    payload = _product_payload_from_live_row(
        live_row,
        keyword=task.source,
        source_profile=f"bulk_{task.kind}_{task.profile}_p{task.page_index}",
    )

    jd_sku_id = str(payload.get("jd_sku_id") or "").strip()
    title = str(payload.get("title") or "").strip()
    if not jd_sku_id or not title or title == "未知商品":
        return "skipped"

    payload["jd_sku_id"] = jd_sku_id
    payload["product_url"] = material_url or payload.get("product_url")
    payload["material_url"] = material_url or payload.get("material_url")
    # short_url 不再硬编码丢弃；是否生成/保存由 config/catalog_ingest_policy.json 控制。
    payload.pop("short_url", None)

    tags = str(payload.get("ai_tags") or "")
    tag_suffix = f"bulk扩池:raw_candidate|待评估|{task.kind}:{task.profile}"
    payload["ai_tags"] = (tags + "|" + tag_suffix).strip("|")[:255]
    payload["status"] = "active"
    payload["last_sync_at"] = datetime.now(timezone.utc)

    existing = db.query(Product).filter(Product.jd_sku_id == jd_sku_id).first()

    if existing is None:
        # 新入库商品默认进 raw candidate，不直接进入微信主动推荐，避免污染主榜。
        payload["merchant_recommendable"] = False
        payload["allow_proactive_push"] = False
        payload["allow_partner_share"] = True
    else:
        # 已经是可推荐的老商品，不能被 bulk raw 同步降级，也不能擦掉短链。
        if getattr(existing, "short_url", None):
            payload.pop("short_url", None)
        if bool(getattr(existing, "merchant_recommendable", False)):
            payload.pop("merchant_recommendable", None)
        if bool(getattr(existing, "allow_proactive_push", False)):
            payload.pop("allow_proactive_push", None)
        if bool(getattr(existing, "allow_partner_share", False)):
            payload.pop("allow_partner_share", None)


    short_policy = short_link_policy or {}
    should_build_short = False
    if bool(short_policy.get("enabled", False)) and material_url and not dry_run:
        if existing is None and bool(short_policy.get("new_products_only", True)):
            should_build_short = True
        elif existing is not None and bool(short_policy.get("update_existing_missing_short_url", False)) and not getattr(existing, "short_url", None):
            should_build_short = True

    if should_build_short and client is not None:
        generated_short_url = _build_short_link(client, material_url)
        if generated_short_url:
            payload["short_url"] = generated_short_url
            payload["product_url"] = generated_short_url

    if dry_run:
        return "dry_run"

    _, action = upsert_product(db, payload)
    db.commit()
    return action


def _fetch_items(client: JDUnionClient, task: FetchTask) -> list[dict[str, Any]]:
    if task.kind == "keyword":
        response = client.goods_query(
            keyword=task.source,
            page_index=task.page_index,
            page_size=task.page_size,
            sort_name=task.sort_name,
            sort=task.sort,
        )
        return extract_goods_query_items(response)

    if task.kind == "elite":
        response = client.jingfen_query(
            elite_id=int(task.source),
            page_index=task.page_index,
            page_size=task.page_size,
            sort_name=task.sort_name,
            sort=task.sort,
        )
        return extract_jingfen_items(response)

    return []


def _run_task(task: FetchTask, args, stop_event: threading.Event) -> dict[str, Any]:
    if stop_event.is_set():
        return {"status": "skipped_stop", "task": task.__dict__}

    started = time.time()
    db = SessionLocal()
    try:
        client = JDUnionClient(timeout_seconds=args.timeout_seconds)
        if args.request_sleep_seconds > 0:
            time.sleep(args.request_sleep_seconds * random.random())

        items = _fetch_items(client, task)
        short_link_policy = _bulk_short_link_policy(args)

        inserted = 0
        updated = 0
        skipped = 0
        dry_run = 0

        for item in items:
            if stop_event.is_set():
                break
            try:
                action = _safe_upsert_raw_candidate(db, item, task=task, dry_run=args.dry_run, client=client, short_link_policy=short_link_policy)
                if action == "inserted":
                    inserted += 1
                elif action == "updated":
                    updated += 1
                elif action == "dry_run":
                    dry_run += 1
                else:
                    skipped += 1
            except Exception:
                try:
                    db.rollback()
                except Exception:
                    pass
                skipped += 1

        elapsed_ms = int((time.time() - started) * 1000)
        return {
            "status": "success",
            "kind": task.kind,
            "source": task.source,
            "profile": task.profile,
            "page_index": task.page_index,
            "fetched": len(items),
            "inserted": inserted,
            "updated": updated,
            "skipped": skipped,
            "dry_run": dry_run,
            "elapsed_ms": elapsed_ms,
        }
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        return {
            "status": "failed",
            "kind": task.kind,
            "source": task.source,
            "profile": task.profile,
            "page_index": task.page_index,
            "error": repr(exc)[:800],
            "elapsed_ms": int((time.time() - started) * 1000),
        }
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-total", type=int, default=100000)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--keyword-limit", type=int, default=0)
    parser.add_argument("--pages-per-keyword", type=int, default=40)
    parser.add_argument("--elite-pages", type=int, default=20)
    parser.add_argument("--page-size", type=int, default=50)
    parser.add_argument("--max-requests", type=int, default=12000)
    parser.add_argument("--timeout-seconds", type=int, default=20)
    parser.add_argument("--request-sleep-seconds", type=float, default=0.12)
    parser.add_argument("--include-elite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--progress-every", type=int, default=50)
    parser.add_argument("--ingest-policy-path", default=str(INGEST_POLICY_PATH))
    args = parser.parse_args()

    args.workers = max(1, min(int(args.workers), 24))
    args.page_size = max(1, min(int(args.page_size), 50))
    args.pages_per_keyword = max(1, int(args.pages_per_keyword))
    args.elite_pages = max(1, int(args.elite_pages))

    initial_total = _count_products()
    tasks = _build_tasks(
        keyword_limit=args.keyword_limit,
        pages_per_keyword=args.pages_per_keyword,
        page_size=args.page_size,
        include_elite=args.include_elite,
        elite_pages=args.elite_pages,
        max_requests=args.max_requests,
    )

    status = {
        "job": "bulk_catalog_expand",
        "status": "running",
        "started_at": _now_iso(),
        "target_total": args.target_total,
        "initial_total": initial_total,
        "workers": args.workers,
        "task_count": len(tasks),
        "dry_run": args.dry_run,
        "inserted": 0,
        "updated": 0,
        "failed_tasks": 0,
        "processed_tasks": 0,
    }
    _write_status(status)

    print(json.dumps({"event": "start", **status}, ensure_ascii=False), flush=True)

    if initial_total >= args.target_total:
        status.update({"status": "success", "finished_at": _now_iso(), "final_total": initial_total})
        _write_status(status)
        print(json.dumps({"event": "already_reached", **status}, ensure_ascii=False), flush=True)
        return 0

    stop_event = threading.Event()
    lock = threading.Lock()

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        future_map = {pool.submit(_run_task, task, args, stop_event): task for task in tasks}

        for future in as_completed(future_map):
            result = future.result()

            with lock:
                status["processed_tasks"] = int(status.get("processed_tasks", 0)) + 1
                status["inserted"] = int(status.get("inserted", 0)) + int(result.get("inserted", 0) or 0)
                status["updated"] = int(status.get("updated", 0)) + int(result.get("updated", 0) or 0)
                if result.get("status") == "failed":
                    status["failed_tasks"] = int(status.get("failed_tasks", 0)) + 1

                estimated_total = initial_total + int(status.get("inserted", 0))
                status["estimated_total"] = estimated_total

                should_print = (
                    int(status["processed_tasks"]) <= 10
                    or int(status["processed_tasks"]) % max(1, args.progress_every) == 0
                    or result.get("status") == "failed"
                )

                if estimated_total >= args.target_total:
                    stop_event.set()
                    status["stop_reason"] = "target_reached"

                if should_print:
                    print(json.dumps({"event": "progress", "result": result, "status": status}, ensure_ascii=False), flush=True)
                    _write_status(status)

    final_total = _count_products()
    status.update(
        {
            "status": "success" if final_total >= min(args.target_total, initial_total + 1) else "partial",
            "finished_at": _now_iso(),
            "final_total": final_total,
        }
    )
    _write_status(status)
    print(json.dumps({"event": "finish", **status}, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
