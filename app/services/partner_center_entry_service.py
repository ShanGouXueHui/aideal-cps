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


def _get_partner_center_entry_reply_legacy(db: Session, wechat_openid: str) -> str:
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

def _partner_center_commercial_entry_text() -> str:
    return (
        "合伙人中心｜智省优选\n\n"
        "你当前还没有开通合伙人身份。\n\n"
        "适合谁：\n"
        "1）经常给家里、朋友、同事买日用品的人\n"
        "2）愿意把自己觉得划算的商品顺手分享出去的人\n"
        "3）希望有一个更省事的选品、素材和订单记录入口的人\n\n"
        "开通后主要能做什么：\n"
        "1）获取更适合分享的商品推荐\n"
        "2）查看可分享商品、素材和转链入口\n"
        "3）查看订单、返佣和合伙人规则\n"
        "4）后续接入更完整的分享数据和用户偏好分析\n\n"
        "开通方式：\n"
        "1）直接开通：100 元\n"
        "2）自动升级：累计采购满 10000 元\n\n"
        "重要说明：\n"
        "合伙人收益以京东联盟实际结算为准；退货、取消、无效订单、平台规则调整等情况可能不产生收益。"
        "这里不承诺固定收益，也不建议为返佣而非理性消费。\n\n"
        "你可以继续回复：\n"
        "1）合伙人规则\n"
        "2）开通合伙人\n"
        "3）今日推荐\n"
    )


def get_partner_center_entry_reply(db, wechat_openid: str) -> str:
    """Commercial partner center entry.

    Keeps legacy payload for already-opened/recognized partner states, but replaces
    the unopened hard prompt with a commercial, compliant explanation.
    """  # PARTNER_CENTER_COMMERCIAL_WRAPPER_GATE
    legacy_text = ""
    try:
        legacy_text = str(_get_partner_center_entry_reply_legacy(db, wechat_openid) or "").strip()
    except Exception:
        legacy_text = ""

    unopened_markers = [
        "你还没有开通合伙人身份",
        "当前开通方式",
        "直接付费 100 元开通",
        "累计采购满 10000 元自动升级",
    ]

    if legacy_text and not any(marker in legacy_text for marker in unopened_markers):
        if "京东联盟实际结算" not in legacy_text and "不承诺固定收益" not in legacy_text:
            return (
                legacy_text.rstrip()
                + "\n\n说明：合伙人收益以京东联盟实际结算为准；退货、取消、无效订单、平台规则调整等情况可能不产生收益，不承诺固定收益。"
            )
        return legacy_text

    return _partner_center_commercial_entry_text()


def get_partner_center_entry_text_reply(db, wechat_openid: str) -> str:
    return get_partner_center_entry_reply(db, wechat_openid)


def build_partner_center_entry_text_reply(db, wechat_openid: str) -> str:
    return get_partner_center_entry_reply(db, wechat_openid)
