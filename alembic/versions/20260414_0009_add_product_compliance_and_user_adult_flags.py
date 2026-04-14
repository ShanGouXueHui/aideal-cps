"""add product compliance and user adult flags"""

from alembic import op
import sqlalchemy as sa


revision = "20260414_0009"
down_revision = "20260414_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("products", sa.Column("compliance_level", sa.String(length=32), nullable=False, server_default="normal"))
    op.add_column("products", sa.Column("age_gate_required", sa.Boolean(), nullable=False, server_default="0"))
    op.add_column("products", sa.Column("allow_proactive_push", sa.Boolean(), nullable=False, server_default="1"))
    op.add_column("products", sa.Column("allow_partner_share", sa.Boolean(), nullable=False, server_default="1"))
    op.add_column("products", sa.Column("compliance_notes", sa.String(length=500), nullable=True))
    op.create_index("ix_products_compliance_level", "products", ["compliance_level"])
    op.create_index("ix_products_age_gate_required", "products", ["age_gate_required"])
    op.create_index("ix_products_allow_proactive_push", "products", ["allow_proactive_push"])
    op.create_index("ix_products_allow_partner_share", "products", ["allow_partner_share"])

    op.add_column("users", sa.Column("adult_verified", sa.Boolean(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("adult_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("verification_source", sa.String(length=32), nullable=True))
    op.create_index("ix_users_adult_verified", "users", ["adult_verified"])


def downgrade() -> None:
    op.drop_index("ix_users_adult_verified", table_name="users")
    op.drop_column("users", "verification_source")
    op.drop_column("users", "adult_verified_at")
    op.drop_column("users", "adult_verified")

    op.drop_index("ix_products_allow_partner_share", table_name="products")
    op.drop_index("ix_products_allow_proactive_push", table_name="products")
    op.drop_index("ix_products_age_gate_required", table_name="products")
    op.drop_index("ix_products_compliance_level", table_name="products")
    op.drop_column("products", "compliance_notes")
    op.drop_column("products", "allow_partner_share")
    op.drop_column("products", "allow_proactive_push")
    op.drop_column("products", "age_gate_required")
    op.drop_column("products", "compliance_level")
