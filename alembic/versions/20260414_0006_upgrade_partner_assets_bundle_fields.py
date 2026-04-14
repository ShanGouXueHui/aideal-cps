"""upgrade partner assets bundle fields"""

from alembic import op
import sqlalchemy as sa


revision = "20260414_0006"
down_revision = "20260414_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("partner_share_assets", sa.Column("buy_copy", sa.Text(), nullable=True))
    op.add_column("partner_share_assets", sa.Column("buy_qr_svg_path", sa.String(length=1000), nullable=True))
    op.add_column("partner_share_assets", sa.Column("share_qr_svg_path", sa.String(length=1000), nullable=True))
    op.add_column("partner_share_assets", sa.Column("poster_svg_path", sa.String(length=1000), nullable=True))
    op.add_column("partner_share_assets", sa.Column("j_command_short", sa.String(length=255), nullable=True))
    op.add_column("partner_share_assets", sa.Column("j_command_long", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("partner_share_assets", "j_command_long")
    op.drop_column("partner_share_assets", "j_command_short")
    op.drop_column("partner_share_assets", "poster_svg_path")
    op.drop_column("partner_share_assets", "share_qr_svg_path")
    op.drop_column("partner_share_assets", "buy_qr_svg_path")
    op.drop_column("partner_share_assets", "buy_copy")
