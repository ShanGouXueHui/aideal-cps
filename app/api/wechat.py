import os
from fastapi import APIRouter, Request, Response
from fastapi.responses import PlainTextResponse

from app.services.wechat_service import verify_wechat_signature, parse_wechat_xml
from app.services.message_router import route

router = APIRouter()

TOKEN = os.getenv("WECHAT_TOKEN", "aideal_token")


@router.get("/wechat/callback")
async def verify(signature: str = "", timestamp: str = "", nonce: str = "", echostr: str = ""):
    if verify_wechat_signature(TOKEN, signature, timestamp, nonce):
        return PlainTextResponse(echostr)
    return "invalid"


@router.post("/wechat/callback")
async def callback(request: Request, signature: str = "", timestamp: str = "", nonce: str = ""):
    if not verify_wechat_signature(TOKEN, signature, timestamp, nonce):
        return Response("invalid", status_code=403)

    body = await request.body()
    msg = parse_wechat_xml(body)

    resp = route(msg)

    return Response(content=resp, media_type="application/xml")
