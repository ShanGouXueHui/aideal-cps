"""upgrade click logs for attribution

Revision ID: 20260414_0003
Revises: 20260414_0002
Create Date: 2026-04-14 20:10:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260414_0003"
down_revision = "20260414_0002"
branch_labels = None
depends_on = None


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_column(inspector, "click_logs", "wechat_openid"):
        op.add_column("click_logs", sa.Column("wechat_openid", sa.String(length=64), nullable=True))
    if not _has_column(inspector, "click_logs", "request_source"):
        op.add_column("click_logs", sa.Column("request_source", sa.String(length=50), nullable=True))
    if not _has_column(inspector, "click_logs", "scene"):
        op.add_column("click_logs", sa.Column("scene", sa.String(length=50), nullable=True))
    if not _has_column(inspector, "click_logs", "slot"):
        op.add_column("click_logs", sa.Column("slot", sa.Integer(), nullable=True))
    if not _has_column(inspector, "click_logs", "trace_id"):
        op.add_column("click_logs", sa.Column("trace_id", sa.String(length=64), nullable=True))
    if not _has_column(inspector, "click_logs", "final_url"):
        op.add_column("click_logs", sa.Column("final_url", sa.String(length=1000), nullable=True))
    if not _has_column(inspector, "click_logs", "material_url"):
        op.add_column("click_logs", sa.Column("material_url", sa.String(length=1000), nullable=True))
    if not _has_column(inspector, "click_logs", "short_url"):
        op.add_column("click_logs", sa.Column("short_url", sa.String(length=1000), nullable=True))
    if not _has_column(inspector, "click_logs", "client_ip"):
        op.add_column("click_logs", sa.Column("client_ip", sa.String(length=64), nullable=True))
    if not _has_column(inspector, "click_logs", "user_agent"):
        op.add_column("click_logs", sa.Column("user_agent", sa.String(length=500), nullable=True))
    if not _has_column(inspector, "click_logs", "referer"):
        op.add_column("click_logs", sa.Column("referer", sa.String(length=1000), nullable=True))

    indexes = {idx["name"] for idx in inspector.get_indexes("click_logs")}
    if "ix_click_logs_trace_id" not in indexes:
        op.create_index("ix_click_logs_trace_id", "click_logs", ["trace_id"], unique=False)
    if "ix_click_logs_scene" not in indexes:
        op.create_index("ix_click_logs_scene", "click_logs", ["scene"], unique=False)
    if "ix_click_logs_slot" not in indexes:
        op.create_index("ix_click_logs_slot", "click_logs", ["slot"], unique=False)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    indexes = {idx["name"] for idx in inspector.get_indexes("click_logs")}
    if "ix_click_logs_slot" in indexes:
        op.drop_index("ix_click_logs_slot", table_name="click_logs")
    if "ix_click_logs_scene" in indexes:
        op.drop_index("ix_click_logs_scene", table_name="click_logs")
    if "ix_click_logs_trace_id" in indexes:
        op.drop_index("ix_click_logs_trace_id", table_name="click_logs")

    columns = {col["name"] for col in inspector.get_columns("click_logs")}
    for name in [
        "referer",
        "user_agent",
        "client_ip",
        "short_url",
        "material_url",
        "final_url",
        "trace_id",
        "slot",
        "scene",
        "request_source",
        "wechat_openid",
    ]:
        if name in columns:
            op.drop_column("click_logs", name)
