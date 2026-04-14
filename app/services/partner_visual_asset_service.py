from __future__ import annotations

import html
import io
from datetime import datetime
from pathlib import Path

import qrcode
from qrcode.image.svg import SvgPathImage

from app.models.product import Product
from app.services.partner_program_config_service import load_partner_share_copy


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data" / "partner_assets"


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _truncate(text: str | None, max_len: int) -> str:
    value = (text or "").strip()
    if len(value) <= max_len:
        return value
    return value[: max_len - 1] + "…"


def _wrap_text(text: str, line_len: int = 18, max_lines: int = 3) -> list[str]:
    value = (text or "").strip()
    if not value:
        return [""]

    lines: list[str] = []
    current = ""
    for ch in value:
        current += ch
        if len(current) >= line_len:
            lines.append(current)
            current = ""
            if len(lines) >= max_lines:
                break

    if current and len(lines) < max_lines:
        lines.append(current)

    consumed = sum(len(x) for x in lines)
    if len(lines) == max_lines and consumed < len(value):
        lines[-1] = _truncate(lines[-1], max(2, line_len - 1))

    return lines or [""]


def _make_qr_svg(content: str, output_path: Path) -> str:
    qr = qrcode.QRCode(border=1, box_size=8)
    qr.add_data(content)
    qr.make(fit=True)

    image = qr.make_image(image_factory=SvgPathImage)
    buf = io.BytesIO()
    image.save(buf)
    svg_text = buf.getvalue().decode("utf-8")
    output_path.write_text(svg_text, encoding="utf-8")
    return svg_text


def _svg_body(svg_text: str) -> str:
    body = svg_text.strip()
    if body.startswith("<?xml"):
        parts = body.split("?>", 1)
        body = parts[1].strip() if len(parts) > 1 else body
    return body


def build_partner_asset_bundle(
    *,
    partner_code: str,
    product: Product,
    asset_token: str,
    buy_url: str,
    share_url: str,
    buy_copy: str,
    share_copy: str,
    reason: str,
    price_text: str,
    rank_tags: str | None,
) -> dict:
    copy_cfg = load_partner_share_copy()

    today = datetime.now().strftime("%Y%m%d")
    base_dir = DATA_DIR / today / partner_code / str(product.id)
    _ensure_dir(base_dir)

    buy_qr_svg_path = base_dir / "buy_qr.svg"
    share_qr_svg_path = base_dir / "share_qr.svg"
    poster_svg_path = base_dir / "poster.svg"

    buy_qr_svg = _make_qr_svg(buy_url, buy_qr_svg_path)
    _make_qr_svg(share_url, share_qr_svg_path)

    qr_body = _svg_body(buy_qr_svg)
    title_lines = _wrap_text(getattr(product, "title", "") or "", line_len=20, max_lines=3)
    reason_lines = _wrap_text(reason, line_len=22, max_lines=2)

    title_svg_parts: list[str] = []
    title_y = 860
    for line in title_lines:
        title_svg_parts.append(
            f'<text x="40" y="{title_y}" font-size="34" font-weight="700" fill="#1F2937">{html.escape(line)}</text>'
        )
        title_y += 44

    reason_svg_parts: list[str] = []
    reason_y = 1035
    for line in reason_lines:
        reason_svg_parts.append(
            f'<text x="40" y="{reason_y}" font-size="24" fill="#4B5563">{html.escape(line)}</text>'
        )
        reason_y += 32

    title_svg = "".join(title_svg_parts)
    reason_svg = "".join(reason_svg_parts)

    image_url = (getattr(product, "image_url", None) or "").strip()
    image_element = ""
    if image_url:
        image_element = (
            '<image href="{href}" x="40" y="168" width="640" height="640" '
            'preserveAspectRatio="xMidYMid slice" />'
        ).format(href=html.escape(image_url, quote=True))

    tags = (rank_tags or "").strip()
    tag_element = ""
    if tags:
        tag_element = (
            f'<text x="40" y="812" font-size="22" fill="#B45309">'
            f'{html.escape(_truncate(tags, 24))}</text>'
        )

    shop_name = html.escape(_truncate(getattr(product, "shop_name", None) or "", 20))
    poster_title = html.escape(copy_cfg["poster_title"])
    poster_subtitle = html.escape(copy_cfg["poster_subtitle"])
    safe_price_text = html.escape(price_text)
    safe_token = html.escape(asset_token[:12])

    poster_svg = "\n".join(
        [
            '<svg xmlns="http://www.w3.org/2000/svg" width="720" height="1280" viewBox="0 0 720 1280">',
            '  <rect width="720" height="1280" fill="#F5F7FA"/>',
            '  <rect x="0" y="0" width="720" height="120" fill="#1F3D36"/>',
            f'  <text x="40" y="56" font-size="40" font-weight="700" fill="#FFFFFF">{poster_title}</text>',
            f'  <text x="40" y="92" font-size="22" fill="#D1FAE5">{poster_subtitle}</text>',
            '',
            '  <rect x="24" y="144" width="672" height="1112" rx="28" fill="#FFFFFF"/>',
            '  <rect x="40" y="168" width="640" height="640" rx="24" fill="#E5E7EB"/>',
            f'  {image_element}',
            '',
            '  <rect x="40" y="724" width="180" height="48" rx="24" fill="#ECFDF5"/>',
            '  <text x="62" y="756" font-size="24" font-weight="700" fill="#047857">一键购买优先</text>',
            '',
            '  <rect x="500" y="724" width="180" height="48" rx="24" fill="#FEF2F2"/>',
            f'  <text x="522" y="756" font-size="22" font-weight="700" fill="#DC2626">{safe_price_text}</text>',
            '',
            f'  {tag_element}',
            f'  {title_svg}',
            '  <text x="40" y="1000" font-size="24" font-weight="700" fill="#111827">推荐理由</text>',
            f'  {reason_svg}',
            f'  <text x="40" y="1135" font-size="22" fill="#6B7280">店铺：{shop_name}</text>',
            '  <text x="40" y="1172" font-size="20" fill="#9CA3AF">扫码直达商品页</text>',
            '',
            '  <g transform="translate(510,1020) scale(0.42)">',
            f'    {qr_body}',
            '  </g>',
            '',
            f'  <text x="40" y="1225" font-size="20" fill="#6B7280">资产编号：{safe_token}</text>',
            '</svg>',
            '',
        ]
    )

    poster_svg_path.write_text(poster_svg, encoding="utf-8")

    return {
        "buy_qr_svg_path": str(buy_qr_svg_path.relative_to(PROJECT_ROOT)),
        "share_qr_svg_path": str(share_qr_svg_path.relative_to(PROJECT_ROOT)),
        "poster_svg_path": str(poster_svg_path.relative_to(PROJECT_ROOT)),
        "buy_copy": buy_copy,
        "share_copy": share_copy,
    }
