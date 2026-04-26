from __future__ import annotations

import importlib
import logging
from typing import Any

from app.core.db import SessionLocal
from app.services.wechat_service import build_news_response, build_text_response

logger = logging.getLogger("uvicorn.error")


def _call_candidates(module_name: str, candidate_names: list[str], attempts: list[tuple[tuple[Any, ...], dict[str, Any]]]) -> Any:
    try:
        mod = importlib.import_module(module_name)
    except Exception:
        logger.exception("router import failed | module=%s", module_name)
        return None

    for name in candidate_names:
        fn = getattr(mod, name, None)
        if not callable(fn):
            continue

        for args, kwargs in attempts:
            try:
                result = fn(*args, **kwargs)
                if result is not None:
                    return result
            except TypeError:
                continue
            except Exception:
                logger.exception("router call failed | module=%s fn=%s", module_name, name)
                break
    return None


def _get_today_news_articles(db, wechat_openid: str) -> list[dict[str, str]]:
    result = _call_candidates(
        "app.services.wechat_recommend_runtime_service",
        [
            "get_today_recommend_news_articles",
            "build_today_recommend_news_articles",
        ],
        [
            ((db, wechat_openid), {}),
            ((), {"db": db, "wechat_openid": wechat_openid}),
        ],
    )
    if isinstance(result, (list, tuple)):
        rows = []
        for item in result:
            if isinstance(item, dict):
                rows.append(item)
        return rows
    return []


def _get_today_text(db, wechat_openid: str) -> str:
    result = _call_candidates(
        "app.services.wechat_recommend_runtime_service",
        ["get_today_recommend_text_reply"],
        [
            ((db, wechat_openid), {}),
            ((), {"db": db, "wechat_openid": wechat_openid}),
        ],
    )
    return str(result or "").strip()


def _get_find_entry_news_articles(db, wechat_openid: str) -> list[dict[str, str]]:
    result = _call_candidates(
        "app.services.wechat_recommend_runtime_service",
        ["get_find_product_entry_news_articles"],
        [
            ((db, wechat_openid), {}),
            ((), {"db": db, "wechat_openid": wechat_openid}),
        ],
    )
    if isinstance(result, (list, tuple)):
        return [item for item in result if isinstance(item, dict)]
    return []




def _get_find_entry_text(db, wechat_openid: str) -> str:
    result = _call_candidates(
        "app.services.wechat_recommend_runtime_service",
        ["get_find_product_entry_text_reply"],
        [
            ((db, wechat_openid), {}),
            ((), {"db": db, "wechat_openid": wechat_openid}),
        ],
    )
    return str(result or "").strip()


def _get_partner_center_text(db, wechat_openid: str) -> str:
    result = _call_candidates(
        "app.services.partner_center_entry_service",
        [
            "get_partner_center_entry_text_reply",
            "build_partner_center_entry_text_reply",
            "get_partner_center_entry_reply",
        ],
        [
            ((db, wechat_openid), {}),
            ((), {"db": db, "wechat_openid": wechat_openid}),
        ],
    )
    return str(result or "").strip()


def _get_dialog_news_articles(db, wechat_openid: str, content: str) -> list[dict[str, str]]:
    result = _call_candidates(
        "app.services.wechat_dialog_service",
        [
            "get_recommendation_news_articles",
            "get_product_request_news_articles",
        ],
        [
            ((db, wechat_openid, content), {}),
            ((), {"db": db, "openid": wechat_openid, "content": content}),
            ((), {"db": db, "wechat_openid": wechat_openid, "content": content}),
        ],
    )
    if isinstance(result, (list, tuple)):
        return [item for item in result if isinstance(item, dict)]
    return []




def _get_dialog_text(db, wechat_openid: str, content: str, msg_type: str) -> str:
    product_request_text = _call_candidates(
        "app.services.wechat_dialog_service",
        ["get_product_request_text_reply"],
        [
            ((db, wechat_openid, content), {}),
            ((), {"db": db, "openid": wechat_openid, "content": content}),
            ((), {"db": db, "wechat_openid": wechat_openid, "content": content}),
        ],
    )
    product_request_text = str(product_request_text or "").strip()
    if product_request_text:
        return product_request_text  # SPECIALTY_TEXT_FALLBACK_GATE

    result = _call_candidates(
        "app.services.wechat_dialog_service",
        [
            "get_text_reply",
            "get_dialog_text_reply",
            "get_wechat_text_reply",
            "reply_for_user_message",
            "handle_text_message",
            "handle_user_message",
        ],
        [
            ((), {"db": db, "wechat_openid": wechat_openid, "content": content, "msg_type": msg_type}),
            ((db, wechat_openid, content), {}),
            ((db, content, wechat_openid), {}),
            ((wechat_openid, content), {}),
            ((), {"db": db, "openid": wechat_openid, "content": content}),
            ((), {"db": db, "user_id": wechat_openid, "content": content}),
        ],
    )
    return str(result or "").strip()


def _record_subscribe_user_profile(openid: str) -> None:
    """Create or refresh encrypted user profile when a user subscribes."""
    openid = str(openid or "").strip()
    if not openid:
        return

    db = SessionLocal()
    try:
        from app.services.user_service import get_or_create_user_by_openid_db

        get_or_create_user_by_openid_db(db, openid)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("subscribe user profile failed | openid_tail=%s", openid[-8:])
    finally:
        db.close()



def _get_configured_find_entry_fallback_text() -> str:
    try:
        from app.services.wechat_find_product_entry_config_service import get_find_product_entry_copy

        return get_find_product_entry_copy("fallback_text", "").strip()
    except Exception:
        logger.exception("load find product fallback copy failed")
        return ""



