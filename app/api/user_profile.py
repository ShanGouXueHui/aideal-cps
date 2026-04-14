from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.services.adult_verification_config_service import load_adult_verification_rules
from app.services.adult_verification_service import (
    build_adult_verification_url,
    get_adult_verification_status,
    mark_user_adult_verified,
)

router = APIRouter(tags=["user-profile"])


@router.get("/api/user/adult-verification/status")
def adult_verification_status(wechat_openid: str, db: Session = Depends(get_db)):
    return get_adult_verification_status(db, wechat_openid)


@router.post("/api/user/adult-verification/declare")
def adult_verification_declare(
    wechat_openid: str = Form(...),
    db: Session = Depends(get_db),
):
    try:
        return mark_user_adult_verified(db, wechat_openid=wechat_openid)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/h5/adult-verify", response_class=HTMLResponse)
def adult_verify_page(wechat_openid: str):
    rules = load_adult_verification_rules()
    submit_url = "/api/user/adult-verification/declare"

    html = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>{rules["page_title"]}</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #f7f7f5;
      color: #111;
      margin: 0;
      padding: 24px;
    }}
    .card {{
      max-width: 560px;
      margin: 40px auto;
      background: #fff;
      border-radius: 20px;
      padding: 24px;
      box-shadow: 0 10px 30px rgba(0,0,0,0.06);
    }}
    h1 {{
      font-size: 22px;
      margin: 0 0 12px;
    }}
    p {{
      line-height: 1.7;
      color: #444;
    }}
    .notice {{
      margin-top: 16px;
      padding: 14px 16px;
      border-radius: 12px;
      background: #f3f6f4;
      color: #1f3d36;
    }}
    .btn {{
      display: inline-block;
      margin-top: 20px;
      width: 100%;
      padding: 14px 16px;
      border: 0;
      border-radius: 12px;
      background: #1f3d36;
      color: #fff;
      font-size: 16px;
      cursor: pointer;
    }}
    .minor {{
      font-size: 13px;
      color: #777;
      margin-top: 14px;
    }}
  </style>
</head>
<body>
  <div class="card">
    <h1>{rules["page_title"]}</h1>
    <p>{rules["page_subtitle"]}</p>
    <div class="notice">{rules["min_age_notice"]}</div>
    <form method="post" action="{submit_url}">
      <input type="hidden" name="wechat_openid" value="{wechat_openid}" />
      <button class="btn" type="submit">我已年满18岁，继续查看</button>
    </form>
    <div class="minor">提交后仅写入你的成年声明标记，用于限制级商品被动查看。</div>
  </div>
</body>
</html>
"""
    return HTMLResponse(content=html)
