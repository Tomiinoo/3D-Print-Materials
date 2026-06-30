"""migrate prototype material references

Revision ID: 177bf7f45345
Revises: 5c97e2fd405e
Create Date: 2026-06-28

"""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "177bf7f45345"
down_revision: Union[str, Sequence[str], None] = "5c97e2fd405e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


IMPORT_SOURCE_TYPE = "legacy_import"
IMPORT_SOURCE_TITLE = "Material Lab prototype reference import"
IMPORT_CONFIDENCE = "low"
IMPORT_STATE = "unknown"


PROPERTY_SPECS: dict[str, dict[str, str]] = {
    "density_g_cm3": {
        "key": "density",
        "name": "Density",
        "category": "Physical",
        "value_type": "numeric",
        "default_unit": "g/cm³",
        "description": "Mass per unit volume.",
    },
    "hdt_c": {
        "key": "heat_deflection_temperature",
        "name": "Heat deflection temperature",
        "category": "Thermal",
        "value_type": "numeric",
        "default_unit": "°C",
        "description": "Heat deflection temperature; exact load and standard belong in the source record.",
    },
    "continuous_service_c": {
        "key": "continuous_service_temperature",
        "name": "Continuous service temperature",
        "category": "Thermal",
        "value_type": "numeric",
        "default_unit": "°C",
        "description": "Legacy continuous-service guidance; verify against a product-specific source for engineering use.",
    },
    "tensile_mpa": {
        "key": "tensile_strength",
        "name": "Tensile strength",
        "category": "Mechanical",
        "value_type": "numeric_or_range",
        "default_unit": "MPa",
        "description": "Tensile strength. Legacy values may be ranges or text and are preserved without invented parsing.",
    },
    "modulus_gpa": {
        "key": "tensile_modulus",
        "name": "Tensile modulus",
        "category": "Mechanical",
        "value_type": "numeric_or_range",
        "default_unit": "GPa",
        "description": "Tensile modulus. Legacy values may be ranges or text and are preserved without invented parsing.",
    },
    "impact_note": {
        "key": "impact_resistance_note",
        "name": "Impact resistance note",
        "category": "Mechanical",
        "value_type": "text",
        "default_unit": "",
        "description": "Qualitative impact-resistance note retained from the prototype.",
    },
    "shrinkage_note": {
        "key": "shrinkage_note",
        "name": "Shrinkage note",
        "category": "Print behaviour",
        "value_type": "text",
        "default_unit": "",
        "description": "Qualitative shrinkage note retained from the prototype.",
    },
}


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "unclassified"


