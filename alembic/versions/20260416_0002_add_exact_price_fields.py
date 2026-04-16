"""add exact price fields

Revision ID: 20260416_0002
Revises: 20260416_0001
Create Date: 2026-04-16
"""

from alembic import op
import sqlalchemy as sa


revision = "20260416_0002"
down_revision = "20260416_0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("products", sa.Column("purchase_price", sa.Numeric(12, 2), nullable=True))
    op.add_column("products", sa.Column("basis_price", sa.Numeric(12, 2), nullable=True))
    op.add_column("products", sa.Column("basis_price_type", sa.Integer(), nullable=True))
    op.add_column("products", sa.Column("good_comments_share", sa.Float(), nullable=True))
    op.add_column("products", sa.Column("comment_count", sa.Integer(), nullable=True))
    op.add_column("products", sa.Column("price_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("products", sa.Column("is_exact_discount", sa.Boolean(), nullable=False, server_default=sa.text("0")))

    op.create_index("ix_products_basis_price_type", "products", ["basis_price_type"])
    op.create_index("ix_products_is_exact_discount", "products", ["is_exact_discount"])


def downgrade():
    op.drop_index("ix_products_is_exact_discount", table_name="products")
    op.drop_index("ix_products_basis_price_type", table_name="products")

    op.drop_column("products", "is_exact_discount")
    op.drop_column("products", "price_verified_at")
    op.drop_column("products", "comment_count")
    op.drop_column("products", "good_comments_share")
    op.drop_column("products", "basis_price_type")
    op.drop_column("products", "basis_price")
    op.drop_column("products", "purchase_price")
