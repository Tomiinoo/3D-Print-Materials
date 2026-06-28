from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .database import get_session
from .models_v2 import (
    MaterialPropertyRecord,
    MaterialVariant,
    PropertyDefinition,
)

APP_DIR = Path(__file__).resolve().parent

router = APIRouter()
templates = Jinja2Templates(directory=APP_DIR / "templates")

NAV = [
    ("Dashboard", "/", "dashboard"),
    ("Material Library", "/materials", "materials"),
    ("Material Guide", "/guide", "guide"),
    ("Compare", "/compare", "compare"),
    ("Cost Calculator", "/calculator", "calculator"),
    ("Inventory & Tests", "/inventory", "inventory"),
    ("Settings", "/settings", "settings"),
]

LABELS = {
    "legacy_import": "Legacy import",
    "manufacturer_tds": "Manufacturer TDS",
    "manufacturer_page": "Manufacturer page",
    "paper": "Paper / literature",
    "user_measurement": "Personal measurement",
    "estimated": "Estimated",
    "unknown": "Unknown",
    "high": "High confidence",
    "medium": "Medium confidence",
    "low": "Low confidence",
    "dry": "Dry",
    "conditioned": "Conditioned",
    "wet": "Wet",
}


def label(value: str | None) -> str:
    if not value:
        return "Unknown"
    return LABELS.get(value, value.replace("_", " ").title())


def confidence_rank(value: str) -> int:
    return {"high": 3, "medium": 2, "low": 1}.get(value, 0)


def display_value(record: MaterialPropertyRecord) -> str:
    unit = record.unit.strip()

    if record.value_number is not None:
        return f"{record.value_number:g} {unit}".strip()

    if record.value_min is not None and record.value_max is not None:
        return f"{record.value_min:g}–{record.value_max:g} {unit}".strip()

    if record.value_min is not None:
        return f"≥ {record.value_min:g} {unit}".strip()

    if record.value_max is not None:
        return f"≤ {record.value_max:g} {unit}".strip()

    return record.value_text.strip() or "—"


def property_payload(record: MaterialPropertyRecord) -> dict[str, Any]:
    definition = record.property_definition
    return {
        "id": record.id,
        "key": definition.key,
        "name": definition.name,
        "category": definition.category,
        "value": display_value(record),
        "material_state": label(record.material_state),
        "source_type": label(record.source_type),
        "source_title": record.source_title.strip() or "No source title recorded",
        "source_url": record.source_url.strip(),
        "confidence": label(record.confidence),
        "confidence_key": record.confidence,
        "notes": record.notes.strip(),
        "is_primary": record.is_primary,
        "sort_order": definition.sort_order,
    }


def best_properties(properties: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {}

    for item in properties:
        current = selected.get(item["key"])
        if current is None:
            selected[item["key"]] = item
            continue

        item_rank = (
            int(item["is_primary"]),
            confidence_rank(item["confidence_key"]),
            item["id"],
        )
        current_rank = (
            int(current["is_primary"]),
            confidence_rank(current["confidence_key"]),
            current["id"],
        )

        if item_rank > current_rank:
            selected[item["key"]] = item

    return selected


def variant_payload(variant: MaterialVariant) -> dict[str, Any]:
    records = [
        property_payload(record)
        for record in variant.property_records
    ]
    records.sort(key=lambda item: (item["sort_order"], item["name"], item["id"]))

    primary = best_properties(records)
    legacy_count = sum(
        1 for item in records
        if item["source_type"] == "Legacy import"
    )
    verified_count = sum(
        1 for item in records
        if item["confidence_key"] in {"high", "medium"}
    )

    if verified_count:
        quality_label = "Verified sources present"
        quality_kind = "verified"
    elif legacy_count:
        quality_label = "Legacy reference import"
        quality_kind = "legacy"
    else:
        quality_label = "Needs sources"
        quality_kind = "missing"

    return {
        "id": variant.id,
        "slug": variant.slug,
        "name": variant.short_name,
        "full_name": variant.full_name,
        "family": variant.family.name,
        "family_color": variant.family.color_hex,
        "classification": variant.classification,
        "formula": variant.formula,
        "repeat_unit": variant.repeat_unit,
        "description": variant.description,
        "best_for": variant.best_for,
        "avoid_for": variant.avoid_for,
        "source_notes": variant.source_notes,
        "properties": records,
        "primary": primary,
        "record_count": len(records),
        "legacy_count": legacy_count,
        "verified_count": verified_count,
        "quality_label": quality_label,
        "quality_kind": quality_kind,
    }


def page(request: Request, template: str, **context: Any):
    defaults = {
        "request": request,
        "page_name": "materials",
        "nav": NAV,
    }
    defaults.update(context)
    return templates.TemplateResponse(template, defaults)


def load_variants(session: Session) -> list[MaterialVariant]:
    variants = list(
        session.scalars(
            select(MaterialVariant)
            .options(
                selectinload(MaterialVariant.family),
                selectinload(MaterialVariant.property_records).selectinload(
                    MaterialPropertyRecord.property_definition
                ),
            )
            .where(MaterialVariant.is_active.is_(True))
        )
    )
    return sorted(
        variants,
        key=lambda item: (item.family.name.lower(), item.short_name.lower()),
    )


@router.get("/v2/materials")
def v2_materials_page(
    request: Request,
    session: Session = Depends(get_session),
):
    materials = [variant_payload(variant) for variant in load_variants(session)]
    families = sorted({material["family"] for material in materials})

    return page(
        request,
        "v2_materials.html",
        materials=materials,
        families=families,
    )


@router.get("/v2/materials/{slug}")
def v2_material_detail(
    slug: str,
    request: Request,
    session: Session = Depends(get_session),
):
    variant = session.scalar(
        select(MaterialVariant)
        .options(
            selectinload(MaterialVariant.family),
            selectinload(MaterialVariant.property_records).selectinload(
                MaterialPropertyRecord.property_definition
            ),
        )
        .where(MaterialVariant.slug == slug)
    )

    if variant is None:
        raise HTTPException(status_code=404, detail="V2 material not found")

    return page(
        request,
        "v2_material_detail.html",
        material=variant_payload(variant),
    )
