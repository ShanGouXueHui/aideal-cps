"""add partner reward ledger"""

from alembic import op
import sqlalchemy as sa


revision = "20260414_0007"
down_revision = "20260414_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "partner_reward_ledgers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("partner_account_id", sa.Integer(), nullable=False),
        sa.Column("order_ref", sa.String(length=128), nullable=True),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("click_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("applied_share_rate", sa.Float(), nullable=True),
        sa.Column("commission_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("reward_base_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("points_delta", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["partner_account_id"], ["partner_accounts.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
    )
    op.create_index("ix_partner_reward_ledgers_id", "partner_reward_ledgers", ["id"])
    op.create_index("ix_partner_reward_ledgers_partner_account_id", "partner_reward_ledgers", ["partner_account_id"])
    op.create_index("ix_partner_reward_ledgers_order_ref", "partner_reward_ledgers", ["order_ref"])
    op.create_index("ix_partner_reward_ledgers_product_id", "partner_reward_ledgers", ["product_id"])
    op.create_index("ix_partner_reward_ledgers_click_id", "partner_reward_ledgers", ["click_id"])
    op.create_index("ix_partner_reward_ledgers_event_type", "partner_reward_ledgers", ["event_type"])


def downgrade() -> None:
    op.drop_index("ix_partner_reward_ledgers_event_type", table_name="partner_reward_ledgers")
    op.drop_index("ix_partner_reward_ledgers_click_id", table_name="partner_reward_ledgers")
    op.drop_index("ix_partner_reward_ledgers_product_id", table_name="partner_reward_ledgers")
    op.drop_index("ix_partner_reward_ledgers_order_ref", table_name="partner_reward_ledgers")
    op.drop_index("ix_partner_reward_ledgers_partner_account_id", table_name="partner_reward_ledgers")
    op.drop_index("ix_partner_reward_ledgers_id", table_name="partner_reward_ledgers")
    op.drop_table("partner_reward_ledgers")
