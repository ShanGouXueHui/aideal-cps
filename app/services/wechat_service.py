import hashlib
import time
import xml.etree.ElementTree as ET


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


def build_text_response(to_user, from_user, content):
    now = int(time.time())
    return f"""<xml>
<ToUserName><![CDATA[{to_user}]]></ToUserName>
<FromUserName><![CDATA[{from_user}]]></FromUserName>
<CreateTime>{now}</CreateTime>
<MsgType><![CDATA[text]]></MsgType>
<Content><![CDATA[{content}]]></Content>
</xml>"""
