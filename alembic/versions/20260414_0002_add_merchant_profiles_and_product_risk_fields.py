"""add merchant profiles and product risk fields

Revision ID: 20260414_0002
Revises: 20260413_0001
Create Date: 2026-04-14 11:30:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260414_0002"
down_revision = "20260413_0001"
branch_labels = None
depends_on = None


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("merchant_profiles"):
        op.create_table(
            "merchant_profiles",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("shop_id", sa.String(length=64), nullable=False),
            sa.Column("shop_name", sa.String(length=255), nullable=True),
            sa.Column("shop_label", sa.String(length=50), nullable=True),
            sa.Column("owner", sa.String(length=20), nullable=True),
            sa.Column("user_evaluate_score", sa.Float(), nullable=True),
            sa.Column("after_service_score", sa.Float(), nullable=True),
            sa.Column("logistics_lvyue_score", sa.Float(), nullable=True),
            sa.Column("score_rank_rate", sa.Float(), nullable=True),
            sa.Column("merchant_health_score", sa.Float(), nullable=True),
            sa.Column("risk_flags", sa.String(length=255), nullable=True),
            sa.Column("recommendable", sa.Boolean(), nullable=True, server_default=sa.text("1")),
            sa.Column("source", sa.String(length=20), nullable=True, server_default="jd"),
            sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_merchant_profiles_shop_id", "merchant_profiles", ["shop_id"], unique=True)
        op.create_index("ix_merchant_profiles_recommendable", "merchant_profiles", ["recommendable"], unique=False)

    if not _has_column(inspector, "products", "merchant_health_score"):
        op.add_column("products", sa.Column("merchant_health_score", sa.Float(), nullable=True))
    if not _has_column(inspector, "products", "merchant_risk_flags"):
        op.add_column("products", sa.Column("merchant_risk_flags", sa.String(length=255), nullable=True))
    if not _has_column(inspector, "products", "merchant_recommendable"):
        op.add_column("products", sa.Column("merchant_recommendable", sa.Boolean(), nullable=True, server_default=sa.text("1")))

    indexes = {idx["name"] for idx in inspector.get_indexes("products")}
    if "ix_products_merchant_recommendable" not in indexes:
        op.create_index("ix_products_merchant_recommendable", "products", ["merchant_recommendable"], unique=False)
    if "ix_products_merchant_health_score" not in indexes:
        op.create_index("ix_products_merchant_health_score", "products", ["merchant_health_score"], unique=False)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    indexes = {idx["name"] for idx in inspector.get_indexes("products")}
    if "ix_products_merchant_health_score" in indexes:
        op.drop_index("ix_products_merchant_health_score", table_name="products")
    if "ix_products_merchant_recommendable" in indexes:
        op.drop_index("ix_products_merchant_recommendable", table_name="products")

    columns = {col["name"] for col in inspector.get_columns("products")}
    for name in ["merchant_recommendable", "merchant_risk_flags", "merchant_health_score"]:
        if name in columns:
            op.drop_column("products", name)

    if inspector.has_table("merchant_profiles"):
        idxs = {idx["name"] for idx in inspector.get_indexes("merchant_profiles")}
        if "ix_merchant_profiles_recommendable" in idxs:
            op.drop_index("ix_merchant_profiles_recommendable", table_name="merchant_profiles")
        if "ix_merchant_profiles_shop_id" in idxs:
            op.drop_index("ix_merchant_profiles_shop_id", table_name="merchant_profiles")
        op.drop_table("merchant_profiles")
