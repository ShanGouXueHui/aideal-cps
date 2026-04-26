from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import text

from app.core.db import engine
from app.services.user_crypto_service import encrypt_text, hash_identity

load_dotenv(Path(".env"))


def _has_column(conn, table: str, column: str) -> bool:
    row = conn.execute(text(f"SHOW COLUMNS FROM `{table}` LIKE :column"), {"column": column}).first()
    return row is not None


def _has_index(conn, table: str, index_name: str) -> bool:
    rows = conn.execute(text(f"SHOW INDEX FROM `{table}` WHERE Key_name=:name"), {"name": index_name}).all()
    return bool(rows)


def _add_column(conn, table: str, column: str, ddl: str) -> None:
    if not _has_column(conn, table, column):
        conn.execute(text(f"ALTER TABLE `{table}` ADD COLUMN {ddl}"))
        print(f"added {table}.{column}")
    else:
        print(f"exists {table}.{column}")


def _add_index(conn, table: str, index_name: str, ddl: str) -> None:
    if not _has_index(conn, table, index_name):
        conn.execute(text(ddl))
        print(f"added index {table}.{index_name}")
    else:
        print(f"exists index {table}.{index_name}")


def main() -> None:
    with engine.begin() as conn:
        _add_column(conn, "users", "wechat_openid_hash", "`wechat_openid_hash` VARCHAR(64) NULL")
        _add_column(conn, "users", "wechat_openid_ciphertext", "`wechat_openid_ciphertext` TEXT NULL")
        _add_column(conn, "users", "wechat_unionid_hash", "`wechat_unionid_hash` VARCHAR(64) NULL")
        _add_column(conn, "users", "wechat_unionid_ciphertext", "`wechat_unionid_ciphertext` TEXT NULL")
        _add_column(conn, "users", "nickname_ciphertext", "`nickname_ciphertext` TEXT NULL")
        _add_column(conn, "users", "preferred_categories_ciphertext", "`preferred_categories_ciphertext` TEXT NULL")
        _add_column(conn, "users", "last_query_text_ciphertext", "`last_query_text_ciphertext` TEXT NULL")

        _add_column(conn, "click_logs", "wechat_openid_hash", "`wechat_openid_hash` VARCHAR(64) NULL")
        _add_column(conn, "click_logs", "wechat_openid_ciphertext", "`wechat_openid_ciphertext` TEXT NULL")

        _add_index(conn, "users", "ux_users_wechat_openid_hash", "CREATE UNIQUE INDEX ux_users_wechat_openid_hash ON users (wechat_openid_hash)")
        _add_index(conn, "users", "ix_users_wechat_unionid_hash", "CREATE INDEX ix_users_wechat_unionid_hash ON users (wechat_unionid_hash)")
        _add_index(conn, "click_logs", "ix_click_logs_wechat_openid_hash", "CREATE INDEX ix_click_logs_wechat_openid_hash ON click_logs (wechat_openid_hash)")

        users = conn.execute(text(
            "SELECT id, wechat_openid, wechat_unionid, nickname, preferred_categories, last_query_text "
            "FROM users"
        )).mappings().all()

        migrated_users = 0
        for row in users:
            updates = {}
            if row.get("wechat_openid"):
                updates["wechat_openid_hash"] = hash_identity(row["wechat_openid"])
                updates["wechat_openid_ciphertext"] = encrypt_text(row["wechat_openid"])
            if row.get("wechat_unionid"):
                updates["wechat_unionid_hash"] = hash_identity(row["wechat_unionid"])
                updates["wechat_unionid_ciphertext"] = encrypt_text(row["wechat_unionid"])
            if row.get("nickname"):
                updates["nickname_ciphertext"] = encrypt_text(row["nickname"])
            if row.get("preferred_categories"):
                updates["preferred_categories_ciphertext"] = encrypt_text(row["preferred_categories"])
            if row.get("last_query_text"):
                updates["last_query_text_ciphertext"] = encrypt_text(row["last_query_text"])

            if updates:
                sets = ", ".join([f"{k}=:{k}" for k in updates])
                payload = dict(updates)
                payload["id"] = row["id"]
                conn.execute(text(f"UPDATE users SET {sets} WHERE id=:id"), payload)
                migrated_users += 1

        clicks = conn.execute(text("SELECT id, wechat_openid FROM click_logs WHERE wechat_openid IS NOT NULL AND wechat_openid != ''")).mappings().all()
        migrated_clicks = 0
        for row in clicks:
            conn.execute(
                text(
                    "UPDATE click_logs "
                    "SET wechat_openid_hash=:h, wechat_openid_ciphertext=:c "
                    "WHERE id=:id"
                ),
                {"h": hash_identity(row["wechat_openid"]), "c": encrypt_text(row["wechat_openid"]), "id": row["id"]},
            )
            migrated_clicks += 1

        conn.execute(text(
            "UPDATE users "
            "SET wechat_openid=NULL, wechat_unionid=NULL, nickname=NULL, preferred_categories=NULL, last_query_text=NULL "
            "WHERE wechat_openid IS NOT NULL OR wechat_unionid IS NOT NULL OR nickname IS NOT NULL "
            "OR preferred_categories IS NOT NULL OR last_query_text IS NOT NULL"
        ))
        conn.execute(text("UPDATE click_logs SET wechat_openid=NULL WHERE wechat_openid IS NOT NULL"))

        print("migrated_users =", migrated_users)
        print("migrated_click_logs =", migrated_clicks)
        print("plaintext user identity/profile fields cleared")
        print("plaintext click openid fields cleared")


if __name__ == "__main__":
    main()
