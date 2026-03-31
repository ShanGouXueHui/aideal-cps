from sqlalchemy import text


def update_user_preference(db, user_id, category):
    db.execute(text("""
        INSERT INTO user_profile (user_id, prefer_category)
        VALUES (:uid, :cat)
        ON DUPLICATE KEY UPDATE prefer_category=:cat
    """), {"uid": user_id, "cat": category})
    db.commit()


def get_user_preference(db, user_id):
    row = db.execute(text("""
        SELECT prefer_category FROM user_profile WHERE user_id=:uid
    """), {"uid": user_id}).fetchone()

    if row:
        return row[0]

    return None
