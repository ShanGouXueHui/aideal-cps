"""add partner redemption flow"""

from alembic import op
import sqlalchemy as sa


revision = "20260414_0008"
down_revision = "20260414_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("partner_accounts", sa.Column("activation_fee_paid", sa.Boolean(), nullable=False, server_default="0"))
    op.add_column("partner_accounts", sa.Column("activation_fee_paid_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("partner_accounts", sa.Column("activated_via", sa.String(length=32), nullable=True))

    op.create_table(
        "partner_point_redemptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("partner_account_id", sa.Integer(), nullable=False),
        sa.Column("item_code", sa.String(length=64), nullable=False),
        sa.Column("item_name", sa.String(length=255), nullable=False),
        sa.Column("scene_code", sa.String(length=64), nullable=False),
        sa.Column("cash_price_rmb", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("points_used", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("cash_due_rmb", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("fulfill_mode", sa.String(length=32), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("fulfilled_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["partner_account_id"], ["partner_accounts.id"]),
    )
    op.create_index("ix_partner_point_redemptions_id", "partner_point_redemptions", ["id"])
    op.create_index("ix_partner_point_redemptions_partner_account_id", "partner_point_redemptions", ["partner_account_id"])
    op.create_index("ix_partner_point_redemptions_item_code", "partner_point_redemptions", ["item_code"])
    op.create_index("ix_partner_point_redemptions_scene_code", "partner_point_redemptions", ["scene_code"])
    op.create_index("ix_partner_point_redemptions_status", "partner_point_redemptions", ["status"])


def downgrade() -> None:
    op.drop_index("ix_partner_point_redemptions_status", table_name="partner_point_redemptions")
    op.drop_index("ix_partner_point_redemptions_scene_code", table_name="partner_point_redemptions")
    op.drop_index("ix_partner_point_redemptions_item_code", table_name="partner_point_redemptions")
    op.drop_index("ix_partner_point_redemptions_partner_account_id", table_name="partner_point_redemptions")
    op.drop_index("ix_partner_point_redemptions_id", table_name="partner_point_redemptions")
    op.drop_table("partner_point_redemptions")

    op.drop_column("partner_accounts", "activated_via")
    op.drop_column("partner_accounts", "activation_fee_paid_at")
    op.drop_column("partner_accounts", "activation_fee_paid")
