"""add printer tools and nozzle inventory

Revision ID: c4f2b8a9d731
Revises: 2b6a1e4d9c30
Create Date: 2026-07-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c4f2b8a9d731"
down_revision: Union[str, Sequence[str], None] = "2b6a1e4d9c30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(inspector, table_name: str) -> set[str]:
    if table_name not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def _indexes(inspector, table_name: str) -> set[str]:
    if table_name not in inspector.get_table_names():
        return set()
    return {index["name"] for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "printer_tools" not in tables:
        op.create_table(
            "printer_tools",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("printer_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=140), nullable=False, server_default="Main print tool"),
            sa.Column("tool_order", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("max_hotend_c", sa.Float(), nullable=False, server_default="300"),
            sa.Column("nozzle_system", sa.String(length=120), nullable=False, server_default=""),
            sa.Column("supported_feed_routes", sa.String(length=220), nullable=False, server_default=""),
            sa.Column("notes", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["printer_id"], ["printer_presets.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_printer_tools_printer_id", "printer_tools", ["printer_id"], unique=False)

    if "nozzle_catalog_items" not in tables:
        op.create_table(
            "nozzle_catalog_items",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("display_name", sa.String(length=180), nullable=False),
            sa.Column("manufacturer", sa.String(length=120), nullable=False, server_default=""),
            sa.Column("model", sa.String(length=140), nullable=False, server_default=""),
            sa.Column("diameter_mm", sa.Float(), nullable=True),
            sa.Column("nozzle_material", sa.String(length=80), nullable=False, server_default=""),
            sa.Column("nozzle_system", sa.String(length=120), nullable=False, server_default=""),
            sa.Column("max_temp_c", sa.Float(), nullable=True),
            sa.Column("abrasive_ready", sa.Boolean(), nullable=True),
            sa.Column("carbon_fibre_suitable", sa.Boolean(), nullable=True),
            sa.Column("glass_fibre_suitable", sa.Boolean(), nullable=True),
            sa.Column("high_flow", sa.Boolean(), nullable=True),
            sa.Column("recommended_usage", sa.Text(), nullable=False, server_default=""),
            sa.Column("source_reference", sa.Text(), nullable=False, server_default=""),
            sa.Column("is_user_created", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.PrimaryKeyConstraint("id"),
        )

    nozzle_columns = _columns(inspector, "printer_nozzles")
    nozzle_additions = {
        "tool_id": sa.Column("tool_id", sa.Integer(), nullable=True),
        "catalog_item_id": sa.Column("catalog_item_id", sa.Integer(), nullable=True),
        "manufacturer": sa.Column("manufacturer", sa.String(length=120), nullable=False, server_default=""),
        "part_number": sa.Column("part_number", sa.String(length=140), nullable=False, server_default=""),
        "nozzle_system": sa.Column("nozzle_system", sa.String(length=120), nullable=False, server_default=""),
        "max_temp_c": sa.Column("max_temp_c", sa.Float(), nullable=True),
        "abrasive_ready": sa.Column("abrasive_ready", sa.Boolean(), nullable=True),
        "carbon_fibre_suitable": sa.Column("carbon_fibre_suitable", sa.Boolean(), nullable=True),
        "glass_fibre_suitable": sa.Column("glass_fibre_suitable", sa.Boolean(), nullable=True),
        "high_flow": sa.Column("high_flow", sa.Boolean(), nullable=True),
        "inventory_status": sa.Column("inventory_status", sa.String(length=40), nullable=False, server_default="spare"),
    }
    missing_nozzle_columns = [key for key in nozzle_additions if key not in nozzle_columns]
    if missing_nozzle_columns:
        with op.batch_alter_table("printer_nozzles", schema=None) as batch_op:
            for key in missing_nozzle_columns:
                batch_op.add_column(nozzle_additions[key])
        with op.batch_alter_table("printer_nozzles", schema=None) as batch_op:
            for key in missing_nozzle_columns:
                if key not in {"tool_id", "catalog_item_id", "max_temp_c", "abrasive_ready", "carbon_fibre_suitable", "glass_fibre_suitable", "high_flow"}:
                    batch_op.alter_column(key, server_default=None)

    nozzle_indexes = _indexes(inspector, "printer_nozzles")
    with op.batch_alter_table("printer_nozzles", schema=None) as batch_op:
        if "ix_printer_nozzles_tool_id" not in nozzle_indexes:
            batch_op.create_index("ix_printer_nozzles_tool_id", ["tool_id"], unique=False)
        if "ix_printer_nozzles_catalog_item_id" not in nozzle_indexes:
            batch_op.create_index("ix_printer_nozzles_catalog_item_id", ["catalog_item_id"], unique=False)

    catalog_count = bind.execute(sa.text("SELECT COUNT(*) FROM nozzle_catalog_items")).scalar_one()
    if catalog_count == 0:
        catalog = sa.table(
            "nozzle_catalog_items",
            sa.column("display_name"),
            sa.column("manufacturer"),
            sa.column("model"),
            sa.column("diameter_mm"),
            sa.column("nozzle_material"),
            sa.column("nozzle_system"),
            sa.column("max_temp_c"),
            sa.column("abrasive_ready"),
            sa.column("carbon_fibre_suitable"),
            sa.column("glass_fibre_suitable"),
            sa.column("high_flow"),
            sa.column("recommended_usage"),
            sa.column("source_reference"),
            sa.column("is_user_created"),
            sa.column("is_active"),
        )
        op.bulk_insert(
            catalog,
            [
                {
                    "display_name": "Generic brass nozzle",
                    "manufacturer": "Generic",
                    "model": "",
                    "diameter_mm": None,
                    "nozzle_material": "brass",
                    "nozzle_system": "unknown / user-defined",
                    "max_temp_c": None,
                    "abrasive_ready": False,
                    "carbon_fibre_suitable": False,
                    "glass_fibre_suitable": False,
                    "high_flow": None,
                    "recommended_usage": "General non-abrasive filaments. Confirm assembly temperature from the exact part.",
                    "source_reference": "Built-in generic category; not a manufacturer specification.",
                    "is_user_created": False,
                    "is_active": True,
                },
                {
                    "display_name": "Generic hardened steel nozzle",
                    "manufacturer": "Generic",
                    "model": "",
                    "diameter_mm": None,
                    "nozzle_material": "hardened steel",
                    "nozzle_system": "unknown / user-defined",
                    "max_temp_c": None,
                    "abrasive_ready": True,
                    "carbon_fibre_suitable": True,
                    "glass_fibre_suitable": True,
                    "high_flow": None,
                    "recommended_usage": "Abrasive-filled filaments when the exact nozzle and hotend are confirmed.",
                    "source_reference": "Built-in generic category; not a manufacturer specification.",
                    "is_user_created": False,
                    "is_active": True,
                },
                {
                    "display_name": "Generic stainless steel nozzle",
                    "manufacturer": "Generic",
                    "model": "",
                    "diameter_mm": None,
                    "nozzle_material": "stainless steel",
                    "nozzle_system": "unknown / user-defined",
                    "max_temp_c": None,
                    "abrasive_ready": False,
                    "carbon_fibre_suitable": False,
                    "glass_fibre_suitable": False,
                    "high_flow": None,
                    "recommended_usage": "Specialty non-abrasive use. Confirm temperature and wear limits from the exact part.",
                    "source_reference": "Built-in generic category; not a manufacturer specification.",
                    "is_user_created": False,
                    "is_active": True,
                },
                {
                    "display_name": "Generic ruby / abrasive-resistant nozzle",
                    "manufacturer": "Generic",
                    "model": "",
                    "diameter_mm": None,
                    "nozzle_material": "ruby / abrasive-resistant",
                    "nozzle_system": "unknown / user-defined",
                    "max_temp_c": None,
                    "abrasive_ready": True,
                    "carbon_fibre_suitable": True,
                    "glass_fibre_suitable": True,
                    "high_flow": None,
                    "recommended_usage": "Abrasive-filled filaments when the exact assembly is confirmed.",
                    "source_reference": "Built-in generic category; not a manufacturer specification.",
                    "is_user_created": False,
                    "is_active": True,
                },
            ],
        )

    printers = bind.execute(sa.text("SELECT id, nozzle_max_c FROM printer_presets")).mappings().all()
    for printer in printers:
        existing_tool_id = bind.execute(
            sa.text("SELECT id FROM printer_tools WHERE printer_id = :printer_id ORDER BY tool_order, id LIMIT 1"),
            {"printer_id": printer["id"]},
        ).scalar_one_or_none()
        if existing_tool_id is None:
            bind.execute(
                sa.text(
                    "INSERT INTO printer_tools "
                    "(printer_id, name, tool_order, is_active, max_hotend_c, nozzle_system, supported_feed_routes, notes, created_at) "
                    "VALUES (:printer_id, 'Main print tool', 1, 1, :max_hotend_c, '', 'standard filament path', '', CURRENT_TIMESTAMP)"
                ),
                {"printer_id": printer["id"], "max_hotend_c": printer["nozzle_max_c"] or 300},
            )
            existing_tool_id = bind.execute(
                sa.text("SELECT id FROM printer_tools WHERE printer_id = :printer_id ORDER BY tool_order, id LIMIT 1"),
                {"printer_id": printer["id"]},
            ).scalar_one()

        bind.execute(
            sa.text(
                "UPDATE printer_nozzles "
                "SET tool_id = :tool_id, "
                "inventory_status = CASE WHEN installed = 1 THEN 'installed' WHEN is_active = 1 THEN 'spare' ELSE 'archived' END "
                "WHERE printer_id = :printer_id AND tool_id IS NULL"
            ),
            {"tool_id": existing_tool_id, "printer_id": printer["id"]},
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "printer_nozzles" in tables:
        nozzle_columns = _columns(inspector, "printer_nozzles")
        nozzle_indexes = _indexes(inspector, "printer_nozzles")
        with op.batch_alter_table("printer_nozzles", schema=None) as batch_op:
            if "ix_printer_nozzles_catalog_item_id" in nozzle_indexes:
                batch_op.drop_index("ix_printer_nozzles_catalog_item_id")
            if "ix_printer_nozzles_tool_id" in nozzle_indexes:
                batch_op.drop_index("ix_printer_nozzles_tool_id")
            for column in [
                "inventory_status",
                "high_flow",
                "glass_fibre_suitable",
                "carbon_fibre_suitable",
                "abrasive_ready",
                "max_temp_c",
                "nozzle_system",
                "part_number",
                "manufacturer",
                "catalog_item_id",
                "tool_id",
            ]:
                if column in nozzle_columns:
                    batch_op.drop_column(column)

    if "nozzle_catalog_items" in tables:
        op.drop_table("nozzle_catalog_items")

    if "printer_tools" in tables:
        op.drop_index("ix_printer_tools_printer_id", table_name="printer_tools")
        op.drop_table("printer_tools")
