import hashlib
import time
import xml.etree.ElementTree as ET
from typing import Iterable


def verify_wechat_signature(token, signature, timestamp, nonce):
    arr = [token, timestamp, nonce]
    arr.sort()
    raw = "".join(arr)
    sha1 = hashlib.sha1(raw.encode()).hexdigest()
    return sha1 == signature


def parse_wechat_xml(xml_data):
    root = ET.fromstring(xml_data)
    data = {}
    for child in root:
        data[child.tag] = child.text or ""
    return data


def _cdata(value: str) -> str:
    return f"<![CDATA[{value or ''}]]>"


def build_text_response(to_user, from_user, content):
    now = int(time.time())
    return (
        "<xml>"
        f"<ToUserName>{_cdata(to_user)}</ToUserName>"
        f"<FromUserName>{_cdata(from_user)}</FromUserName>"
        f"<CreateTime>{now}</CreateTime>"
        "<MsgType><![CDATA[text]]></MsgType>"
        f"<Content>{_cdata(content)}</Content>"
        "</xml>"
    )


def build_news_response(to_user, from_user, articles: Iterable[dict]):
    article_list = list(articles or [])[:8]
    if not article_list:
        return build_text_response(to_user, from_user, "当前暂无可展示内容。")

    now = int(time.time())
    article_xml_parts = []

    for article in article_list:
        title = str(article.get("title") or "").strip()
        description = str(article.get("description") or "").strip()
        pic_url = str(article.get("pic_url") or "").strip()
        url = str(article.get("url") or "").strip()

        article_xml_parts.append(
            "<item>"
            f"<Title>{_cdata(title)}</Title>"
            f"<Description>{_cdata(description)}</Description>"
            f"<PicUrl>{_cdata(pic_url)}</PicUrl>"
            f"<Url>{_cdata(url)}</Url>"
            "</item>"
        )

    articles_xml = "".join(article_xml_parts)

    return (
        "<xml>"
        f"<ToUserName>{_cdata(to_user)}</ToUserName>"
        f"<FromUserName>{_cdata(from_user)}</FromUserName>"
        f"<CreateTime>{now}</CreateTime>"
        "<MsgType><![CDATA[news]]></MsgType>"
        f"<ArticleCount>{len(article_list)}</ArticleCount>"
        f"<Articles>{articles_xml}</Articles>"
        "</xml>"
    )
