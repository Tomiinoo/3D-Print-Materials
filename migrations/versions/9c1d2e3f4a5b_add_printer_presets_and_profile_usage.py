"""add printer presets and print profile usage

Revision ID: 9c1d2e3f4a5b
Revises: 8a7c4d9f2b31
Create Date: 2026-06-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9c1d2e3f4a5b"
down_revision: Union[str, Sequence[str], None] = "8a7c4d9f2b31"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "printer_presets" not in tables:
        op.create_table(
            "printer_presets",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("slug", sa.String(length=100), nullable=False),
            sa.Column("name", sa.String(length=160), nullable=False),
            sa.Column("nozzle_max_c", sa.Float(), nullable=False),
            sa.Column("bed_max_c", sa.Float(), nullable=False),
            sa.Column("enclosed", sa.Boolean(), nullable=False),
            sa.Column("direct_drive", sa.Boolean(), nullable=False),
            sa.Column("supports_flexible", sa.Boolean(), nullable=False),
            sa.Column("ams_capable", sa.Boolean(), nullable=False),
            sa.Column("notes", sa.Text(), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            op.f("ix_printer_presets_slug"),
            "printer_presets",
            ["slug"],
            unique=True,
        )

    profile_columns = {
        column["name"]
        for column in inspector.get_columns("print_profiles")
    }
    profile_indexes = {
        index["name"]
        for index in inspector.get_indexes("print_profiles")
    }

    with op.batch_alter_table("print_profiles", schema=None) as batch_op:
        if "printer_id" not in profile_columns:
            batch_op.add_column(sa.Column("printer_id", sa.Integer(), nullable=True))
        if "filament_used_g" not in profile_columns:
            batch_op.add_column(
                sa.Column(
                    "filament_used_g",
                    sa.Float(),
                    nullable=False,
                    server_default="0",
                )
            )
        if "printer_id" not in profile_columns and "ix_print_profiles_printer_id" not in profile_indexes:
            batch_op.create_index(
                "ix_print_profiles_printer_id",
                ["printer_id"],
                unique=False,
            )
        if "printer_id" not in profile_columns:
            batch_op.create_foreign_key(
                "fk_print_profiles_printer_id_printer_presets",
                "printer_presets",
                ["printer_id"],
                ["id"],
            )

    if "filament_used_g" not in profile_columns:
        with op.batch_alter_table("print_profiles", schema=None) as batch_op:
            batch_op.alter_column("filament_used_g", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("print_profiles", schema=None) as batch_op:
        batch_op.drop_constraint(
            "fk_print_profiles_printer_id_printer_presets",
            type_="foreignkey",
        )
        batch_op.drop_index("ix_print_profiles_printer_id")
        batch_op.drop_column("filament_used_g")
        batch_op.drop_column("printer_id")

    op.drop_index(op.f("ix_printer_presets_slug"), table_name="printer_presets")
    op.drop_table("printer_presets")
