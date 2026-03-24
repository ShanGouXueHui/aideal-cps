from datetime import date, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import text

DAILY_LIMIT = 50  # ✅ 正式版本


def cleanup_old_usage(db: Session):
    # 🧹 删除7天前数据（可调）
    db.execute(text("""
        DELETE FROM user_ai_usage
        WHERE date < :d
    """), {"d": date.today() - timedelta(days=7)})
    db.commit()


def check_and_increase_usage(db: Session, user_id: int):
    today = date.today()

    # 🧹 每次调用顺带清理（轻量级）
    cleanup_old_usage(db)

    row = db.execute(text("""
        SELECT id, request_count, date
        FROM user_ai_usage
        WHERE user_id=:uid
        ORDER BY date DESC
        LIMIT 1
    """), {"uid": user_id}).fetchone()

    # 1️⃣ 没记录
    if not row:
        db.execute(text("""
            INSERT INTO user_ai_usage (user_id, date, request_count)
            VALUES (:uid, :d, 1)
        """), {"uid": user_id, "d": today})
        db.commit()
        return True

    # 2️⃣ 跨天 → 自动重置
    if row.date != today:
        db.execute(text("""
            INSERT INTO user_ai_usage (user_id, date, request_count)
            VALUES (:uid, :d, 1)
        """), {"uid": user_id, "d": today})
        db.commit()
        return True

    # 3️⃣ 超限
    if row.request_count >= DAILY_LIMIT:
        return False

    # 4️⃣ 正常累加
    db.execute(text("""
        UPDATE user_ai_usage
        SET request_count = request_count + 1
        WHERE id = :id
    """), {"id": row.id})

    db.commit()
    return True
