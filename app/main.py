from __future__ import annotations

import json
import re
import shutil
import sqlite3
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .database import Base, DB_PATH, DATA_DIR, SessionLocal, engine, get_session
from .catalog import catalog_entries, catalog_entry_by_slug
from .models import FilamentProduct, Material, PriceEntry, PrinterPreset, PrintProfile
from .seed import seed_materials, seed_printer_presets
from .v2_routes import router as v2_router

APP_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        seed_materials(session)
        seed_printer_presets(session)
    yield


app = FastAPI(title="Material Lab", version="0.1.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")
templates = Jinja2Templates(directory=APP_DIR / "templates")
app.include_router(v2_router)


SCORE_LABELS = {
    "rigidity_xy": "XY rigidity",
    "strength_xy": "XY strength",
    "rigidity_z": "Z rigidity",
    "layer_adhesion": "Layer adhesion",
    "impact_resistance": "Impact resistance",
    "heat_resistance": "Heat resistance",
    "chemical_resistance": "Chemical resistance",
    "water_resistance": "Water resistance",
    "moisture_tolerance": "Moisture tolerance",
    "printability": "Ease of printing",
    "creep_resistance": "Creep resistance",
    "uv_resistance": "UV resistance",
    "price_range": "Price range",
}

MATERIAL_LIBRARY_FILTERS = [
    {"key": "all", "label": "All materials"},
    {"key": "main-path", "label": "Direct path"},
    {"key": "aux-path", "label": "Aux path"},
    {"key": "ams-compatible", "label": "AMS compatible"},
    {"key": "hardened-nozzle", "label": "Hardened nozzle"},
    {"key": "catalog-backlog", "label": "Catalog backlog"},
    {"key": "group-pla", "label": "PLA"},
    {"key": "group-polyester", "label": "PET / copolyester"},
    {"key": "group-styrenic", "label": "ABS / ASA / styrenic"},
    {"key": "group-elastomer", "label": "Flexible / elastomer"},
    {"key": "group-polyamide", "label": "Nylon / polyamide"},
    {"key": "group-pc", "label": "PC / blends"},
    {"key": "group-high-temp", "label": "High-temp"},
    {"key": "group-support", "label": "Support"},
    {"key": "group-filled", "label": "Filled / abrasive"},
    {"key": "group-esd", "label": "ESD / conductive"},
    {"key": "group-polyolefin", "label": "PP / polyolefin"},
]


def parse_json(raw: str | None, fallback: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        return json.loads(raw or "{}")
    except json.JSONDecodeError:
        return fallback or {}


def clean_text(value: str | None) -> str:
    return (value or "").strip()


def text_has(text: str, *needles: str) -> bool:
    return any(needle in text for needle in needles)


def text_tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def token_has(tokens: set[str], *needles: str) -> bool:
    return any(needle in tokens for needle in needles)


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", clean_text(value).lower()).strip("-")
    return slug or "printer"


def public_text(value: Any) -> Any:
    if isinstance(value, str):
        return value.replace("X2D", "printer").replace("x2d", "printer")
    if isinstance(value, dict):
        return {key: public_text(item) for key, item in value.items()}
    if isinstance(value, list):
        return [public_text(item) for item in value]
    return value


def active_products(products: list[FilamentProduct]) -> list[FilamentProduct]:
    return [product for product in products if product.is_active]


def active_printers(session: Session) -> list[PrinterPreset]:
    return list(
        session.scalars(
            select(PrinterPreset)
            .where(PrinterPreset.is_active.is_(True))
            .order_by(PrinterPreset.name)
        )
    )


def printer_payload(printer: PrinterPreset) -> dict[str, Any]:
    return {
        "id": printer.id,
        "slug": printer.slug,
        "name": printer.name,
        "nozzle_max_c": printer.nozzle_max_c,
        "bed_max_c": printer.bed_max_c,
        "enclosed": printer.enclosed,
        "direct_drive": printer.direct_drive,
        "supports_flexible": printer.supports_flexible,
        "ams_capable": printer.ams_capable,
        "notes": public_text(printer.notes),
        "is_active": printer.is_active,
    }


def parsed_number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)

    matches = re.findall(r"-?\d+(?:[.,]\d+)?", str(value))
    if not matches:
        return None

    numbers = [float(match.replace(",", ".")) for match in matches[:2]]
    if len(numbers) == 1:
        return numbers[0]
    return sum(numbers) / len(numbers)


def parsed_max_number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)

    matches = re.findall(r"-?\d+(?:[.,]\d+)?", str(value))
    if not matches:
        return None
    return max(float(match.replace(",", ".")) for match in matches)


