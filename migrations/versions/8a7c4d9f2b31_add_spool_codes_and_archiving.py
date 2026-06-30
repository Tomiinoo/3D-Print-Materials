"""add spool codes and archiving

Revision ID: 8a7c4d9f2b31
Revises: 177bf7f45345
Create Date: 2026-06-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8a7c4d9f2b31"
down_revision: Union[str, Sequence[str], None] = "177bf7f45345"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("filament_products", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "spool_code",
                sa.String(length=60),
                nullable=False,
                server_default="",
            )
        )
        batch_op.add_column(
            sa.Column(
                "is_active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            )
        )

    op.execute(
        """
        UPDATE filament_products
        SET spool_code = 'S-' || printf('%03d', id)
        WHERE spool_code = '' OR spool_code IS NULL
        """
    )

    with op.batch_alter_table("filament_products", schema=None) as batch_op:
        batch_op.alter_column("spool_code", server_default=None)
        batch_op.alter_column("is_active", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("filament_products", schema=None) as batch_op:
        batch_op.drop_column("is_active")
        batch_op.drop_column("spool_code")