def load_json(raw: str | None) -> dict[str, Any]:
    try:
        parsed = json.loads(raw or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def is_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def legacy_note(source_notes: str) -> str:
    note = (
        "Imported from the prototype properties_json field. "
        "Verify against a property-specific source before engineering use."
    )
    if source_notes.strip():
        note += f" Legacy source notes: {source_notes.strip()}"
    return note


def upgrade() -> None:
    """Copy legacy material references into the new V2 engineering tables."""
    bind = op.get_bind()

    legacy_materials = sa.table(
        "materials",
        sa.column("id", sa.Integer),
        sa.column("slug", sa.String),
        sa.column("name", sa.String),
        sa.column("full_name", sa.String),
        sa.column("family", sa.String),
        sa.column("subfamily", sa.String),
        sa.column("family_color", sa.String),
        sa.column("formula", sa.String),
        sa.column("repeat_unit", sa.String),
        sa.column("description", sa.Text),
        sa.column("best_for", sa.Text),
        sa.column("avoid_for", sa.Text),
        sa.column("properties_json", sa.Text),
        sa.column("source_notes", sa.Text),
        sa.column("is_active", sa.Boolean),
        sa.column("created_at", sa.DateTime),
    )

    material_families = sa.table(
        "material_families",
        sa.column("id", sa.Integer),
        sa.column("slug", sa.String),
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("color_hex", sa.String),
        sa.column("is_active", sa.Boolean),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
    )

    material_variants = sa.table(
        "material_variants",
        sa.column("id", sa.Integer),
        sa.column("family_id", sa.Integer),
        sa.column("slug", sa.String),
        sa.column("short_name", sa.String),
        sa.column("full_name", sa.String),
        sa.column("classification", sa.String),
        sa.column("formula", sa.String),
        sa.column("repeat_unit", sa.String),
        sa.column("description", sa.Text),
        sa.column("best_for", sa.Text),
        sa.column("avoid_for", sa.Text),
        sa.column("source_notes", sa.Text),
        sa.column("is_active", sa.Boolean),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
    )

    property_definitions = sa.table(
        "property_definitions",
        sa.column("id", sa.Integer),
        sa.column("key", sa.String),
        sa.column("name", sa.String),
        sa.column("category", sa.String),
        sa.column("value_type", sa.String),
        sa.column("default_unit", sa.String),
        sa.column("description", sa.Text),
        sa.column("sort_order", sa.Integer),
        sa.column("is_active", sa.Boolean),
    )

    property_records = sa.table(
        "material_property_records",
        sa.column("id", sa.Integer),
        sa.column("material_variant_id", sa.Integer),
        sa.column("property_definition_id", sa.Integer),
        sa.column("value_number", sa.Float),
        sa.column("value_min", sa.Float),
        sa.column("value_max", sa.Float),
        sa.column("value_text", sa.Text),
        sa.column("unit", sa.String),
        sa.column("material_state", sa.String),
        sa.column("test_condition", sa.Text),
        sa.column("test_standard", sa.String),
        sa.column("source_type", sa.String),
        sa.column("source_title", sa.String),
        sa.column("source_url", sa.String),
        sa.column("confidence", sa.String),
        sa.column("observed_on", sa.Date),
        sa.column("notes", sa.Text),
        sa.column("is_primary", sa.Boolean),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
    )

    definition_ids: dict[str, int] = {}

    for sort_order, spec in enumerate(PROPERTY_SPECS.values(), start=10):
        definition_id = bind.execute(
            sa.select(property_definitions.c.id).where(
                property_definitions.c.key == spec["key"]
            )
        ).scalar_one_or_none()

        if definition_id is None:
            result = bind.execute(
                sa.insert(property_definitions).values(
                    key=spec["key"],
                    name=spec["name"],
                    category=spec["category"],
                    value_type=spec["value_type"],
                    default_unit=spec["default_unit"],
                    description=spec["description"],
                    sort_order=sort_order,
                    is_active=True,
                )
            )
            definition_id = bind.execute(
                sa.select(property_definitions.c.id).where(
                    property_definitions.c.key == spec["key"]
                )
            ).scalar_one()

        definition_ids[spec["key"]] = definition_id

    legacy_rows = bind.execute(sa.select(legacy_materials)).mappings().all()

    for row in legacy_rows:
        now = row["created_at"] or datetime.utcnow()
        family_name = (row["family"] or "Unclassified").strip() or "Unclassified"

        family_id = bind.execute(
            sa.select(material_families.c.id).where(
                material_families.c.name == family_name
            )
        ).scalar_one_or_none()

        if family_id is None:
            result = bind.execute(
                sa.insert(material_families).values(
                    slug=slugify(family_name),
                    name=family_name,
                    description="Imported from the Material Lab prototype.",
                    color_hex=(row["family_color"] or "#64748b"),
                    is_active=bool(row["is_active"]),
                    created_at=now,
                    updated_at=now,
                )
            )
            family_id = bind.execute(
                sa.select(material_families.c.id).where(
                    material_families.c.name == family_name
                )
            ).scalar_one()

        variant_id = bind.execute(
            sa.select(material_variants.c.id).where(
                material_variants.c.slug == row["slug"]
            )
        ).scalar_one_or_none()

        if variant_id is None:
            result = bind.execute(
                sa.insert(material_variants).values(
                    family_id=family_id,
                    slug=row["slug"],
                    short_name=row["name"],
                    full_name=row["full_name"],
                    classification=row["subfamily"] or "Base polymer",
                    formula=row["formula"] or "",
                    repeat_unit=row["repeat_unit"] or "",
                    description=row["description"] or "",
                    best_for=row["best_for"] or "",
                    avoid_for=row["avoid_for"] or "",
                    source_notes=row["source_notes"] or "",
                    is_active=bool(row["is_active"]),
                    created_at=now,
                    updated_at=now,
                )
            )
            variant_id = bind.execute(
                sa.select(material_variants.c.id).where(
                    material_variants.c.slug == row["slug"]
                )
            ).scalar_one()

        properties = load_json(row["properties_json"])
        source_notes = row["source_notes"] or ""

        for legacy_key, spec in PROPERTY_SPECS.items():
            value = properties.get(legacy_key)
            if not is_present(value):
                continue

            definition_id = definition_ids[spec["key"]]

            existing_record = bind.execute(
                sa.select(property_records.c.id).where(
                    property_records.c.material_variant_id == variant_id,
                    property_records.c.property_definition_id == definition_id,
                    property_records.c.source_type == IMPORT_SOURCE_TYPE,
                    property_records.c.source_title == IMPORT_SOURCE_TITLE,
                )
            ).scalar_one_or_none()

            if existing_record is not None:
                continue

            value_number = None
            value_text = ""

            if isinstance(value, (int, float)) and not isinstance(value, bool):
                value_number = float(value)
            else:
                value_text = str(value)

            bind.execute(
                sa.insert(property_records).values(
                    material_variant_id=variant_id,
                    property_definition_id=definition_id,
                    value_number=value_number,
                    value_min=None,
                    value_max=None,
                    value_text=value_text,
                    unit=spec["default_unit"],
                    material_state=IMPORT_STATE,
                    test_condition="",
                    test_standard="",
                    source_type=IMPORT_SOURCE_TYPE,
                    source_title=IMPORT_SOURCE_TITLE,
                    source_url="",
                    confidence=IMPORT_CONFIDENCE,
                    observed_on=None,
                    notes=legacy_note(source_notes),
                    is_primary=False,
                    created_at=now,
                    updated_at=now,
                )
            )


def downgrade() -> None:
    """
    This import is intentionally non-reversible.

    Deleting imported records could delete user edits made after an upgrade.
    Production migrations are forward-only; restore a verified database backup
    instead of downgrading past this point.
    """
    raise NotImplementedError(
        "Prototype material-reference import is intentionally forward-only."
    )
