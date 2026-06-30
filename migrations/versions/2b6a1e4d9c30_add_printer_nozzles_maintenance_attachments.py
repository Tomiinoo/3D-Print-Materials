"""add printer nozzles maintenance attachments

Revision ID: 2b6a1e4d9c30
Revises: 9c1d2e3f4a5b
Create Date: 2026-06-30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "2b6a1e4d9c30"
down_revision: Union[str, Sequence[str], None] = "9c1d2e3f4a5b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(inspector, table_name: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table_name)}


def _indexes(inspector, table_name: str) -> set[str]:
    return {index["name"] for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    printer_columns = _columns(inspector, "printer_presets")
    printer_additions = {
        "description": sa.Column("description", sa.String(length=260), nullable=False, server_default=""),
        "printer_type": sa.Column("printer_type", sa.String(length=80), nullable=False, server_default="FDM / FFF"),
        "chamber_max_c": sa.Column("chamber_max_c", sa.Float(), nullable=False, server_default="0"),
        "heated_chamber": sa.Column("heated_chamber", sa.Boolean(), nullable=False, server_default=sa.false()),
        "build_volume": sa.Column("build_volume", sa.String(length=120), nullable=False, server_default=""),
        "purchase_date": sa.Column("purchase_date", sa.Date(), nullable=True),
        "serial_number": sa.Column("serial_number", sa.String(length=120), nullable=False, server_default=""),
        "hours_before_tracking": sa.Column("hours_before_tracking", sa.Float(), nullable=False, server_default="0"),
    }
    missing_printer_columns = [key for key in printer_additions if key not in printer_columns]
    if missing_printer_columns:
        with op.batch_alter_table("printer_presets", schema=None) as batch_op:
            for key in missing_printer_columns:
                batch_op.add_column(printer_additions[key])
        with op.batch_alter_table("printer_presets", schema=None) as batch_op:
            for key in missing_printer_columns:
                if key != "purchase_date":
                    batch_op.alter_column(key, server_default=None)

    if "printer_nozzles" not in tables:
        op.create_table(
            "printer_nozzles",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("printer_id", sa.Integer(), nullable=False),
            sa.Column("label", sa.String(length=180), nullable=False),
            sa.Column("diameter_mm", sa.Float(), nullable=False),
            sa.Column("nozzle_material", sa.String(length=60), nullable=False),
            sa.Column("brand_product", sa.String(length=180), nullable=False),
            sa.Column("installed", sa.Boolean(), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("installed_on", sa.Date(), nullable=True),
            sa.Column("hours_before_tracking", sa.Float(), nullable=False),
            sa.Column("notes", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["printer_id"], ["printer_presets.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_printer_nozzles_printer_id", "printer_nozzles", ["printer_id"], unique=False)

    if "printer_maintenance" not in tables:
        op.create_table(
            "printer_maintenance",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("printer_id", sa.Integer(), nullable=False),
            sa.Column("maintenance_date", sa.Date(), nullable=False),
            sa.Column("maintenance_type", sa.String(length=60), nullable=False),
            sa.Column("component", sa.String(length=180), nullable=False),
            sa.Column("notes", sa.Text(), nullable=False),
            sa.Column("cost_eur", sa.Float(), nullable=True),
            sa.Column("printer_hours", sa.Float(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["printer_id"], ["printer_presets.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_printer_maintenance_printer_id", "printer_maintenance", ["printer_id"], unique=False)

    profile_columns = _columns(inspector, "print_profiles")
    profile_indexes = _indexes(inspector, "print_profiles")
    with op.batch_alter_table("print_profiles", schema=None) as batch_op:
        if "printer_nozzle_id" not in profile_columns:
            batch_op.add_column(sa.Column("printer_nozzle_id", sa.Integer(), nullable=True))
        if "print_duration_hours" not in profile_columns:
            batch_op.add_column(sa.Column("print_duration_hours", sa.Float(), nullable=True))
        if "printer_nozzle_id" not in profile_columns and "ix_print_profiles_printer_nozzle_id" not in profile_indexes:
            batch_op.create_index("ix_print_profiles_printer_nozzle_id", ["printer_nozzle_id"], unique=False)
        if "printer_nozzle_id" not in profile_columns:
            batch_op.create_foreign_key(
                "fk_print_profiles_printer_nozzle_id_printer_nozzles",
                "printer_nozzles",
                ["printer_nozzle_id"],
                ["id"],
            )

    if "print_attachments" not in tables:
        op.create_table(
            "print_attachments",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("print_profile_id", sa.Integer(), nullable=False),
            sa.Column("original_filename", sa.String(length=260), nullable=False),
            sa.Column("stored_relative_path", sa.String(length=500), nullable=False),
            sa.Column("file_category", sa.String(length=20), nullable=False),
            sa.Column("mime_type", sa.String(length=120), nullable=False),
            sa.Column("file_size", sa.Integer(), nullable=False),
            sa.Column("uploaded_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["print_profile_id"], ["print_profiles.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("stored_relative_path"),
        )
        op.create_index("ix_print_attachments_print_profile_id", "print_attachments", ["print_profile_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "print_attachments" in tables:
        op.drop_index("ix_print_attachments_print_profile_id", table_name="print_attachments")
        op.drop_table("print_attachments")

    profile_columns = _columns(inspector, "print_profiles")
    with op.batch_alter_table("print_profiles", schema=None) as batch_op:
        if "printer_nozzle_id" in profile_columns:
            batch_op.drop_constraint("fk_print_profiles_printer_nozzle_id_printer_nozzles", type_="foreignkey")
            batch_op.drop_index("ix_print_profiles_printer_nozzle_id")
            batch_op.drop_column("printer_nozzle_id")
        if "print_duration_hours" in profile_columns:
            batch_op.drop_column("print_duration_hours")

    if "printer_maintenance" in tables:
        op.drop_index("ix_printer_maintenance_printer_id", table_name="printer_maintenance")
        op.drop_table("printer_maintenance")

    if "printer_nozzles" in tables:
        op.drop_index("ix_printer_nozzles_printer_id", table_name="printer_nozzles")
        op.drop_table("printer_nozzles")

    printer_columns = _columns(inspector, "printer_presets")
    with op.batch_alter_table("printer_presets", schema=None) as batch_op:
        for column in [
            "hours_before_tracking",
            "serial_number",
            "purchase_date",
            "build_volume",
            "heated_chamber",
            "chamber_max_c",
            "printer_type",
            "description",
        ]:
            if column in printer_columns:
                batch_op.drop_column(column)
