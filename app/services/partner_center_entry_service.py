from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.user import User
from app.models.partner_account import PartnerAccount

try:
    from app.models.partner_share_asset import PartnerShareAsset
except Exception:
    PartnerShareAsset = None

try:
    from app.services.partner_reward_service import get_partner_reward_overview
except Exception:
    get_partner_reward_overview = None


def _safe_float(value) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _get_user(db: Session, wechat_openid: str):
    return db.query(User).filter(User.wechat_openid == wechat_openid).first()


def _get_partner_account(db: Session, user_id: int):
    return db.query(PartnerAccount).filter(PartnerAccount.user_id == user_id).first()


def _get_recent_asset_count(db: Session, partner_account_id: int) -> int:
    if PartnerShareAsset is None:
        return 0
    try:
        return (
            db.query(PartnerShareAsset)
            .filter(PartnerShareAsset.partner_account_id == partner_account_id)
            .count()
        )
    except Exception:
        return 0


def get_partner_center_entry_reply(db: Session, wechat_openid: str) -> str:
    user = _get_user(db, wechat_openid)
    if not user:
        return (
            "你还没有开通合伙人身份。\n"
            "当前开通方式：\n"
            "1）直接付费 100 元开通\n"
            "2）累计采购满 10000 元自动升级\n\n"
            "回复“开通合伙人”或“合伙人规则”，我继续带你看。"
        )

    account = _get_partner_account(db, int(user.id))
    if not account:
        return (
            "你当前还不是合伙人。\n"
            "当前开通方式：\n"
            "1）直接付费 100 元开通\n"
            "2）累计采购满 10000 元自动升级\n\n"
            "开通后可以获得：分享商品、推广素材、积分抵扣、等级升级。"
        )

    reward_overview = None
    if get_partner_reward_overview is not None:
        try:
            reward_overview = get_partner_reward_overview(db, wechat_openid=wechat_openid)
        except Exception:
            reward_overview = None

    available_points = _safe_float((reward_overview or {}).get("available_points"))
    net_commission = _safe_float((reward_overview or {}).get("net_settled_commission"))
    recent_asset_count = _get_recent_asset_count(db, int(account.id))

    lines = [
        "你的合伙人中心摘要：",
        "",
        f"合伙人编码：{account.partner_code}",
        f"当前等级：{getattr(account, 'tier_code', 'partner')}",
        f"当前状态：{getattr(account, 'status', 'active')}",
        f"分成比例：{_safe_float(getattr(account, 'share_rate', 0)):.2f}",
        f"可用积分：{available_points:.2f}",
        f"累计已结算佣金：¥{net_commission:.2f}",
        f"最近可用素材数：{recent_asset_count}",
    ]

    if getattr(account, "activation_fee_paid", False):
        lines.append(f"开通方式：{getattr(account, 'activated_via', 'unknown')}")

    lines.extend([
        "",
        "你可以直接回复：",
        "1）积分",
        "2）素材",
        "3）分享商品",
        "4）续费",
    ])
    return "\n".join(lines)