def truthy_setting(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def material_compatibility(
    material: Material,
    settings: dict[str, Any],
    printers: list[PrinterPreset] | None = None,
) -> dict[str, Any]:
    family = clean_text(material.family).lower()
    subfamily = clean_text(material.subfamily).lower()
    name = clean_text(material.name).lower()
    nozzle_max = parsed_max_number(settings.get("nozzle"))
    bed_max = parsed_max_number(settings.get("bed"))
    chamber_max = parsed_max_number(settings.get("chamber"))
    direct_ok = truthy_setting(settings.get("main_compatible"), True)
    aux_ok = truthy_setting(settings.get("aux_compatible"), False)
    flexible = "elastomer" in family or "flex" in subfamily or "tpu" in name or "tpe" in name
    support = "support" in family or "support" in subfamily or name in {"pva", "bvoh"}
    ams_ok = truthy_setting(settings.get("ams_compatible"), aux_ok and not flexible and not support)
    requires_enclosure = chamber_max is not None and chamber_max > 40

    filter_keys = ["main-path"] if direct_ok else []
    if aux_ok:
        filter_keys.append("aux-path")
    if ams_ok:
        filter_keys.append("ams-compatible")
    if text_has(clean_text(settings.get("recommended_nozzle")).lower(), "hardened", "tc", "steel"):
        filter_keys.append("hardened-nozzle")

    printer_matches: list[str] = []
    printer_match_labels: list[str] = []
    for printer in printers or []:
        if nozzle_max is not None and printer.nozzle_max_c and nozzle_max > printer.nozzle_max_c:
            continue
        if bed_max is not None and printer.bed_max_c and bed_max > printer.bed_max_c:
            continue
        if requires_enclosure and not printer.enclosed:
            continue
        if flexible and not printer.supports_flexible:
            continue

        key = f"printer-{printer.slug}"
        printer_matches.append(key)
        printer_match_labels.append(printer.name)
        filter_keys.append(key)

    return {
        "direct_path": direct_ok,
        "aux_path": aux_ok,
        "ams": ams_ok,
        "requires_enclosure": requires_enclosure,
        "printer_matches": printer_matches,
        "printer_match_labels": printer_match_labels,
        "filter_keys": filter_keys,
        "nozzle_max_c": nozzle_max,
        "bed_max_c": bed_max,
        "chamber_max_c": chamber_max,
    }


def material_filter_keys(material: Material, settings: dict[str, Any]) -> list[str]:
    identity_fields = [
        material.name,
        material.full_name,
        material.family,
        material.subfamily,
    ]
    nozzle_fields = [
        clean_text(settings.get("recommended_nozzle")),
        clean_text(settings.get("nozzle")),
    ]
    haystack = " ".join(clean_text(str(field)).lower() for field in identity_fields)
    nozzle_haystack = " ".join(clean_text(str(field)).lower() for field in nozzle_fields)
    tokens = text_tokens(haystack)
    nozzle_tokens = text_tokens(nozzle_haystack)
    keys: list[str] = []

    is_pla = token_has(tokens, "pla") or text_has(haystack, "polylactic")
    if is_pla:
        keys.append("group-pla")
    if token_has(tokens, "pet", "petg", "pett", "copet", "cpe", "pctg", "pbt") or text_has(haystack, "copolyester") or (text_has(haystack, "polyester") and not is_pla):
        keys.append("group-polyester")
    if token_has(tokens, "abs", "asa", "hips", "san") or text_has(haystack, "styrenic"):
        keys.append("group-styrenic")
    if token_has(tokens, "tpu", "tpe", "tpc", "tpv") or text_has(haystack, "elastomer", "flexible"):
        keys.append("group-elastomer")
    if token_has(tokens, "pa6", "pa11", "pa12", "pa66", "ppa", "paht", "copa") or text_has(haystack, "polyamide", "nylon"):
        keys.append("group-polyamide")
    if token_has(tokens, "pc") or text_has(haystack, "polycarbonate"):
        keys.append("group-pc")
    if token_has(tokens, "peek", "pekk", "pei", "pps", "psu", "ppsu", "pesu", "lcp", "paek"):
        keys.append("group-high-temp")
    if token_has(tokens, "pva", "bvoh") or text_has(haystack, "support", "breakaway"):
        keys.append("group-support")
    if token_has(tokens, "cf", "gf", "carbon", "glass", "fiber", "fibre", "kevlar", "aramid", "basalt", "filled", "ceramic", "mineral", "wood", "metal", "abrasive"):
        keys.append("group-filled")
    if token_has(tokens, "esd") or text_has(haystack, "conductive"):
        keys.append("group-esd")
    if token_has(tokens, "pp", "hdpe", "ldpe") or text_has(haystack, "polypropylene", "polyolefin"):
        keys.append("group-polyolefin")
    if token_has(tokens, "cf", "gf", "carbon", "glass", "filled") or token_has(nozzle_tokens, "tc") or text_has(nozzle_haystack, "hardened", "steel", "abrasive"):
        keys.append("hardened-nozzle")

    return sorted(set(keys))


def real_property(value: Any, unit: str = "") -> dict[str, Any]:
    number = parsed_number(value)
    label = str(value).strip() if value not in (None, "") else ""
    if number is None:
        return {"value": None, "label": label, "unit": unit}
    if isinstance(value, (int, float)) or not label:
        label = f"{number:g} {unit}".strip()
    return {"value": number, "label": label, "unit": unit}


def property_label(properties: dict[str, Any], key: str, unit: str = "") -> str:
    return public_text(real_property(properties.get(key), unit)["label"])


def first_property_label(
    properties: dict[str, Any],
    candidates: list[tuple[str, str]],
) -> str:
    for key, unit in candidates:
        label = property_label(properties, key, unit)
        if label:
            return label
    return ""


def joined_values(values: list[str]) -> str:
    return " · ".join(value for value in values if value)


def engineering_reference_rows(
    properties: dict[str, Any],
    settings: dict[str, Any],
    scores: dict[str, Any],
) -> list[dict[str, Any]]:
    dry_scores = scores.get("dry", {})

    def row(
        key: str,
        real_label: str,
        real_value: str,
        real_kind: str = "value",
    ) -> dict[str, Any]:
        score_value = dry_scores.get(key, 0) or 0
        try:
            score_number = float(score_value)
        except (TypeError, ValueError):
            score_number = 0
        score_number = max(0, min(10, score_number))
        display_score = int(score_number) if score_number.is_integer() else round(score_number, 1)
        return {
            "key": key,
            "label": SCORE_LABELS[key],
            "score": display_score,
            "score_percent": score_number * 10,
            "real_label": real_label,
            "real_value": public_text(real_value),
            "real_kind": real_kind,
        }

    def missing(key: str, real_label: str, real_value: str) -> dict[str, Any]:
        return row(key, real_label, real_value, "missing")

    modulus = first_property_label(
        properties,
        [("modulus_gpa", "GPa"), ("tensile_modulus_gpa", "GPa"), ("flexural_modulus_gpa", "GPa")],
    )
    tensile = first_property_label(
        properties,
        [("tensile_mpa", "MPa"), ("tensile_strength_mpa", "MPa"), ("flexural_strength_mpa", "MPa")],
    )
    z_modulus = first_property_label(properties, [("z_modulus_gpa", "GPa"), ("z_rigidity_gpa", "GPa")])
    layer_value = first_property_label(
        properties,
        [("z_tensile_mpa", "MPa"), ("layer_adhesion_mpa", "MPa"), ("interlayer_strength_mpa", "MPa")],
    )
    impact = first_property_label(
        properties,
        [
            ("charpy_impact_kj_m2", "kJ/m²"),
            ("izod_impact_j_m", "J/m"),
            ("notched_impact_kj_m2", "kJ/m²"),
        ],
    ) or clean_text(public_text(properties.get("impact_note")))
    heat = joined_values(
        [
            f"HDT {property_label(properties, 'hdt_c', '°C')}" if property_label(properties, "hdt_c", "°C") else "",
            (
                f"Service {property_label(properties, 'continuous_service_c', '°C')}"
                if property_label(properties, "continuous_service_c", "°C")
                else ""
            ),
        ]
    )
    chemical = first_property_label(
        properties,
        [("chemical_resistance_note", ""), ("chemical_exposure_note", ""), ("solvent_resistance_note", "")],
    )
    water = first_property_label(
        properties,
        [
            ("water_absorption_pct", "%"),
            ("water_absorption_24h_pct", "%"),
            ("saturation_water_absorption_pct", "%"),
            ("water_resistance_note", ""),
        ],
    )
    drying = clean_text(public_text(settings.get("drying")))
    process = joined_values(
        [
            f"Nozzle {public_text(settings.get('nozzle'))}" if settings.get("nozzle") else "",
            f"Bed {public_text(settings.get('bed'))}" if settings.get("bed") else "",
            f"Chamber {public_text(settings.get('chamber'))}" if settings.get("chamber") else "",
        ]
    )
    creep = first_property_label(properties, [("creep_note", ""), ("creep_modulus_mpa", "MPa")])
    uv = first_property_label(properties, [("uv_note", ""), ("weathering_note", ""), ("uv_resistance_note", "")])

    return [
        row("rigidity_xy", "Tensile/flexural modulus", modulus)
        if modulus
        else missing("rigidity_xy", "Tensile/flexural modulus", "No modulus value stored yet"),
        row("strength_xy", "Tensile/flexural strength", tensile)
        if tensile
        else missing("strength_xy", "Tensile/flexural strength", "No strength value stored yet"),
        row("rigidity_z", "Z-direction stiffness", z_modulus)
        if z_modulus
        else missing("rigidity_z", "Z-direction stiffness", "No Z stiffness value stored yet"),
        row("layer_adhesion", "Layer / Z strength", layer_value)
        if layer_value
        else missing("layer_adhesion", "Layer / Z strength", "No layer-strength value stored yet"),
        row("impact_resistance", "Impact evidence", impact, "note" if parsed_number(impact) is None else "value")
        if impact
        else missing("impact_resistance", "Impact evidence", "No impact test value stored yet"),
        row("heat_resistance", "Heat data", heat)
        if heat
        else missing("heat_resistance", "Heat data", "No HDT or service-temperature value stored yet"),
        row("chemical_resistance", "Chemical exposure", chemical, "note")
        if chemical
        else missing("chemical_resistance", "Chemical exposure", "No chemical exposure data stored yet"),
        row("water_resistance", "Water uptake / exposure", water, "note" if parsed_number(water) is None else "value")
        if water
        else missing("water_resistance", "Water uptake / exposure", "No water absorption value stored yet"),
        row("moisture_tolerance", "Drying / conditioning guide", drying, "guide")
        if drying
        else missing("moisture_tolerance", "Drying / conditioning", "No moisture conditioning data stored yet"),
        row("printability", "Starting process window", process, "guide")
        if process
        else missing("printability", "Starting process window", "No process window stored yet"),
        row("creep_resistance", "Creep / long-term load", creep, "note" if parsed_number(creep) is None else "value")
        if creep
        else missing("creep_resistance", "Creep / long-term load", "No creep test value stored yet"),
        row("uv_resistance", "UV / weathering", uv, "note")
        if uv
        else missing("uv_resistance", "UV / weathering", "No UV weathering data stored yet"),
    ]


def product_price(product: FilamentProduct) -> tuple[float | None, float | None, date | None]:
    if not product.price_entries:
        return None, None, None
    entry = sorted(product.price_entries, key=lambda x: (x.observed_on, x.id), reverse=True)[0]
    price_per_kg = (entry.price_eur / product.spool_weight_g * 1000) if product.spool_weight_g else None
    return entry.price_eur, price_per_kg, entry.observed_on


def display_spool_code(product: FilamentProduct) -> str:
    return product.spool_code or f"S-{product.id:03d}"


def normalized_spool_code(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", clean_text(value).lower())


def spool_path(product: FilamentProduct) -> str:
    return f"/spools/{quote(display_spool_code(product), safe='')}"


def product_detail_options():
    return (
        selectinload(FilamentProduct.material),
        selectinload(FilamentProduct.price_entries),
        selectinload(FilamentProduct.print_profiles).selectinload(PrintProfile.material),
        selectinload(FilamentProduct.print_profiles).selectinload(PrintProfile.printer),
    )


def product_by_spool_code(session: Session, spool_code: str) -> FilamentProduct | None:
    target = normalized_spool_code(spool_code)
    if not target:
        return None
    products = session.scalars(
        select(FilamentProduct)
        .options(*product_detail_options())
        .order_by(FilamentProduct.id.desc())
    )
    for product in products:
        if normalized_spool_code(display_spool_code(product)) == target:
            return product
    return None


def ensure_unique_spool_code(
    session: Session,
    spool_code: str,
    current_product_id: int | None = None,
) -> None:
    target = normalized_spool_code(spool_code)
    if not target:
        return
    for product in session.scalars(select(FilamentProduct).order_by(FilamentProduct.id)):
        if current_product_id is not None and product.id == current_product_id:
            continue
        if normalized_spool_code(display_spool_code(product)) == target:
            raise HTTPException(status_code=409, detail="This spool number already exists.")


def product_payload(product: FilamentProduct) -> dict[str, Any]:
    latest, per_kg, observed = product_price(product)
    return {
        "id": product.id,
        "material_id": product.material_id,
        "brand": product.brand,
        "product_name": product.product_name,
        "supplier": product.supplier,
        "url": product.url,
        "color_name": product.color_name,
        "spool_code": display_spool_code(product),
        "spool_path": spool_path(product),
        "spool_weight_g": product.spool_weight_g,
        "notes": product.notes,
        "favorite": product.favorite,
        "is_active": product.is_active,
        "profile_count": len(product.print_profiles),
        "buy_again_label": "Would buy again" if product.favorite else "Needs more evidence",
        "latest_price_eur": latest,
        "price_per_kg": per_kg,
        "price_observed_on": observed.isoformat() if observed else None,
        "price_entries": [
            {
                "id": p.id,
                "price_eur": p.price_eur,
                "observed_on": p.observed_on.isoformat(),
                "source_label": p.source_label,
                "stock_note": p.stock_note,
            }
            for p in sorted(product.price_entries, key=lambda x: (x.observed_on, x.id), reverse=True)
        ],
    }


def spool_page_payload(product: FilamentProduct) -> dict[str, Any]:
    payload = product_payload(product)
    payload.update(
        {
            "material_name": product.material.name,
            "material_slug": product.material.slug,
            "material_full_name": product.material.full_name,
            "material_family": product.material.family,
            "material_color": product.material.family_color,
        }
    )
    return payload


def material_price_range(products: list[FilamentProduct]) -> dict[str, Any]:
    values = [
        price_per_kg
        for product in active_products(products)
        for _, price_per_kg, _ in [product_price(product)]
        if price_per_kg is not None
    ]

    if not values:
        return {"value": None, "min": None, "max": None, "label": "", "unit": "€/kg"}

    low = min(values)
    high = max(values)
    label = f"€{low:.2f}/kg" if low == high else f"€{low:.2f}–€{high:.2f}/kg"
    return {
        "value": low,
        "min": low,
        "max": high,
        "label": label,
        "unit": "€/kg",
    }


def real_properties_payload(
    properties: dict[str, Any],
    products: list[FilamentProduct],
) -> dict[str, dict[str, Any]]:
    return {
        "density_g_cm3": real_property(properties.get("density_g_cm3"), "g/cm³"),
        "hdt_c": real_property(properties.get("hdt_c"), "°C"),
        "continuous_service_c": real_property(properties.get("continuous_service_c"), "°C"),
        "tensile_mpa": real_property(properties.get("tensile_mpa"), "MPa"),
        "modulus_gpa": real_property(properties.get("modulus_gpa"), "GPa"),
        "moisture_sensitivity": real_property(properties.get("moisture_sensitivity"), "/10"),
        "price_per_kg": material_price_range(products),
    }


def material_slug(value: str) -> str:
    normalized = clean_text(value).lower().replace("+", " plus ")
    return re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")


def pretty_json(raw: str | dict[str, Any]) -> str:
    try:
        parsed = raw if isinstance(raw, dict) else json.loads(raw or "{}")
    except json.JSONDecodeError:
        return str(raw or "{}")
    return json.dumps(parsed, indent=2, ensure_ascii=False)


def material_form_payload(material: Material) -> dict[str, Any]:
    settings = parse_json(material.settings_json)
    properties = parse_json(material.properties_json)
    return {
        "name": material.name,
        "slug": material.slug,
        "full_name": material.full_name,
        "family": material.family,
        "subfamily": material.subfamily,
        "family_color": material.family_color,
        "formula": material.formula,
        "repeat_unit": material.repeat_unit,
        "description": material.description,
        "best_for": material.best_for,
        "avoid_for": material.avoid_for,
        "source_notes": material.source_notes,
        "settings": settings,
        "properties": properties,
    }


def validate_material_json(settings_json: str, properties_json: str) -> tuple[str, str]:
    try:
        json.loads(settings_json)
        json.loads(properties_json)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Settings / properties JSON is invalid: {exc.msg}") from exc
    return settings_json, properties_json


def material_source_label(source_notes: str, is_catalog: bool = False) -> str:
    notes = clean_text(public_text(source_notes)).lower()
    if not notes:
        return "No source note"
    if "tds" in notes or "manufacturer" in notes:
        return "Manufacturer/source note"
    if "legacy" in notes or "prototype" in notes or is_catalog:
        return "Approximate/catalog source"
    return "Source note saved"


def material_confidence_items(
    source_notes: str,
    product_count: int,
    profile_count: int,
    is_catalog: bool = False,
) -> list[dict[str, Any]]:
    return [
        {
            "label": "Data source",
            "value": material_source_label(source_notes, is_catalog),
            "kind": "good" if source_notes else "warn",
        },
        {
            "label": "Exact spools",
            "value": f"{product_count} saved" if product_count else "None yet",
            "kind": "good" if product_count else "warn",
        },
        {
            "label": "Personal tests",
            "value": f"{profile_count} logged" if profile_count else "0 logged",
            "kind": "good" if profile_count else "warn",
        },
        {
            "label": "Before trusting",
            "value": "Confirm exact spool TDS" if product_count else "Add exact spool first",
            "kind": "warn",
        },
    ]


def material_readiness_items(
    source_notes: str,
    product_count: int,
    profiles: list[PrintProfile],
) -> list[dict[str, Any]]:
    orientation_known = any(
        text_has(clean_text(profile.notes).lower(), "xy", "x-y", "z ", "orientation", "load direction")
        for profile in profiles
    )
    state_known = any(clean_text(profile.state) for profile in profiles)
    return [
        {"label": "Exact manufacturer spool selected", "done": product_count > 0},
        {"label": "TDS or source note saved", "done": bool(clean_text(source_notes))},
        {"label": "Material state logged", "done": state_known},
        {"label": "Print orientation/load direction noted", "done": orientation_known},
        {"label": "Personal print test exists", "done": bool(profiles)},
    ]


def merge_material_form_values(
    settings_json: str,
    properties_json: str,
    *,
    nozzle: str = "",
    bed: str = "",
    chamber: str = "",
    speed: str = "",
    drying: str = "",
    cooling: str = "",
    recommended_nozzle: str = "",
    main_compatible: bool = False,
    aux_compatible: bool = False,
    ams_compatible: bool = False,
    density_g_cm3: str = "",
    tensile_mpa: str = "",
    modulus_gpa: str = "",
    hdt_c: str = "",
    continuous_service_c: str = "",
    moisture_sensitivity: str = "",
    water_resistance: str = "",
    chemical_resistance: str = "",
    uv_resistance: str = "",
    creep_resistance: str = "",
    flame_resistance: str = "",
    impact_note: str = "",
    shrinkage_note: str = "",
) -> tuple[str, str]:
    settings_json, properties_json = validate_material_json(settings_json, properties_json)
    settings = json.loads(settings_json or "{}")
    properties = json.loads(properties_json or "{}")

    def put_text(target: dict[str, Any], key: str, value: str) -> None:
        cleaned = clean_text(value)
        if cleaned:
            target[key] = cleaned

    def put_numberish(target: dict[str, Any], key: str, value: str) -> None:
        cleaned = clean_text(value)
        if not cleaned:
            return
        number = parsed_number(cleaned)
        target[key] = number if number is not None and re.fullmatch(r"-?\d+(?:[.,]\d+)?", cleaned) else cleaned

    for key, value in {
        "nozzle": nozzle,
        "bed": bed,
        "chamber": chamber,
        "speed": speed,
        "drying": drying,
        "cooling": cooling,
        "recommended_nozzle": recommended_nozzle,
    }.items():
        put_text(settings, key, value)

    settings["main_compatible"] = bool(main_compatible)
    settings["aux_compatible"] = bool(aux_compatible)
    settings["ams_compatible"] = bool(ams_compatible)

    for key, value in {
        "density_g_cm3": density_g_cm3,
        "tensile_mpa": tensile_mpa,
        "modulus_gpa": modulus_gpa,
        "hdt_c": hdt_c,
        "continuous_service_c": continuous_service_c,
        "moisture_sensitivity": moisture_sensitivity,
        "water_resistance": water_resistance,
        "chemical_resistance": chemical_resistance,
        "uv_resistance": uv_resistance,
        "creep_resistance": creep_resistance,
        "flame_resistance": flame_resistance,
    }.items():
        put_numberish(properties, key, value)

    put_text(properties, "impact_note", impact_note)
    put_text(properties, "shrinkage_note", shrinkage_note)

    density_value = parsed_number(properties.get("density_g_cm3"))
    if density_value is not None:
        properties["mass_g_mm3"] = density_value / 1000

    return pretty_json(settings), pretty_json(properties)


def material_payload(
    material: Material,
    include_products: bool = True,
    printers: list[PrinterPreset] | None = None,
) -> dict[str, Any]:
    props = public_text(parse_json(material.properties_json))
    setting = public_text(parse_json(material.settings_json))
    scores = props.get("scores", {})
    visible_products = active_products(material.products)
    visible_profiles = list(material.print_profiles)
    compatibility = material_compatibility(material, setting, printers)
    data: dict[str, Any] = {
        "id": material.id,
        "slug": material.slug,
        "name": public_text(material.name),
        "full_name": public_text(material.full_name),
        "family": public_text(material.family),
        "subfamily": public_text(material.subfamily),
        "family_color": material.family_color,
        "formula": public_text(material.formula),
        "repeat_unit": public_text(material.repeat_unit),
        "description": public_text(material.description),
        "best_for": public_text(material.best_for),
        "avoid_for": public_text(material.avoid_for),
        "settings": setting,
        "properties": props,
        "real_properties": real_properties_payload(props, material.products),
        "engineering_rows": engineering_reference_rows(props, setting, scores),
        "scores": scores,
        "compatibility": compatibility,
        "filter_keys": material_filter_keys(material, setting),
        "source_notes": public_text(material.source_notes),
        "product_count": len(visible_products),
        "profile_count": len(visible_profiles),
        "confidence_items": material_confidence_items(material.source_notes, len(visible_products), len(visible_profiles)),
        "readiness_items": material_readiness_items(material.source_notes, len(visible_products), visible_profiles),
        "is_catalog": False,
    }
    if include_products:
        data["products"] = [product_payload(p) for p in visible_products]
    return data


def catalog_detail_payload(
    slug: str,
    printers: list[PrinterPreset] | None = None,
) -> dict[str, Any] | None:
    payload = catalog_entry_by_slug(slug, printers=printers)
    if payload is None:
        return None
    payload["engineering_rows"] = engineering_reference_rows(
        payload["properties"],
        payload["settings"],
        payload["scores"],
    )
    source_notes = payload.get("source_notes") or payload.get("source_title") or ""
    payload["confidence_items"] = material_confidence_items(source_notes, 0, 0, is_catalog=True)
    payload["readiness_items"] = material_readiness_items(source_notes, 0, [])
    payload["profile_count"] = 0
    return payload


def profile_payload(profile: PrintProfile) -> dict[str, Any]:
    return {
        "id": profile.id,
        "profile_name": profile.profile_name,
        "state": profile.state,
        "printer_name": profile.printer.name if profile.printer else "",
        "nozzle_diameter": profile.nozzle_diameter,
        "nozzle_temp": profile.nozzle_temp,
        "bed_temp": profile.bed_temp,
        "chamber_temp": profile.chamber_temp,
        "speed_mm_s": profile.speed_mm_s,
        "dryer_temp": profile.dryer_temp,
        "dryer_hours": profile.dryer_hours,
        "build_plate": profile.build_plate,
        "filament_used_g": profile.filament_used_g,
        "result_rating": profile.result_rating,
        "notes": profile.notes,
        "printed_on": profile.printed_on.isoformat(),
        "product_name": f"{profile.product.brand} {profile.product.product_name}" if profile.product else None,
        "product_spool_code": display_spool_code(profile.product) if profile.product else None,
        "product_spool_path": spool_path(profile.product) if profile.product else None,
    }


def all_materials(session: Session) -> list[Material]:
    return list(
        session.scalars(
            select(Material)
            .options(selectinload(Material.products).selectinload(FilamentProduct.price_entries))
            .options(selectinload(Material.products).selectinload(FilamentProduct.print_profiles))
            .where(Material.is_active.is_(True))
            .order_by(Material.family, Material.name)
        )
    )


def page(request: Request, template: str, **context: Any):
    defaults = {
        "request": request,
        "nav": [
            ("Dashboard", "/", "dashboard"),
            ("Material Library", "/materials", "materials"),
            ("Material Guide", "/guide", "guide"),
            ("Compare", "/compare", "compare"),
            ("Cost Calculator", "/calculator", "calculator"),
            ("Inventory & Tests", "/inventory", "inventory"),
            ("Settings", "/settings", "settings"),
        ],
        "score_labels": SCORE_LABELS,
    }
    defaults.update(context)
    return templates.TemplateResponse(template, defaults)


@app.get("/")
def dashboard(request: Request, session: Session = Depends(get_session)):
    materials = all_materials(session)
    printers = active_printers(session)
    material_data = [material_payload(m, printers=printers) for m in materials]
    stats = {
        "materials": len(materials),
        "products": sum(len(active_products(m.products)) for m in materials),
        "tested_profiles": len(session.scalars(select(PrintProfile)).all()),
        "families": len({m.family for m in materials}),
    }
    return page(request, "dashboard.html", page_name="dashboard", materials=material_data, stats=stats)


@app.get("/materials")
def materials_page(request: Request, session: Session = Depends(get_session)):
    printers = active_printers(session)
    materials = [material_payload(m, printers=printers) for m in all_materials(session)]
    existing_slugs = {m["slug"] for m in materials}
    catalog_materials = catalog_entries(existing_slugs, printers=printers)
    library_materials = materials + catalog_materials
    filters = [dict(item) for item in MATERIAL_LIBRARY_FILTERS]
    filters.extend(
        {"key": f"printer-{printer.slug}", "label": printer.name}
        for printer in printers
    )
    return page(
        request,
        "materials.html",
        page_name="materials",
        materials=library_materials,
        filters=filters,
        printers=[printer_payload(printer) for printer in printers],
    )


@app.get("/materials/new")
def material_new_form(request: Request):
    example_settings = {
        "nozzle": "250–270 °C", "bed": "80–100 °C", "chamber": "50–65 °C", "drying": "75–85 °C · 8 h",
        "speed": "40–120 mm/s", "recommended_nozzle": "0.4 mm TC", "main_compatible": True,
        "aux_compatible": True, "cooling": "Low fan",
    }
    example_properties = {
        "density_g_cm3": 1.10, "mass_g_mm3": 0.0011, "hdt_c": 90, "continuous_service_c": 75,
        "moisture_sensitivity": 5, "water_resistance": 6, "flame_resistance": 2, "chemical_resistance": 5,
        "uv_resistance": 5, "creep_resistance": 5, "tensile_mpa": "Add TDS value", "modulus_gpa": "Add TDS value",
        "impact_note": "Add test method / TDS note", "shrinkage_note": "Add shrinkage note",
        "scores": {"dry": {key: 5 for key in SCORE_LABELS}, "wet": {key: 4 for key in SCORE_LABELS}},
    }
    material = {
        "name": "",
        "slug": "",
        "full_name": "",
        "family": "",
        "subfamily": "Base polymer",
        "family_color": "#64748b",
        "formula": "",
        "repeat_unit": "",
        "description": "",
        "best_for": "",
        "avoid_for": "",
        "source_notes": "",
        "settings": example_settings,
        "properties": example_properties,
    }
    return page(
        request, "material_form.html", page_name="materials", mode="create", material=material,
        example_settings=json.dumps(example_settings, indent=2), example_properties=json.dumps(example_properties, indent=2),
    )


@app.post("/materials/new")
def create_material(
    name: str = Form(...),
    slug: str = Form(...),
    full_name: str = Form(...),
    family: str = Form(...),
    subfamily: str = Form("Base polymer"),
    family_color: str = Form("#64748b"),
    formula: str = Form("—"),
    repeat_unit: str = Form("—"),
    description: str = Form(""),
    best_for: str = Form(""),
    avoid_for: str = Form(""),
    settings_json: str = Form("{}"),
    properties_json: str = Form("{}"),
    nozzle: str = Form(""),
    bed: str = Form(""),
    chamber: str = Form(""),
    speed: str = Form(""),
    drying: str = Form(""),
    cooling: str = Form(""),
    recommended_nozzle: str = Form(""),
    main_compatible: bool = Form(False),
    aux_compatible: bool = Form(False),
    ams_compatible: bool = Form(False),
    density_g_cm3: str = Form(""),
    tensile_mpa: str = Form(""),
    modulus_gpa: str = Form(""),
    hdt_c: str = Form(""),
    continuous_service_c: str = Form(""),
    moisture_sensitivity: str = Form(""),
    water_resistance: str = Form(""),
    chemical_resistance: str = Form(""),
    uv_resistance: str = Form(""),
    creep_resistance: str = Form(""),
    flame_resistance: str = Form(""),
    impact_note: str = Form(""),
    shrinkage_note: str = Form(""),
    source_notes: str = Form(""),
    session: Session = Depends(get_session),
):
    slug = material_slug(slug or name)
    if not slug:
        raise HTTPException(status_code=400, detail="Material slug is required.")
    if session.scalar(select(Material).where(Material.slug == slug)):
        raise HTTPException(status_code=409, detail="This material slug already exists.")
    settings_json, properties_json = merge_material_form_values(
        settings_json,
        properties_json,
        nozzle=nozzle,
        bed=bed,
        chamber=chamber,
        speed=speed,
        drying=drying,
        cooling=cooling,
        recommended_nozzle=recommended_nozzle,
        main_compatible=main_compatible,
        aux_compatible=aux_compatible,
        ams_compatible=ams_compatible,
        density_g_cm3=density_g_cm3,
        tensile_mpa=tensile_mpa,
        modulus_gpa=modulus_gpa,
        hdt_c=hdt_c,
        continuous_service_c=continuous_service_c,
        moisture_sensitivity=moisture_sensitivity,
        water_resistance=water_resistance,
        chemical_resistance=chemical_resistance,
        uv_resistance=uv_resistance,
        creep_resistance=creep_resistance,
        flame_resistance=flame_resistance,
        impact_note=impact_note,
        shrinkage_note=shrinkage_note,
    )
    mat = Material(
        name=name.strip(), slug=slug, full_name=full_name.strip(), family=family.strip(), subfamily=subfamily.strip(),
        family_color=family_color.strip() or "#64748b", formula=formula.strip(), repeat_unit=repeat_unit.strip(),
        description=description.strip(), best_for=best_for.strip(), avoid_for=avoid_for.strip(), settings_json=settings_json,
        properties_json=properties_json, source_notes=source_notes.strip(),
    )
    session.add(mat)
    session.commit()
    return RedirectResponse(f"/materials/{mat.slug}", status_code=303)


@app.get("/materials/{slug}/edit")
def material_edit_form(slug: str, request: Request, session: Session = Depends(get_session)):
    material = session.scalar(select(Material).where(Material.slug == slug))
    if not material:
        if catalog_entry_by_slug(slug) is not None:
            return RedirectResponse(f"/materials/{slug}", status_code=303)
        raise HTTPException(status_code=404, detail="Material not found")
    return page(
        request,
        "material_form.html",
        page_name="materials",
        mode="edit",
        material=material_form_payload(material),
        example_settings=pretty_json(material.settings_json),
        example_properties=pretty_json(material.properties_json),
    )


@app.post("/materials/{slug}/edit")
def update_material(
    slug: str,
    name: str = Form(...),
    new_slug: str = Form(..., alias="slug"),
    full_name: str = Form(...),
    family: str = Form(...),
    subfamily: str = Form("Base polymer"),
    family_color: str = Form("#64748b"),
    formula: str = Form("—"),
    repeat_unit: str = Form("—"),
    description: str = Form(""),
    best_for: str = Form(""),
    avoid_for: str = Form(""),
    settings_json: str = Form("{}"),
    properties_json: str = Form("{}"),
    nozzle: str = Form(""),
    bed: str = Form(""),
    chamber: str = Form(""),
    speed: str = Form(""),
    drying: str = Form(""),
    cooling: str = Form(""),
    recommended_nozzle: str = Form(""),
    main_compatible: bool = Form(False),
    aux_compatible: bool = Form(False),
    ams_compatible: bool = Form(False),
    density_g_cm3: str = Form(""),
    tensile_mpa: str = Form(""),
    modulus_gpa: str = Form(""),
    hdt_c: str = Form(""),
    continuous_service_c: str = Form(""),
    moisture_sensitivity: str = Form(""),
    water_resistance: str = Form(""),
    chemical_resistance: str = Form(""),
    uv_resistance: str = Form(""),
    creep_resistance: str = Form(""),
    flame_resistance: str = Form(""),
    impact_note: str = Form(""),
    shrinkage_note: str = Form(""),
    source_notes: str = Form(""),
    session: Session = Depends(get_session),
):
    material = session.scalar(select(Material).where(Material.slug == slug))
    if not material:
        raise HTTPException(status_code=404, detail="Material not found")

    cleaned_slug = material_slug(new_slug or name)
    if not cleaned_slug:
        raise HTTPException(status_code=400, detail="Material slug is required.")
    existing = session.scalar(select(Material).where(Material.slug == cleaned_slug, Material.id != material.id))
    if existing:
        raise HTTPException(status_code=409, detail="This material slug already exists.")

    settings_json, properties_json = merge_material_form_values(
        settings_json,
        properties_json,
        nozzle=nozzle,
        bed=bed,
        chamber=chamber,
        speed=speed,
        drying=drying,
        cooling=cooling,
        recommended_nozzle=recommended_nozzle,
        main_compatible=main_compatible,
        aux_compatible=aux_compatible,
        ams_compatible=ams_compatible,
        density_g_cm3=density_g_cm3,
        tensile_mpa=tensile_mpa,
        modulus_gpa=modulus_gpa,
        hdt_c=hdt_c,
        continuous_service_c=continuous_service_c,
        moisture_sensitivity=moisture_sensitivity,
        water_resistance=water_resistance,
        chemical_resistance=chemical_resistance,
        uv_resistance=uv_resistance,
        creep_resistance=creep_resistance,
        flame_resistance=flame_resistance,
        impact_note=impact_note,
        shrinkage_note=shrinkage_note,
    )
    material.name = name.strip()
    material.slug = cleaned_slug
    material.full_name = full_name.strip()
    material.family = family.strip()
    material.subfamily = subfamily.strip() or "Base polymer"
    material.family_color = family_color.strip() or "#64748b"
    material.formula = formula.strip() or "—"
    material.repeat_unit = repeat_unit.strip() or "—"
    material.description = description.strip()
    material.best_for = best_for.strip()
    material.avoid_for = avoid_for.strip()
    material.settings_json = settings_json
    material.properties_json = properties_json
    material.source_notes = source_notes.strip()
    session.commit()
    return RedirectResponse(f"/materials/{material.slug}", status_code=303)


@app.post("/materials/{slug}/promote")
def promote_catalog_material(slug: str, session: Session = Depends(get_session)):
    existing = session.scalar(select(Material).where(Material.slug == slug))
    if existing:
        return RedirectResponse(f"/materials/{existing.slug}/edit", status_code=303)

    payload = catalog_detail_payload(slug)
    if payload is None:
        raise HTTPException(status_code=404, detail="Catalog material not found")

    source_parts = [
        payload.get("source_notes", ""),
        f"Source title: {payload.get('source_title', '')}" if payload.get("source_title") else "",
        f"Source URL: {payload.get('source_url', '')}" if payload.get("source_url") else "",
    ]
    material = Material(
        name=payload["name"],
        slug=payload["slug"],
        full_name=payload["full_name"],
        family=payload["family"],
        subfamily=payload["subfamily"],
        family_color=payload["family_color"],
        formula=payload["formula"],
        repeat_unit=payload["repeat_unit"],
        description=payload["description"],
        best_for=payload["best_for"],
        avoid_for=payload["avoid_for"],
        settings_json=pretty_json(payload["settings"]),
        properties_json=pretty_json(payload["properties"]),
        source_notes=" ".join(part for part in source_parts if part).strip(),
    )
    session.add(material)
    session.commit()
    return RedirectResponse(f"/materials/{material.slug}/edit", status_code=303)


@app.get("/materials/{slug}")
def material_detail(slug: str, request: Request, session: Session = Depends(get_session)):
    printers = active_printers(session)
    material = session.scalar(
        select(Material)
        .options(
            selectinload(Material.products).selectinload(FilamentProduct.price_entries),
            selectinload(Material.products).selectinload(FilamentProduct.print_profiles),
            selectinload(Material.print_profiles).selectinload(PrintProfile.product),
            selectinload(Material.print_profiles).selectinload(PrintProfile.printer),
        )
        .where(Material.slug == slug)
    )
    if not material:
        payload = catalog_detail_payload(slug, printers=printers)
        if payload is None:
            raise HTTPException(status_code=404, detail="Material not found")
        return page(
            request,
            "material_detail.html",
            page_name="materials",
            material=payload,
            profiles=[],
            printers=[printer_payload(printer) for printer in printers],
        )
    payload = material_payload(material, printers=printers)
    profiles = [profile_payload(p) for p in material.print_profiles]
    return page(
        request,
        "material_detail.html",
        page_name="materials",
        material=payload,
        profiles=profiles,
        printers=[printer_payload(printer) for printer in printers],
    )


@app.post("/materials/{slug}/products")
def add_product(
    slug: str,
    brand: str = Form(...),
    product_name: str = Form(...),
    supplier: str = Form(""),
    url: str = Form(""),
    color_name: str = Form(""),
    spool_code: str = Form(""),
    spool_weight_g: float = Form(1000),
    first_price_eur: float | None = Form(None),
    notes: str = Form(""),
    favorite: bool = Form(False),
    session: Session = Depends(get_session),
):
    material = session.scalar(select(Material).where(Material.slug == slug))
    if not material:
        raise HTTPException(status_code=404, detail="Material not found")
    cleaned_spool_code = clean_text(spool_code)
    if cleaned_spool_code:
        ensure_unique_spool_code(session, cleaned_spool_code)
    product = FilamentProduct(
        material_id=material.id, brand=brand.strip(), product_name=product_name.strip(), supplier=supplier.strip(), url=url.strip(),
        color_name=color_name.strip(), spool_code=cleaned_spool_code, spool_weight_g=spool_weight_g, notes=notes.strip(), favorite=favorite,
    )
    session.add(product)
    session.flush()
    if not product.spool_code:
        generated_spool_code = f"S-{product.id:03d}"
        ensure_unique_spool_code(session, generated_spool_code, current_product_id=product.id)
        product.spool_code = generated_spool_code
    if first_price_eur is not None and first_price_eur > 0:
        session.add(PriceEntry(product_id=product.id, price_eur=first_price_eur, observed_on=date.today(), source_label="Initial manual price"))
    session.commit()
    return RedirectResponse(f"/materials/{slug}#products", status_code=303)


@app.get("/spools/{spool_code}")
def spool_detail(spool_code: str, request: Request, session: Session = Depends(get_session)):
    product = product_by_spool_code(session, spool_code)
    if not product:
        raise HTTPException(status_code=404, detail="Spool not found")
    profiles = [profile_payload(profile) for profile in product.print_profiles]
    return page(
        request,
        "spool_detail.html",
        page_name="inventory",
        product=spool_page_payload(product),
        profiles=profiles,
    )


@app.get("/spools/{spool_code}/edit")
def edit_spool_form(spool_code: str, request: Request, session: Session = Depends(get_session)):
    product = product_by_spool_code(session, spool_code)
    if not product:
        raise HTTPException(status_code=404, detail="Spool not found")
    materials = list(
        session.scalars(
            select(Material)
            .where(Material.is_active.is_(True))
            .order_by(Material.family, Material.name)
        )
    )
    return page(
        request,
        "spool_form.html",
        page_name="inventory",
        product=spool_page_payload(product),
        materials=materials,
    )


@app.post("/spools/{spool_code}/edit")
def update_spool(
    spool_code: str,
    material_id: int = Form(...),
    brand: str = Form(...),
    product_name: str = Form(...),
    supplier: str = Form(""),
    url: str = Form(""),
    color_name: str = Form(""),
    new_spool_code: str = Form(""),
    spool_weight_g: float = Form(1000),
    notes: str = Form(""),
    favorite: bool = Form(False),
    is_active: bool = Form(False),
    session: Session = Depends(get_session),
):
    product = product_by_spool_code(session, spool_code)
    if not product:
        raise HTTPException(status_code=404, detail="Spool not found")
    material = session.scalar(select(Material).where(Material.id == material_id, Material.is_active.is_(True)))
    if not material:
        raise HTTPException(status_code=404, detail="Material not found")
    if spool_weight_g <= 0:
        raise HTTPException(status_code=400, detail="Spool mass must be greater than zero.")

    cleaned_spool_code = clean_text(new_spool_code) or display_spool_code(product)
    ensure_unique_spool_code(session, cleaned_spool_code, current_product_id=product.id)
    product.material_id = material.id
    for profile in product.print_profiles:
        profile.material_id = material.id
    product.brand = brand.strip()
    product.product_name = product_name.strip()
    product.supplier = supplier.strip()
    product.url = url.strip()
    product.color_name = color_name.strip()
    product.spool_code = cleaned_spool_code
    product.spool_weight_g = spool_weight_g
    product.notes = notes.strip()
    product.favorite = favorite
    product.is_active = is_active
    session.commit()
    return RedirectResponse(spool_path(product), status_code=303)


@app.post("/products/{product_id}/archive")
def archive_product(
    product_id: int,
    return_to: str = Form("/inventory"),
    session: Session = Depends(get_session),
):
    product = session.get(FilamentProduct, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    product.is_active = False
    session.commit()
    return RedirectResponse(return_to or "/inventory", status_code=303)


@app.post("/products/{product_id}/restore")
def restore_product(
    product_id: int,
    return_to: str = Form("/inventory#archived"),
    session: Session = Depends(get_session),
):
    product = session.get(FilamentProduct, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    product.is_active = True
    if not product.spool_code:
        product.spool_code = f"S-{product.id:03d}"
    session.commit()
    return RedirectResponse(return_to or "/inventory#archived", status_code=303)


@app.post("/products/{product_id}/delete")
def delete_product(
    product_id: int,
    return_to: str = Form("/inventory"),
    session: Session = Depends(get_session),
):
    product = session.scalar(
        select(FilamentProduct)
        .options(selectinload(FilamentProduct.print_profiles))
        .where(FilamentProduct.id == product_id)
    )
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    for profile in product.print_profiles:
        profile.product_id = None
    session.delete(product)
    session.commit()
    return RedirectResponse(return_to or "/inventory", status_code=303)


@app.post("/products/{product_id}/prices")
def add_price(
    product_id: int,
    price_eur: float = Form(...),
    observed_on: str = Form(""),
    source_label: str = Form("Manual entry"),
    stock_note: str = Form(""),
    return_to: str = Form(""),
    session: Session = Depends(get_session),
):
    product = session.get(FilamentProduct, product_id)
    if not product or not product.is_active:
        raise HTTPException(status_code=404, detail="Product not found")
    try:
        observed_date = date.fromisoformat(clean_text(observed_on)) if clean_text(observed_on) else date.today()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Price date is invalid.") from exc
    session.add(PriceEntry(
        product_id=product_id, price_eur=price_eur, observed_on=observed_date,
        source_label=source_label.strip(), stock_note=stock_note.strip(),
    ))
    session.commit()
    return RedirectResponse(return_to or f"/materials/{product.material.slug}#products", status_code=303)


@app.post("/materials/{slug}/profiles")
def add_profile(
    slug: str,
    profile_name: str = Form(...),
    product_id: str = Form(""),
    printer_id: str = Form(""),
    state: str = Form("Dry"),
    nozzle_diameter: float = Form(0.4),
    nozzle_temp: float = Form(0),
    bed_temp: float = Form(0),
    chamber_temp: float = Form(0),
    speed_mm_s: float = Form(0),
    dryer_temp: float = Form(0),
    dryer_hours: float = Form(0),
    build_plate: str = Form(""),
    filament_used_g: float = Form(0),
    result_rating: int = Form(3),
    notes: str = Form(""),
    printed_on: date = Form(date.today()),
    session: Session = Depends(get_session),
):
    material = session.scalar(select(Material).where(Material.slug == slug))
    if not material:
        raise HTTPException(status_code=404, detail="Material not found")
    product_pk = int(product_id) if clean_text(product_id) else None
    printer_pk = int(printer_id) if clean_text(printer_id) else None
    if product_pk is not None:
        product = session.get(FilamentProduct, product_pk)
        if not product or not product.is_active or product.material_id != material.id:
            raise HTTPException(status_code=404, detail="Spool not found")
    if printer_pk is not None:
        printer = session.get(PrinterPreset, printer_pk)
        if not printer or not printer.is_active:
            raise HTTPException(status_code=404, detail="Printer preset not found")
    profile = PrintProfile(
        material_id=material.id, product_id=product_pk, printer_id=printer_pk,
        profile_name=profile_name.strip(), state=state,
        nozzle_diameter=nozzle_diameter, nozzle_temp=nozzle_temp, bed_temp=bed_temp, chamber_temp=chamber_temp,
        speed_mm_s=speed_mm_s, dryer_temp=dryer_temp, dryer_hours=dryer_hours, build_plate=build_plate.strip(),
        filament_used_g=max(0, filament_used_g), result_rating=max(1, min(5, result_rating)),
        notes=notes.strip(), printed_on=printed_on,
    )
    session.add(profile)
    session.commit()
    return RedirectResponse(f"/materials/{slug}#profiles", status_code=303)


@app.get("/guide")
def guide_page(request: Request, session: Session = Depends(get_session)):
    printers = active_printers(session)
    materials = [material_payload(m, include_products=False, printers=printers) for m in all_materials(session)]
    catalog_materials = catalog_entries({m["slug"] for m in materials}, printers=printers)
    materials.extend(catalog_materials)
    return page(
        request,
        "guide.html",
        page_name="guide",
        materials=materials,
        printers=[printer_payload(printer) for printer in printers],
    )


@app.get("/compare")
def compare_page(request: Request, session: Session = Depends(get_session)):
    printers = active_printers(session)
    materials = [material_payload(m, include_products=False, printers=printers) for m in all_materials(session)]
    catalog_materials = catalog_entries({m["slug"] for m in materials}, printers=printers)
    materials.extend(catalog_materials)
    return page(request, "compare.html", page_name="compare", materials=materials, materials_json=json.dumps(materials))


@app.get("/calculator")
def calculator_page(request: Request, session: Session = Depends(get_session)):
    materials = all_materials(session)
    product_rows = []
    for material in materials:
        for product in active_products(material.products):
            product_rows.append({
                **product_payload(product), "material_slug": material.slug, "material_name": material.name,
                "density_g_cm3": parse_json(material.properties_json).get("density_g_cm3", 1.0),
            })
    return page(request, "calculator.html", page_name="calculator", products=product_rows, products_json=json.dumps(product_rows))


@app.get("/inventory")
def inventory_page(request: Request, session: Session = Depends(get_session)):
    products = list(
        session.scalars(
            select(FilamentProduct)
            .options(selectinload(FilamentProduct.material), selectinload(FilamentProduct.price_entries))
            .options(selectinload(FilamentProduct.print_profiles))
            .order_by(FilamentProduct.favorite.desc(), FilamentProduct.brand, FilamentProduct.product_name)
        )
    )
    active_rows = [product for product in products if product.is_active]
    archived_rows = [product for product in products if not product.is_active]
    profiles = list(
        session.scalars(
            select(PrintProfile)
            .options(
                selectinload(PrintProfile.material),
                selectinload(PrintProfile.product),
                selectinload(PrintProfile.printer),
            )
            .order_by(PrintProfile.printed_on.desc(), PrintProfile.id.desc())
        )
    )
    return page(
        request, "inventory.html", page_name="inventory",
        products=[{**product_payload(p), "material_name": p.material.name, "material_slug": p.material.slug} for p in active_rows],
        archived_products=[{**product_payload(p), "material_name": p.material.name, "material_slug": p.material.slug} for p in archived_rows],
        profiles=[{**profile_payload(p), "material_name": p.material.name, "material_slug": p.material.slug} for p in profiles],
    )


@app.get("/settings")
def settings_page(request: Request, session: Session = Depends(get_session)):
    materials = all_materials(session)
    printers = active_printers(session)
    return page(
        request, "settings.html", page_name="settings", db_path=str(DB_PATH), data_dir=str(DATA_DIR),
        material_count=len(materials), product_count=sum(len(active_products(m.products)) for m in materials),
        printers=[printer_payload(printer) for printer in printers],
    )


@app.post("/settings/printers")
def add_printer(
    name: str = Form(...),
    nozzle_max_c: float = Form(300),
    bed_max_c: float = Form(100),
    enclosed: bool = Form(False),
    direct_drive: bool = Form(True),
    supports_flexible: bool = Form(True),
    ams_capable: bool = Form(False),
    notes: str = Form(""),
    session: Session = Depends(get_session),
):
    base_slug = slugify(name)
    slug = base_slug
    counter = 2
    while session.scalar(select(PrinterPreset.id).where(PrinterPreset.slug == slug)):
        slug = f"{base_slug}-{counter}"
        counter += 1

    session.add(
        PrinterPreset(
            slug=slug,
            name=clean_text(name),
            nozzle_max_c=nozzle_max_c,
            bed_max_c=bed_max_c,
            enclosed=enclosed,
            direct_drive=direct_drive,
            supports_flexible=supports_flexible,
            ams_capable=ams_capable,
            notes=clean_text(notes),
        )
    )
    session.commit()
    return RedirectResponse("/settings#printers", status_code=303)


@app.get("/api/materials")
def api_materials(session: Session = Depends(get_session)):
    printers = active_printers(session)
    materials = [material_payload(m, printers=printers) for m in all_materials(session)]
    materials.extend(catalog_entries({m["slug"] for m in materials}, printers=printers))
    return JSONResponse(materials)


@app.get("/api/materials/{slug}")
def api_material(slug: str, session: Session = Depends(get_session)):
    printers = active_printers(session)
    material = session.scalar(
        select(Material)
        .options(selectinload(Material.products).selectinload(FilamentProduct.price_entries))
        .where(Material.slug == slug)
    )
    if not material:
        payload = catalog_detail_payload(slug, printers=printers)
        if payload is None:
            raise HTTPException(status_code=404, detail="Material not found")
        return JSONResponse(payload)
    return JSONResponse(material_payload(material, printers=printers))


@app.get("/api/calculate")
def api_calculate(
    product_id: int,
    model_volume_mm3: float,
    support_volume_mm3: float = 0,
    purge_g: float = 0,
    waste_percent: float = 0,
    energy_kwh: float = 0,
    electricity_eur_kwh: float = 0,
    session: Session = Depends(get_session),
):
    product = session.scalar(
        select(FilamentProduct)
        .options(selectinload(FilamentProduct.material), selectinload(FilamentProduct.price_entries))
        .where(FilamentProduct.id == product_id)
    )
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    props = parse_json(product.material.properties_json)
    density = float(props.get("density_g_cm3", 1.0))
    raw_part_g = max(0, model_volume_mm3) * density / 1000
    raw_support_g = max(0, support_volume_mm3) * density / 1000
    before_waste_g = raw_part_g + raw_support_g + max(0, purge_g)
    total_g = before_waste_g * (1 + max(0, waste_percent) / 100)
    _, price_per_kg, _ = product_price(product)
    material_cost = (total_g / 1000 * price_per_kg) if price_per_kg is not None else None
    energy_cost = max(0, energy_kwh) * max(0, electricity_eur_kwh)
    return {
        "material": product.material.name,
        "product": f"{product.brand} {product.product_name}",
        "density_g_cm3": density,
        "part_mass_g": round(raw_part_g, 2),
        "support_mass_g": round(raw_support_g, 2),
        "purge_mass_g": round(max(0, purge_g), 2),
        "total_mass_g": round(total_g, 2),
        "price_per_kg": round(price_per_kg, 2) if price_per_kg is not None else None,
        "material_cost_eur": round(material_cost, 2) if material_cost is not None else None,
        "energy_cost_eur": round(energy_cost, 2),
        "total_cost_eur": round((material_cost or 0) + energy_cost, 2) if material_cost is not None else None,
    }


@app.get("/api/export")
def api_export(session: Session = Depends(get_session)):
    materials = all_materials(session)
    all_profiles = list(
        session.scalars(
            select(PrintProfile).options(
                selectinload(PrintProfile.product),
                selectinload(PrintProfile.printer),
            )
        ).all()
    )
    payload = {
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "schema": "material-lab/v1",
        "materials": [material_payload(m) for m in materials],
        "print_profiles": [profile_payload(p) for p in all_profiles],
    }
    backup_file = DATA_DIR / f"material-lab-export-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    backup_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return FileResponse(backup_file, media_type="application/json", filename=backup_file.name)


@app.post("/api/backup")
def api_backup():
    backup_dir = DATA_DIR / "backups"
    backup_dir.mkdir(exist_ok=True)
    target = backup_dir / f"material_lab-{datetime.now().strftime('%Y%m%d-%H%M%S')}.sqlite3"
    with sqlite3.connect(DB_PATH) as source, sqlite3.connect(target) as destination:
        source.backup(destination)
    return JSONResponse({"ok": True, "backup": str(target)})
