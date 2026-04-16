from __future__ import annotations

import base64
import hashlib
import html
import json
import logging
import threading
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from textwrap import wrap

import cairosvg
import requests
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.models.product import Product
from app.services.recommendation_guard_service import allow_proactive_recommend
from app.services.wechat_custom_message_service import (
    send_custom_image,
    send_custom_text,
    upload_temp_image,
)

logger = logging.getLogger("uvicorn.error")
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data" / "wechat_rich_push"
CURSOR_FILE = DATA_DIR / "today_recommend_cursor.json"


def _safe_decimal(value) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except Exception:
        return Decimal("0")


def _safe_int(value) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _truncate(value: str | None, max_len: int) -> str:
    text = (value or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def _wrap_text(value: str | None, width: int, max_lines: int) -> list[str]:
    text = (value or "").strip().replace("\n", " ")
    if not text:
        return [""]
    lines = wrap(text, width=width, break_long_words=True, replace_whitespace=False)
    lines = lines[:max_lines]
    if len(lines) == max_lines:
        consumed = sum(len(x) for x in lines)
        if consumed < len(text):
            lines[-1] = _truncate(lines[-1], max(2, width - 1))
    return lines or [""]


def _load_cursor_map() -> dict[str, int]:
    if not CURSOR_FILE.exists():
        return {}
    try:
        data = json.loads(CURSOR_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {str(k): int(v) for k, v in data.items()}
    except Exception:
        return {}
    return {}


def _save_cursor_map(data: dict[str, int]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CURSOR_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _openid_key(openid: str) -> str:
    return hashlib.sha1(openid.encode("utf-8")).hexdigest()[:24]


def _owner_label(product: Product) -> str:
    owner = str(getattr(product, "owner", "") or "").strip().lower()
    if owner == "g":
        return "京东自营"
    shop_name = str(getattr(product, "shop_name", "") or "").strip()
    return shop_name or "店铺信息待补充"


def _reason(product: Product) -> str:
    price = _safe_decimal(getattr(product, "price", 0))
    coupon_price = _safe_decimal(getattr(product, "coupon_price", 0))
    sales_volume = _safe_int(getattr(product, "sales_volume", 0))
    if coupon_price > 0 and price > coupon_price:
        return f"券后比标价省{price - coupon_price:.2f}元，当前更划算"
    if sales_volume > 0:
        return f"已售{sales_volume}件，热度更高"
    return "当前价格和综合条件都更稳，适合先看"


def _price_text(product: Product) -> str:
    coupon_price = _safe_decimal(getattr(product, "coupon_price", 0))
    price = _safe_decimal(getattr(product, "price", 0))
    value = coupon_price if coupon_price > 0 else price
    if value > 0:
        return f"¥{value:.2f}"
    return "以京东页为准"


def _direct_url(product: Product) -> str:
    for name in ["short_url", "product_url", "material_url"]:
        value = str(getattr(product, name, "") or "").strip()
        if value:
            return value
    return ""


def _today_product_rows(db: Session) -> list[Product]:
    rows = (
        db.query(Product)
        .filter(
            Product.status == "active",
            Product.compliance_level == "normal",
            Product.allow_proactive_push == True,
            Product.merchant_recommendable == True,
            Product.image_url.isnot(None),
            Product.image_url != "",
            Product.short_url.isnot(None),
            Product.short_url != "",
        )
        .all()
    )
    rows = [row for row in rows if allow_proactive_recommend(row)]
    rows.sort(
        key=lambda row: (
            _safe_int(getattr(row, "sales_volume", 0)),
            float(_safe_decimal(getattr(row, "estimated_commission", 0))),
            int(getattr(row, "id", 0) or 0),
        ),
        reverse=True,
    )
    return rows


def _find_entry_product(db: Session) -> Product | None:
    rows = (
        db.query(Product)
        .filter(
            Product.status == "active",
            Product.compliance_level == "normal",
            Product.merchant_recommendable == True,
            Product.image_url.isnot(None),
            Product.image_url != "",
            Product.short_url.isnot(None),
            Product.short_url != "",
        )
        .all()
    )
    rows.sort(
        key=lambda row: (
            _safe_int(getattr(row, "sales_volume", 0)),
            float(_safe_decimal(getattr(row, "merchant_health_score", 0))),
            float(_safe_decimal(getattr(row, "estimated_commission", 0))),
            int(getattr(row, "id", 0) or 0),
        ),
        reverse=True,
    )
    return rows[0] if rows else None


def has_today_recommend_products(db: Session) -> bool:
    return bool(_today_product_rows(db))


def has_find_entry_product(db: Session) -> bool:
    return _find_entry_product(db) is not None


def _next_batch(openid: str, products: list[Product], batch_size: int = 3) -> list[Product]:
    if not products:
        return []
    key = _openid_key(openid)
    cursor_map = _load_cursor_map()
    start = int(cursor_map.get(key, 0) or 0) % len(products)
    selected = [products[(start + idx) % len(products)] for idx in range(min(batch_size, len(products)))]
    cursor_map[key] = (start + len(selected)) % len(products)
    _save_cursor_map(cursor_map)
    return selected


def _image_data_uri(image_url: str) -> str:
    response = requests.get(image_url, timeout=20)
    response.raise_for_status()
    content_type = response.headers.get("Content-Type", "image/jpeg").split(";", 1)[0].strip() or "image/jpeg"
    encoded = base64.b64encode(response.content).decode("utf-8")
    return f"data:{content_type};base64,{encoded}"


def _poster_svg(product: Product, *, title_prefix: str, footer_text: str) -> str:
    title_lines = _wrap_text(getattr(product, "title", "") or "", 18, 3)
    reason_lines = _wrap_text(_reason(product), 20, 2)
    category_name = html.escape(_truncate(getattr(product, "category_name", None) or "", 16))
    shop_name = html.escape(_truncate(_owner_label(product), 18))
    sold_text = f"已售{_safe_int(getattr(product, 'sales_volume', 0))}件"
    price_text = html.escape(_price_text(product))
    image_href = ""
    image_url = str(getattr(product, "image_url", "") or "").strip()
    if image_url:
        try:
            image_href = _image_data_uri(image_url)
        except Exception as exc:
            logger.warning("wechat poster fetch image failed | product_id=%s error=%s", getattr(product, "id", None), exc)

    title_svg: list[str] = []
    y = 860
    for line in title_lines:
        title_svg.append(f'<text x="48" y="{y}" font-size="42" font-weight="700" fill="#111827">{html.escape(line)}</text>')
        y += 54

    reason_svg: list[str] = []
    y = 1100
    for line in reason_lines:
        reason_svg.append(f'<text x="48" y="{y}" font-size="28" fill="#374151">{html.escape(line)}</text>')
        y += 38

    image_element = '<rect x="48" y="170" width="624" height="624" rx="28" fill="#E5E7EB"/>'
    if image_href:
        image_element += f'<image href="{html.escape(image_href, quote=True)}" x="48" y="170" width="624" height="624" preserveAspectRatio="xMidYMid slice"/>'

    return "\n".join([
        '<svg xmlns="http://www.w3.org/2000/svg" width="720" height="1280" viewBox="0 0 720 1280">',
        '  <rect width="720" height="1280" fill="#F3F4F6"/>',
        '  <rect x="24" y="24" width="672" height="1232" rx="36" fill="#FFFFFF"/>',
        '  <rect x="24" y="24" width="672" height="120" rx="36" fill="#1F3D36"/>',
        f'  <text x="48" y="74" font-size="42" font-weight="800" fill="#FFFFFF">{html.escape(title_prefix)}</text>',
        '  <text x="48" y="108" font-size="22" fill="#D1FAE5">智省优选 · 图里先看全，再决定要不要买</text>',
        f'  {image_element}',
        '  <rect x="48" y="726" width="180" height="50" rx="24" fill="#ECFDF5"/>',
        '  <text x="72" y="760" font-size="24" font-weight="700" fill="#047857">到手参考</text>',
        f'  <text x="470" y="760" font-size="24" font-weight="700" fill="#B45309">{html.escape(category_name or "京东好物")}</text>',
        f'  <text x="48" y="835" font-size="64" font-weight="800" fill="#DC2626">{price_text}</text>',
        *title_svg,
        '  <text x="48" y="1060" font-size="24" font-weight="700" fill="#111827">推荐理由</text>',
        *reason_svg,
        f'  <text x="48" y="1190" font-size="24" fill="#6B7280">{shop_name} ｜ {html.escape(sold_text)}</text>',
        f'  <text x="48" y="1234" font-size="24" fill="#1F3D36">{html.escape(footer_text)}</text>',
        '</svg>',
    ])


def _render_png(product: Product, *, openid: str, scene: str, title_prefix: str, footer_text: str) -> Path:
    day = datetime.now().strftime("%Y%m%d")
    out_dir = DATA_DIR / day / _openid_key(openid) / scene
    out_dir.mkdir(parents=True, exist_ok=True)
    png_path = out_dir / f"{int(getattr(product, 'id', 0) or 0)}.png"
    svg_text = _poster_svg(product, title_prefix=title_prefix, footer_text=footer_text)
    cairosvg.svg2png(bytestring=svg_text.encode("utf-8"), write_to=str(png_path))
    return png_path


def _push_today_recommend_sequence_sync(openid: str) -> None:
    db = SessionLocal()
    try:
        products = _today_product_rows(db)
        batch = _next_batch(openid, products, batch_size=3)
        if not batch:
            send_custom_text(openid, "当前还没有可推荐商品。")
            return

        lines = ["今日推荐直达京东：", ""]
        for idx, product in enumerate(batch, start=1):
            png_path = _render_png(
                product,
                openid=openid,
                scene="today_recommend",
                title_prefix=f"今日推荐 {idx}/3",
                footer_text="看完下方文字，点链接直接去京东",
            )
            media_id = upload_temp_image(str(png_path))
            send_custom_image(openid, media_id)
            lines.append(f"{idx}. {_truncate(getattr(product, 'title', '') or '商品', 24)}")
            lines.append(f"到手参考：{_price_text(product)}")
            lines.append(f"理由：{_reason(product)}")
            lines.append(f"直达：{_direct_url(product)}")
            lines.append("")

        lines.append("再点一次“今日推荐”，继续看下一组 3 个。")
        send_custom_text(openid, "\n".join(lines).strip())
    except Exception:
        logger.exception("push today recommend sequence failed | openid_hash=%s", _openid_key(openid))
        try:
            send_custom_text(openid, "推荐图生成失败了，你先再点一次“今日推荐”试试。")
        except Exception:
            logger.exception("push today recommend fallback text failed | openid_hash=%s", _openid_key(openid))
    finally:
        db.close()


def _push_find_product_entry_sequence_sync(openid: str) -> None:
    db = SessionLocal()
    try:
        product = _find_entry_product(db)
        if not product:
            send_custom_text(openid, "当前还没有合适的商品图可发，你可以直接回复想买的商品名。")
            return

        png_path = _render_png(
            product,
            openid=openid,
            scene="find_product_entry",
            title_prefix="先给你一个当前更值得看的",
            footer_text="不想看这个，也可以直接回复品类关键词",
        )
        media_id = upload_temp_image(str(png_path))
        send_custom_image(openid, media_id)
        send_custom_text(
            openid,
            "\n".join([
                f"先给你 1 个当前更值得先看的商品：{_truncate(getattr(product, 'title', '') or '商品', 28)}",
                f"到手参考：{_price_text(product)}",
                f"理由：{_reason(product)}",
                f"直达京东：{_direct_url(product)}",
                "也可以直接回复：卫生纸 / 洗衣液 / 宝宝湿巾 / 京东自营",
            ]),
        )
    except Exception:
        logger.exception("push find entry sequence failed | openid_hash=%s", _openid_key(openid))
        try:
            send_custom_text(openid, "商品图生成失败了，你可以直接回复：卫生纸、洗衣液、宝宝湿巾。")
        except Exception:
            logger.exception("push find entry fallback text failed | openid_hash=%s", _openid_key(openid))
    finally:
        db.close()


def enqueue_today_recommend_sequence(openid: str) -> None:
    threading.Thread(target=_push_today_recommend_sequence_sync, args=(openid,), daemon=True).start()


def enqueue_find_product_entry_sequence(openid: str) -> None:
    threading.Thread(target=_push_find_product_entry_sequence_sync, args=(openid,), daemon=True).start()
