"""add encrypted user identity fields

Revision ID: 20260426_0001
Revises:
Create Date: 2026-04-26
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260426_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Production uses scripts/apply_user_identity_encryption_migration.py for idempotent
    # MySQL-safe migration and plaintext cleanup. This revision documents the schema intent.
    pass


def downgrade() -> None:
    pass
