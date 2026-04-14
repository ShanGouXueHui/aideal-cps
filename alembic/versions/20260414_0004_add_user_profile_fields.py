"""add user profile fields

Revision ID: 20260414_0004
Revises: 20260414_0003
Create Date: 2026-04-14 22:20:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260414_0004"
down_revision = "20260414_0003"
branch_labels = None
depends_on = None


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_column(inspector, "users", "first_subscribe_at"):
        op.add_column("users", sa.Column("first_subscribe_at", sa.DateTime(timezone=True), nullable=True))
    if not _has_column(inspector, "users", "last_interaction_at"):
        op.add_column("users", sa.Column("last_interaction_at", sa.DateTime(timezone=True), nullable=True))
    if not _has_column(inspector, "users", "interaction_count"):
        op.add_column("users", sa.Column("interaction_count", sa.Integer(), nullable=True, server_default="0"))
    if not _has_column(inspector, "users", "price_sensitive_score"):
        op.add_column("users", sa.Column("price_sensitive_score", sa.Float(), nullable=True, server_default="0"))
    if not _has_column(inspector, "users", "quality_sensitive_score"):
        op.add_column("users", sa.Column("quality_sensitive_score", sa.Float(), nullable=True, server_default="0"))
    if not _has_column(inspector, "users", "sales_sensitive_score"):
        op.add_column("users", sa.Column("sales_sensitive_score", sa.Float(), nullable=True, server_default="0"))
    if not _has_column(inspector, "users", "self_operated_sensitive_score"):
        op.add_column("users", sa.Column("self_operated_sensitive_score", sa.Float(), nullable=True, server_default="0"))
    if not _has_column(inspector, "users", "preferred_categories"):
        op.add_column("users", sa.Column("preferred_categories", sa.Text(), nullable=True))
    if not _has_column(inspector, "users", "last_query_text"):
        op.add_column("users", sa.Column("last_query_text", sa.Text(), nullable=True))
    if not _has_column(inspector, "users", "morning_push_enabled"):
        op.add_column("users", sa.Column("morning_push_enabled", sa.Boolean(), nullable=True, server_default=sa.text("1")))
    if not _has_column(inspector, "users", "morning_push_hour"):
        op.add_column("users", sa.Column("morning_push_hour", sa.Integer(), nullable=True, server_default="8"))
    if not _has_column(inspector, "users", "last_push_at"):
        op.add_column("users", sa.Column("last_push_at", sa.DateTime(timezone=True), nullable=True))

    indexes = {idx["name"] for idx in inspector.get_indexes("users")}
    if "ix_users_morning_push_enabled" not in indexes:
        op.create_index("ix_users_morning_push_enabled", "users", ["morning_push_enabled"], unique=False)
    if "ix_users_morning_push_hour" not in indexes:
        op.create_index("ix_users_morning_push_hour", "users", ["morning_push_hour"], unique=False)
    if "ix_users_last_interaction_at" not in indexes:
        op.create_index("ix_users_last_interaction_at", "users", ["last_interaction_at"], unique=False)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    indexes = {idx["name"] for idx in inspector.get_indexes("users")}
    for idx_name in ["ix_users_last_interaction_at", "ix_users_morning_push_hour", "ix_users_morning_push_enabled"]:
        if idx_name in indexes:
            op.drop_index(idx_name, table_name="users")

    columns = {col["name"] for col in inspector.get_columns("users")}
    for column_name in [
        "last_push_at",
        "morning_push_hour",
        "morning_push_enabled",
        "last_query_text",
        "preferred_categories",
        "self_operated_sensitive_score",
        "sales_sensitive_score",
        "quality_sensitive_score",
        "price_sensitive_score",
        "interaction_count",
        "last_interaction_at",
        "first_subscribe_at"
    ]:
        if column_name in columns:
            op.drop_column("users", column_name)
