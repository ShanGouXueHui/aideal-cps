from __future__ import annotations

import html
import re
from pathlib import Path
from textwrap import wrap
from typing import Any

from app.services.poster_card_config_service import load_poster_card_style


def _safe_text(value: Any) -> str:
    return html.escape(str(value or "").strip())


def _slug(value: str) -> str:
    value = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", value.strip())
    value = re.sub(r"_+", "_", value).strip("_")
    return value[:80] or "poster"


def _wrap_lines(text: str, width: int, limit: int) -> list[str]:
    raw = (text or "").strip()
    if not raw:
        return []
    raw = raw.replace("\n", " ")
    lines = wrap(raw, width=width, break_long_words=True, replace_whitespace=False)
    return lines[:limit]


def generate_product_poster_svg(
    *,
    title: str,
    shop_name: str | None,
    category_name: str | None,
    price_text: str,
    reason_text: str,
    link_text: str,
    badge_text: str,
    output_path: str,
) -> str:
    style = load_poster_card_style()

    width = int(style["width"])
    height = int(style["height"])
    padding = int(style["padding"])

    title_lines = _wrap_lines(title, 16, 4)
    reason_lines = _wrap_lines(reason_text, 20, 3)
    meta_line = " / ".join([v for v in [category_name, shop_name] if v])
    meta_lines = _wrap_lines(meta_line, 28, 2) if meta_line else []
    link_lines = _wrap_lines(link_text, 28, 2)

    svg_parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="{style["background"]}"/>',
        f'<rect x="{padding}" y="{padding}" rx="30" ry="30" width="{width - 2 * padding}" height="{height - 2 * padding}" fill="{style["panel_background"]}" stroke="{style["border_color"]}" stroke-width="2"/>',

        f'<text x="{padding + 36}" y="{padding + 60}" font-size="22" font-weight="600" fill="{style["text_secondary"]}">{_safe_text(style["eyebrow"])}</text>',
        f'<text x="{padding + 36}" y="{padding + 120}" font-size="42" font-weight="800" fill="{style["brand_color"]}">{_safe_text(style["brand_name"])}</text>',
        f'<text x="{padding + 36}" y="{padding + 160}" font-size="24" fill="{style["text_secondary"]}">{_safe_text(style["tagline"])}</text>',

        f'<rect x="{padding + 36}" y="{padding + 192}" rx="16" ry="16" width="150" height="38" fill="{style["badge_background"]}"/>',
        f'<text x="{padding + 56}" y="{padding + 217}" font-size="18" font-weight="600" fill="{style["badge_text"]}">{_safe_text(badge_text)}</text>'
    ]

    current_y = padding + 305
    for idx, line in enumerate(title_lines):
        svg_parts.append(
            f'<text x="{padding + 36}" y="{current_y + idx * 52}" font-size="38" font-weight="700" fill="{style["text_primary"]}">{_safe_text(line)}</text>'
        )
    current_y += max(len(title_lines), 1) * 52 + 26

    for idx, line in enumerate(meta_lines):
        svg_parts.append(
            f'<text x="{padding + 36}" y="{current_y + idx * 30}" font-size="20" fill="{style["text_secondary"]}">{_safe_text(line)}</text>'
        )
    current_y += max(len(meta_lines), 0) * 30 + 34

    svg_parts.extend([
        f'<text x="{padding + 36}" y="{current_y}" font-size="20" fill="{style["text_secondary"]}">到手参考</text>',
        f'<text x="{padding + 36}" y="{current_y + 58}" font-size="60" font-weight="800" fill="{style["price_color"]}">{_safe_text(price_text)}</text>'
    ])
    current_y += 140

    svg_parts.append(
        f'<text x="{padding + 36}" y="{current_y}" font-size="20" fill="{style["text_secondary"]}">推荐理由</text>'
    )
    current_y += 36
    for idx, line in enumerate(reason_lines):
        svg_parts.append(
            f'<text x="{padding + 36}" y="{current_y + idx * 34}" font-size="26" fill="{style["text_primary"]}">{_safe_text(line)}</text>'
        )
    current_y += max(len(reason_lines), 1) * 34 + 60

    button_x = padding + 36
    button_y = current_y
    button_w = 220
    button_h = 52
    svg_parts.extend([
        f'<rect x="{button_x}" y="{button_y}" rx="14" ry="14" width="{button_w}" height="{button_h}" fill="{style["button_background"]}"/>',
        f'<text x="{button_x + 26}" y="{button_y + 33}" font-size="22" font-weight="700" fill="{style["button_text"]}">{_safe_text(style["cta_text"])}</text>'
    ])
    current_y += 86

    svg_parts.append(
        f'<text x="{padding + 36}" y="{current_y}" font-size="18" fill="{style["text_secondary"]}">链接路径</text>'
    )
    current_y += 28
    for idx, line in enumerate(link_lines):
        svg_parts.append(
            f'<text x="{padding + 36}" y="{current_y + idx * 28}" font-size="16" fill="{style["brand_color"]}">{_safe_text(line)}</text>'
        )

    footer_y = height - padding - 62
    svg_parts.append(
        f'<text x="{padding + 36}" y="{footer_y}" font-size="20" fill="{style["text_secondary"]}">{_safe_text(style["supporting_line"])}</text>'
    )
    svg_parts.append(
        f'<text x="{padding + 36}" y="{footer_y + 34}" font-size="16" fill="{style["text_secondary"]}">智省优选 · 帮你更理性地做消费决策</text>'
    )

    svg_parts.append("</svg>")

    svg = "\n".join(svg_parts)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(svg, encoding="utf-8")
    return str(path)


def build_product_poster_filename(product_id: int, title: str) -> str:
    return f"{product_id}_{_slug(title)}.svg"
