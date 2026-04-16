"""add wechat recommend exposures manual

Revision ID: 20260416_0001
Revises: 20260414_0009
Create Date: 2026-04-16 04:40:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260416_0001"
down_revision = "20260414_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if "wechat_recommend_exposures" not in inspector.get_table_names():
        op.create_table(
            "wechat_recommend_exposures",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("openid_hash", sa.String(length=64), nullable=False),
            sa.Column("scene", sa.String(length=64), nullable=False),
            sa.Column("product_id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_wechat_recommend_exposures_id", "wechat_recommend_exposures", ["id"], unique=False)
        op.create_index("ix_wechat_recommend_exposures_openid_hash", "wechat_recommend_exposures", ["openid_hash"], unique=False)
        op.create_index("ix_wechat_recommend_exposures_scene", "wechat_recommend_exposures", ["scene"], unique=False)
        op.create_index("ix_wechat_recommend_exposures_product_id", "wechat_recommend_exposures", ["product_id"], unique=False)
        op.create_index("ix_wechat_recommend_exposures_created_at", "wechat_recommend_exposures", ["created_at"], unique=False)
        op.create_index(
            "ix_wechat_recommend_exposure_lookup",
            "wechat_recommend_exposures",
            ["openid_hash", "scene", "created_at"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if "wechat_recommend_exposures" in inspector.get_table_names():
        for idx in [
            "ix_wechat_recommend_exposure_lookup",
            "ix_wechat_recommend_exposures_created_at",
            "ix_wechat_recommend_exposures_product_id",
            "ix_wechat_recommend_exposures_scene",
            "ix_wechat_recommend_exposures_openid_hash",
            "ix_wechat_recommend_exposures_id",
        ]:
            try:
                op.drop_index(idx, table_name="wechat_recommend_exposures")
            except Exception:
                pass
        op.drop_table("wechat_recommend_exposures")
