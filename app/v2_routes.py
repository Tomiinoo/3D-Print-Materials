from __future__ import annotations

from datetime import date
from math import isfinite
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from .database import get_session
from .models_v2 import (
    MaterialPropertyRecord,
    MaterialVariant,
    PropertyDefinition,
)
from .polymer_structure_resolver import resolve_polymer_structure

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


def clean_text(value: str | None) -> str:
    return (value or "").strip()


def confidence_rank(value: str) -> int:
    return {"high": 3, "medium": 2, "low": 1}.get(value, 0)


def evidence_rank(record: dict[str, Any]) -> tuple[int, int, int]:
    return (
        int(record["is_primary"]),
        confidence_rank(record["confidence_key"]),
        record["id"],
    )


def display_value(record: MaterialPropertyRecord) -> str:
    unit = clean_text(record.unit)

    if record.value_number is not None:
        return f"{record.value_number:g} {unit}".strip()

    if record.value_min is not None and record.value_max is not None:
        return f"{record.value_min:g}–{record.value_max:g} {unit}".strip()

    if record.value_min is not None:
        return f"≥ {record.value_min:g} {unit}".strip()

    if record.value_max is not None:
        return f"≤ {record.value_max:g} {unit}".strip()

    return clean_text(record.value_text) or "—"


