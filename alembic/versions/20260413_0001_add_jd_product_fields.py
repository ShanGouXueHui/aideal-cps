"""add jd product fields

Revision ID: 20260413_0001
Revises:
Create Date: 2026-04-13 23:59:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260413_0001"
down_revision = "aef275172fa1"
branch_labels = None
depends_on = None


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    columns = inspector.get_columns(table_name)
    return any(col["name"] == column_name for col in columns)


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_column(inspector, "products", "material_url"):
        op.add_column("products", sa.Column("material_url", sa.String(length=500), nullable=True))
    if not _has_column(inspector, "products", "short_url"):
        op.add_column("products", sa.Column("short_url", sa.String(length=500), nullable=True))
    if not _has_column(inspector, "products", "elite_id"):
        op.add_column("products", sa.Column("elite_id", sa.Integer(), nullable=True))
    if not _has_column(inspector, "products", "elite_name"):
        op.add_column("products", sa.Column("elite_name", sa.String(length=100), nullable=True))
    if not _has_column(inspector, "products", "shop_id"):
        op.add_column("products", sa.Column("shop_id", sa.String(length=64), nullable=True))
    if not _has_column(inspector, "products", "owner"):
        op.add_column("products", sa.Column("owner", sa.String(length=20), nullable=True))
    if not _has_column(inspector, "products", "last_sync_at"):
        op.add_column("products", sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True))

    indexes = {idx["name"] for idx in inspector.get_indexes("products")}
    if "ix_products_elite_id" not in indexes:
        op.create_index("ix_products_elite_id", "products", ["elite_id"], unique=False)
    if "ix_products_shop_id" not in indexes:
        op.create_index("ix_products_shop_id", "products", ["shop_id"], unique=False)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    indexes = {idx["name"] for idx in inspector.get_indexes("products")}
    if "ix_products_shop_id" in indexes:
        op.drop_index("ix_products_shop_id", table_name="products")
    if "ix_products_elite_id" in indexes:
        op.drop_index("ix_products_elite_id", table_name="products")

    columns = {col["name"] for col in inspector.get_columns("products")}
    for name in ["last_sync_at", "owner", "shop_id", "elite_name", "elite_id", "short_url", "material_url"]:
        if name in columns:
            op.drop_column("products", name)