def _rewrite_today_articles_to_batch_h5(articles: list[dict[str, str]], wechat_openid: str) -> list[dict[str, str]]:
    if not articles:
        return articles

    import json
    import re
    from pathlib import Path
    from urllib.parse import quote

    try:
        cfg_path = Path(__file__).resolve().parents[2] / "config" / "wechat_recommend_rules.json"
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        url_cfg = cfg.get("url") if isinstance(cfg.get("url"), dict) else {}
        tpl = str(url_cfg.get("today_batch_h5_path_template") or "").strip()
        if not tpl:
            return articles

        try:
            from app.core.wechat_recommend_config import PUBLIC_BASE_URL
            base_url = str(PUBLIC_BASE_URL or "https://aidealfy.cn").rstrip("/")
        except Exception:
            base_url = "https://aidealfy.cn"

        product_ids: list[int] = []
        seen: set[int] = set()
        for article in articles:
            url = str((article or {}).get("url") or "")
            for raw in re.findall(r"/h5/recommend/(\d+)", url):
                try:
                    pid = int(raw)
                except Exception:
                    continue
                if pid > 0 and pid not in seen:
                    product_ids.append(pid)
                    seen.add(pid)

        if len(product_ids) < 2:
            return articles

        ids_text = ",".join(str(x) for x in product_ids)
        rewritten = []
        for idx, article in enumerate(articles, 1):
            copy = dict(article)
            raw_url = str(copy.get("url") or "")
            found = re.findall(r"/h5/recommend/(\d+)", raw_url)
            focus_id = int(found[0]) if found else product_ids[0]
            path = tpl.format(
                ids=quote(ids_text, safe=","),
                focus_id=focus_id,
                scene=quote("today_recommend", safe=""),
                slot=idx,
            )
            joiner = "&" if "?" in path else "?"
            copy["url"] = (
                base_url
                + path
                + joiner
                + "wechat_openid="
                + quote(str(wechat_openid or ""), safe="")
            )
            rewritten.append(copy)

        return rewritten
    except Exception:
        logger.exception("rewrite today articles to batch h5 failed")
        return articles

def route(
    to_user: str,
    from_user: str,
    msg_type: str,
    content: str = "",
    event: str = "",
    event_key: str = "",
    **kwargs,
) -> str:
    if msg_type == "event" and str(event or "").strip().lower() == "subscribe":
        _record_subscribe_user_profile(to_user)
        db = SessionLocal()
        try:
            _call_candidates(
                "app.services.user_profile_service",
                ["record_subscribe_event"],
                [
                    ((db, to_user), {}),
                    ((), {"db": db, "openid": to_user}),
                    ((), {"db": db, "wechat_openid": to_user}),
                ],
            )
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("subscribe user profile failed | openid_tail=%s", (to_user or "")[-8:])
        finally:
            db.close()
        welcome_text = _call_candidates(
            "app.services.wechat_dialog_service",
            ["get_welcome_reply"],
            [
                ((), {}),
            ],
        )
        welcome_text = str(welcome_text or "").strip()
        if not welcome_text:
            welcome_text = (
                "你好，欢迎来到「智省优选」。\n"
                "你可以点击「今日推荐」或「找商品」，也可以直接告诉我想买什么。"
            )
        return build_text_response(to_user, from_user, welcome_text)  # WELCOME_SUBSCRIBE_GATE

    if msg_type == "event" and event == "CLICK" and event_key == "今日推荐":
        db = SessionLocal()
        try:
            articles = _get_today_news_articles(db, to_user)
            fallback_text = ""
            if not articles:
                fallback_text = _get_today_text(db, to_user)
        finally:
            db.close()

        if articles:
            logger.info(
                "today_recommend passive-news branch | openid_tail=%s article_count=%s",
                (to_user or "")[-8:],
                len(articles),
            )
            articles = _rewrite_today_articles_to_batch_h5(articles, to_user)
            return build_news_response(to_user, from_user, articles)

        if not fallback_text:
            fallback_text = "今天的推荐还在准备中，稍后再试一下～"

        logger.info(
            "today_recommend passive-text-fallback | openid_tail=%s text_len=%s",
            (to_user or "")[-8:],
            len(fallback_text),
        )
        return build_text_response(to_user, from_user, fallback_text)

    if msg_type == "event" and event == "CLICK" and event_key == "找商品":
        db = SessionLocal()
        try:
            text = _get_find_entry_text(db, to_user)
        finally:
            db.close()

        if not text:
            text = _get_configured_find_entry_fallback_text()

        return build_text_response(to_user, from_user, text)  # FIND_PRODUCT_TEXT_ENTRY_CONFIG_GATE


    if msg_type == "event" and event == "CLICK" and event_key == "合伙人中心":
        db = SessionLocal()
        try:
            text = _get_partner_center_text(db, to_user)
        finally:
            db.close()

        if not text:
            text = "合伙人中心正在准备中，稍后再试一下～"
        return build_text_response(to_user, from_user, text)

    if msg_type == "text":
        db = SessionLocal()
        try:
            articles = _get_dialog_news_articles(db, to_user, content)
            text = "" if articles else _get_dialog_text(db, to_user, content, msg_type)
        finally:
            db.close()

        if articles:
            logger.info(
                "product_request passive-news branch | openid_tail=%s article_count=%s content=%s",
                (to_user or "")[-8:],
                len(articles),
                content[:80],
            )
            return build_news_response(to_user, from_user, articles)

        if not text:
            text = "可以直接回复你想买的商品，比如：洗衣液、卫生纸、宝宝湿巾。"
        return build_text_response(to_user, from_user, text)

    return build_text_response(
        to_user,
        from_user,
        "可以直接回复你想买的商品，比如：洗衣液、卫生纸、宝宝湿巾。",
    )
