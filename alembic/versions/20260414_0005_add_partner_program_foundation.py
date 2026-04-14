"""add partner program foundation"""

from alembic import op
import sqlalchemy as sa


revision = "20260414_0005"
down_revision = "20260414_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "partner_accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("partner_code", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("tier_code", sa.String(length=32), nullable=False),
        sa.Column("share_rate", sa.Float(), nullable=False),
        sa.Column("cumulative_paid_gmv", sa.Numeric(12, 2), nullable=True, server_default="0"),
        sa.Column("cumulative_settled_commission", sa.Numeric(12, 2), nullable=True, server_default="0"),
        sa.Column("cumulative_reward_points", sa.Numeric(12, 2), nullable=True, server_default="0"),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.UniqueConstraint("user_id"),
        sa.UniqueConstraint("partner_code"),
    )
    op.create_index("ix_partner_accounts_id", "partner_accounts", ["id"])
    op.create_index("ix_partner_accounts_user_id", "partner_accounts", ["user_id"])
    op.create_index("ix_partner_accounts_partner_code", "partner_accounts", ["partner_code"])
    op.create_index("ix_partner_accounts_status", "partner_accounts", ["status"])
    op.create_index("ix_partner_accounts_tier_code", "partner_accounts", ["tier_code"])

    op.create_table(
        "partner_share_assets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("partner_account_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("asset_token", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("rank_tags", sa.String(length=255), nullable=True),
        sa.Column("short_url", sa.String(length=1000), nullable=True),
        sa.Column("long_url", sa.String(length=1000), nullable=True),
        sa.Column("buy_url", sa.String(length=1000), nullable=True),
        sa.Column("share_url", sa.String(length=1000), nullable=True),
        sa.Column("share_copy", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["partner_account_id"], ["partner_accounts.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.UniqueConstraint("asset_token"),
    )
    op.create_index("ix_partner_share_assets_id", "partner_share_assets", ["id"])
    op.create_index("ix_partner_share_assets_partner_account_id", "partner_share_assets", ["partner_account_id"])
    op.create_index("ix_partner_share_assets_product_id", "partner_share_assets", ["product_id"])
    op.create_index("ix_partner_share_assets_asset_token", "partner_share_assets", ["asset_token"])
    op.create_index("ix_partner_share_assets_status", "partner_share_assets", ["status"])

    op.create_table(
        "partner_share_clicks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("partner_account_id", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("request_source", sa.String(length=64), nullable=True),
        sa.Column("client_ip", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=500), nullable=True),
        sa.Column("referer", sa.String(length=1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["partner_account_id"], ["partner_accounts.id"]),
        sa.ForeignKeyConstraint(["asset_id"], ["partner_share_assets.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
    )
    op.create_index("ix_partner_share_clicks_id", "partner_share_clicks", ["id"])
    op.create_index("ix_partner_share_clicks_partner_account_id", "partner_share_clicks", ["partner_account_id"])
    op.create_index("ix_partner_share_clicks_asset_id", "partner_share_clicks", ["asset_id"])
    op.create_index("ix_partner_share_clicks_product_id", "partner_share_clicks", ["product_id"])


def downgrade() -> None:
    op.drop_index("ix_partner_share_clicks_product_id", table_name="partner_share_clicks")
    op.drop_index("ix_partner_share_clicks_asset_id", table_name="partner_share_clicks")
    op.drop_index("ix_partner_share_clicks_partner_account_id", table_name="partner_share_clicks")
    op.drop_index("ix_partner_share_clicks_id", table_name="partner_share_clicks")
    op.drop_table("partner_share_clicks")

    op.drop_index("ix_partner_share_assets_status", table_name="partner_share_assets")
    op.drop_index("ix_partner_share_assets_asset_token", table_name="partner_share_assets")
    op.drop_index("ix_partner_share_assets_product_id", table_name="partner_share_assets")
    op.drop_index("ix_partner_share_assets_partner_account_id", table_name="partner_share_assets")
    op.drop_index("ix_partner_share_assets_id", table_name="partner_share_assets")
    op.drop_table("partner_share_assets")

    op.drop_index("ix_partner_accounts_tier_code", table_name="partner_accounts")
    op.drop_index("ix_partner_accounts_status", table_name="partner_accounts")
    op.drop_index("ix_partner_accounts_partner_code", table_name="partner_accounts")
    op.drop_index("ix_partner_accounts_user_id", table_name="partner_accounts")
    op.drop_index("ix_partner_accounts_id", table_name="partner_accounts")
    op.drop_table("partner_accounts")
