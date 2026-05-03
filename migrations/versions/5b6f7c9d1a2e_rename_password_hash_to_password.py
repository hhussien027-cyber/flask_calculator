"""rename password_hash to password

Revision ID: 5b6f7c9d1a2e
Revises: 39b82a1b5bda
Create Date: 2026-05-01 23:22:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = "5b6f7c9d1a2e"
down_revision = "39b82a1b5bda"
branch_labels = None
depends_on = None


def _rename_column_if_exists(table_name, from_name, to_name):
    bind = op.get_bind()
    inspector = inspect(bind)
    table_names = inspector.get_table_names()
    if table_name not in table_names:
        return

    column_names = {column["name"] for column in inspector.get_columns(table_name)}
    if from_name not in column_names or to_name in column_names:
        return

    op.alter_column(
        table_name,
        from_name,
        new_column_name=to_name,
        existing_type=sa.String(length=255),
        existing_nullable=False,
    )


def upgrade():
    _rename_column_if_exists("users", "password_hash", "password")
    _rename_column_if_exists("user", "password_hash", "password")


def downgrade():
    _rename_column_if_exists("users", "password", "password_hash")
    _rename_column_if_exists("user", "password", "password_hash")
