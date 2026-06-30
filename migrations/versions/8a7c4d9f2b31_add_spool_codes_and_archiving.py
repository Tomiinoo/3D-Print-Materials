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
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    product_columns = {
        column["name"]
        for column in inspector.get_columns("filament_products")
    }
    add_spool_code = "spool_code" not in product_columns
    add_is_active = "is_active" not in product_columns

    if add_spool_code or add_is_active:
        with op.batch_alter_table("filament_products", schema=None) as batch_op:
            if add_spool_code:
                batch_op.add_column(
                    sa.Column(
                        "spool_code",
                        sa.String(length=60),
                        nullable=False,
                        server_default="",
                    )
                )
            if add_is_active:
                batch_op.add_column(
                    sa.Column(
                        "is_active",
                        sa.Boolean(),
                        nullable=False,
                        server_default=sa.true(),
                    )
                )

    if add_spool_code:
        op.execute(
            """
            UPDATE filament_products
            SET spool_code = 'S-' || printf('%03d', id)
            WHERE spool_code = '' OR spool_code IS NULL
            """
        )

    if add_spool_code or add_is_active:
        with op.batch_alter_table("filament_products", schema=None) as batch_op:
            if add_spool_code:
                batch_op.alter_column("spool_code", server_default=None)
            if add_is_active:
                batch_op.alter_column("is_active", server_default=None)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    product_columns = {
        column["name"]
        for column in inspector.get_columns("filament_products")
    }
    with op.batch_alter_table("filament_products", schema=None) as batch_op:
        if "is_active" in product_columns:
            batch_op.drop_column("is_active")
        if "spool_code" in product_columns:
            batch_op.drop_column("spool_code")