def property_payload(record: MaterialPropertyRecord) -> dict[str, Any]:
    definition = record.property_definition
    return {
        "id": record.id,
        "key": definition.key,
        "name": definition.name,
        "category": definition.category,
        "value": display_value(record),
        "material_state": label(record.material_state),
        "test_condition": clean_text(record.test_condition),
        "test_standard": clean_text(record.test_standard),
        "source_type": label(record.source_type),
        "source_title": clean_text(record.source_title) or "No source title recorded",
        "source_url": clean_text(record.source_url),
        "confidence": label(record.confidence),
        "confidence_key": record.confidence,
        "observed_on": record.observed_on.isoformat() if record.observed_on else "",
        "notes": clean_text(record.notes),
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

        if evidence_rank(item) > evidence_rank(current):
            selected[item["key"]] = item

    return selected


def variant_payload(variant: MaterialVariant) -> dict[str, Any]:
    records = [
        property_payload(record)
        for record in variant.property_records
    ]
    records.sort(key=lambda item: (item["sort_order"], item["name"], item["id"]))

    primary = best_properties(records)

    grouped_by_key: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        grouped_by_key.setdefault(record["key"], []).append(record)

    property_groups: list[dict[str, Any]] = []
    for key, group_records in grouped_by_key.items():
        ordered_records = sorted(
            group_records,
            key=evidence_rank,
            reverse=True,
        )

        preferred = primary[key]
        alternatives = [
            record for record in ordered_records
            if record["id"] != preferred["id"]
        ]

        property_groups.append(
            {
                "key": key,
                "name": preferred["name"],
                "category": preferred["category"],
                "sort_order": preferred["sort_order"],
                "preferred": preferred,
                "alternatives": alternatives,
                "record_count": len(ordered_records),
                "selection_kind": "primary" if preferred["is_primary"] else "best",
                "selection_label": (
                    "Chosen primary evidence"
                    if preferred["is_primary"]
                    else "Best available evidence"
                ),
            }
        )

    property_groups.sort(
        key=lambda group: (
            group["sort_order"],
            group["name"].lower(),
        )
    )

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
        "property_groups": property_groups,
        "primary": primary,
        "record_count": len(records),
        "legacy_count": legacy_count,
        "verified_count": verified_count,
        "quality_label": quality_label,
        "quality_kind": quality_kind,
        "polymer_structure": resolve_polymer_structure(variant),
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

    property_definitions = list(
        session.scalars(
            select(PropertyDefinition)
            .where(PropertyDefinition.is_active.is_(True))
            .order_by(PropertyDefinition.sort_order, PropertyDefinition.name)
        )
    )

    return page(
        request,
        "v2_material_detail.html",
        material=variant_payload(variant),
        property_definitions=property_definitions,
    )


@router.post("/v2/materials/{slug}/properties")
def create_v2_property_record(
    slug: str,
    property_definition_id: int = Form(...),
    value_number: str = Form(""),
    value_min: str = Form(""),
    value_max: str = Form(""),
    value_text: str = Form(""),
    unit: str = Form(""),
    material_state: str = Form("unknown"),
    test_condition: str = Form(""),
    test_standard: str = Form(""),
    source_type: str = Form("manufacturer_tds"),
    source_title: str = Form(...),
    source_url: str = Form(""),
    confidence: str = Form("medium"),
    observed_on_v2: str = Form(""),
    notes: str = Form(""),
    is_primary: bool = Form(False),
    session: Session = Depends(get_session),
):
    valid_states = {"unknown", "dry", "conditioned", "wet"}
    valid_source_types = {
        "manufacturer_tds",
        "manufacturer_page",
        "paper",
        "user_measurement",
        "estimated",
        "other",
    }
    valid_confidence = {"high", "medium", "low"}

    variant = session.scalar(
        select(MaterialVariant).where(
            MaterialVariant.slug == slug,
            MaterialVariant.is_active.is_(True),
        )
    )
    if variant is None:
        raise HTTPException(status_code=404, detail="V2 material not found")

    definition = session.scalar(
        select(PropertyDefinition).where(
            PropertyDefinition.id == property_definition_id,
            PropertyDefinition.is_active.is_(True),
        )
    )
    if definition is None:
        raise HTTPException(status_code=404, detail="Property definition not found")

    numeric_input = clean_text(value_number)
    min_input = clean_text(value_min)
    max_input = clean_text(value_max)
    text_input = clean_text(value_text)

    value_mode_count = sum(
        int(bool(value))
        for value in (
            numeric_input,
            text_input,
            min_input or max_input,
        )
    )

    if value_mode_count > 1:
        raise HTTPException(
            status_code=422,
            detail="Enter a single numeric value, a range, or a text value.",
        )

    parsed_number: float | None = None
    parsed_min: float | None = None
    parsed_max: float | None = None
    if numeric_input:
        try:
            parsed_number = float(numeric_input)
        except ValueError as error:
            raise HTTPException(
                status_code=422,
                detail="Numeric value must be a valid number.",
            ) from error

        if not isfinite(parsed_number):
            raise HTTPException(
                status_code=422,
                detail="Numeric value must be finite.",
            )

    if min_input:
        try:
            parsed_min = float(min_input)
        except ValueError as error:
            raise HTTPException(
                status_code=422,
                detail="Range minimum must be a valid number.",
            ) from error

        if not isfinite(parsed_min):
            raise HTTPException(
                status_code=422,
                detail="Range minimum must be finite.",
            )

    if max_input:
        try:
            parsed_max = float(max_input)
        except ValueError as error:
            raise HTTPException(
                status_code=422,
                detail="Range maximum must be a valid number.",
            ) from error

        if not isfinite(parsed_max):
            raise HTTPException(
                status_code=422,
                detail="Range maximum must be finite.",
            )

    if (
        parsed_min is not None
        and parsed_max is not None
        and parsed_min > parsed_max
    ):
        raise HTTPException(
            status_code=422,
            detail="Range minimum cannot be greater than range maximum.",
        )

    if parsed_number is None and parsed_min is None and parsed_max is None and not text_input:
        raise HTTPException(
            status_code=422,
            detail="Enter a single numeric value, a range, or a text value.",
        )

    source_title_clean = clean_text(source_title)
    if not source_title_clean:
        raise HTTPException(
            status_code=422,
            detail="A source title is required for every property record.",
        )

    if material_state not in valid_states:
        raise HTTPException(status_code=422, detail="Invalid material state.")

    if source_type not in valid_source_types:
        raise HTTPException(status_code=422, detail="Invalid source type.")

    if confidence not in valid_confidence:
        raise HTTPException(status_code=422, detail="Invalid confidence value.")

    observed_date: date | None = None
    observed_on_clean = clean_text(observed_on_v2)
    if observed_on_clean:
        try:
            observed_date = date.fromisoformat(observed_on_clean)
        except ValueError as error:
            raise HTTPException(
                status_code=422,
                detail="Observed date must use YYYY-MM-DD.",
            ) from error

    if is_primary:
        session.execute(
            update(MaterialPropertyRecord)
            .where(
                MaterialPropertyRecord.material_variant_id == variant.id,
                MaterialPropertyRecord.property_definition_id == definition.id,
            )
            .values(is_primary=False)
        )

    session.add(
        MaterialPropertyRecord(
            material_variant_id=variant.id,
            property_definition_id=definition.id,
            value_number=parsed_number,
            value_min=parsed_min,
            value_max=parsed_max,
            value_text=text_input,
            unit=clean_text(unit) or clean_text(definition.default_unit),
            material_state=material_state,
            test_condition=clean_text(test_condition),
            test_standard=clean_text(test_standard),
            source_type=source_type,
            source_title=source_title_clean,
            source_url=clean_text(source_url),
            confidence=confidence,
            observed_on=observed_date,
            notes=clean_text(notes),
            is_primary=is_primary,
        )
    )
    session.commit()

    return RedirectResponse(
        f"/v2/materials/{variant.slug}#properties",
        status_code=303,
    )
