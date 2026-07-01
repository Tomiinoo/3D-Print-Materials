from __future__ import annotations

import json
import re
import shutil
import sqlite3
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import quote

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .database import Base, DB_PATH, DATA_DIR, SessionLocal, engine, get_session
from .catalog import catalog_entries, catalog_entry_by_slug
from .models import (
    FilamentProduct,
    Material,
    NozzleCatalogItem,
    PriceEntry,
    PrintAttachment,
    PrinterMaintenance,
    PrinterNozzle,
    PrinterPreset,
    PrinterTool,
    PrintProfile,
)
from .seed import ensure_printer_tools, seed_materials, seed_nozzle_catalog, seed_printer_presets
from .v2_routes import router as v2_router

APP_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = DATA_DIR / "uploads"
PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MODEL_EXTENSIONS = {".stl", ".3mf"}
PHOTO_MAX_BYTES = 20 * 1024 * 1024
MODEL_MAX_BYTES = 100 * 1024 * 1024
NOZZLE_MATERIAL_OPTIONS = [
    "brass",
    "hardened steel",
    "stainless steel",
    "ruby / abrasive-resistant",
    "other",
]
NOZZLE_INVENTORY_STATUS_OPTIONS = ["installed", "spare", "removed", "worn", "archived"]
COMPATIBILITY_STATUS_LABELS = {
    "recommended": "Recommended",
    "precautions": "Compatible with precautions",
    "needs_confirmation": "Needs hardware confirmation",
    "not_recommended": "Not recommended",
    "not_supported": "Not supported",
}
COMPATIBILITY_STATUS_RANK = {
    "recommended": 5,
    "precautions": 4,
    "needs_confirmation": 3,
    "not_recommended": 2,
    "not_supported": 1,
}
MAINTENANCE_TYPE_OPTIONS = [
    "part replaced",
    "service",
    "repair",
    "upgrade",
    "inspection",
    "other",
]


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        seed_materials(session)
        seed_nozzle_catalog(session)
        seed_printer_presets(session)
        ensure_printer_tools(session)
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
    {"key": "ams-compatible", "label": "Works with AMS / automatic feeder"},
    {"key": "hardened-nozzle", "label": "Needs hardened nozzle"},
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


def parse_form_date(value: str | date | None, field_name: str) -> date:
    if isinstance(value, date):
        return value
    cleaned = clean_text(value)
    if not cleaned:
        return date.today()
    try:
        return date.fromisoformat(cleaned)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"{field_name} is invalid.") from exc


def parse_optional_form_date(value: str | date | None, field_name: str) -> date | None:
    if isinstance(value, date):
        return value
    cleaned = clean_text(value)
    if not cleaned:
        return None
    return parse_form_date(cleaned, field_name)


def parse_optional_float(value: str | float | None) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Number value is invalid.") from exc


def parse_optional_nonnegative_float(value: str | float | None) -> float | None:
    number = parse_optional_float(value)
    return max(0, number) if number is not None else None


def upload_root() -> Path:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    return UPLOAD_DIR


def validate_upload_filename(filename: str) -> tuple[str, str, int]:
    original = clean_text(filename)
    if not original or "/" in original or "\\" in original or Path(original).name != original or original in {".", ".."}:
        raise HTTPException(status_code=400, detail="Uploaded file name is invalid.")

    extension = Path(original).suffix.lower()
    if extension in PHOTO_EXTENSIONS:
        return extension, "photo", PHOTO_MAX_BYTES
    if extension in MODEL_EXTENSIONS:
        return extension, "model", MODEL_MAX_BYTES
    raise HTTPException(status_code=400, detail="Only JPG, PNG, WEBP, STL and 3MF uploads are allowed.")


def stored_upload_path(relative_path: str) -> Path:
    root = upload_root().resolve()
    candidate = (root / relative_path).resolve()
    if candidate != root and root not in candidate.parents:
        raise HTTPException(status_code=400, detail="Attachment path is invalid.")
    return candidate


def delete_stored_upload(relative_path: str) -> None:
    try:
        target = stored_upload_path(relative_path)
    except HTTPException:
        return
    if target.exists() and target.is_file():
        target.unlink()


def delete_attachment_file(attachment: PrintAttachment) -> None:
    delete_stored_upload(attachment.stored_relative_path)


def store_profile_attachment(upload: UploadFile, profile_id: int) -> PrintAttachment | None:
    if not upload.filename:
        return None

    extension, category, max_bytes = validate_upload_filename(upload.filename)
    target_dir = upload_root() / "print-profiles" / str(profile_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{uuid.uuid4().hex}{extension}"
    total = 0

    try:
        with target.open("wb") as output:
            while True:
                chunk = upload.file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise HTTPException(status_code=400, detail=f"{upload.filename} exceeds the upload size limit.")
                output.write(chunk)
    except Exception:
        if target.exists():
            target.unlink()
        raise

    if total <= 0:
        target.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Uploaded files cannot be empty.")

    return PrintAttachment(
        print_profile_id=profile_id,
        original_filename=Path(upload.filename).name,
        stored_relative_path=target.relative_to(upload_root()).as_posix(),
        file_category=category,
        mime_type=upload.content_type or "application/octet-stream",
        file_size=total,
    )


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
            .options(
                selectinload(PrinterPreset.nozzles).selectinload(PrinterNozzle.print_profiles),
                selectinload(PrinterPreset.nozzles).selectinload(PrinterNozzle.catalog_item),
                selectinload(PrinterPreset.nozzles).selectinload(PrinterNozzle.tool),
                selectinload(PrinterPreset.tools).selectinload(PrinterTool.nozzles),
                selectinload(PrinterPreset.print_profiles),
                selectinload(PrinterPreset.maintenance_entries),
            )
            .where(PrinterPreset.is_active.is_(True))
            .order_by(PrinterPreset.name)
        )
    )


def all_printers(session: Session) -> list[PrinterPreset]:
    return list(
        session.scalars(
            select(PrinterPreset)
            .options(
                selectinload(PrinterPreset.nozzles).selectinload(PrinterNozzle.print_profiles),
                selectinload(PrinterPreset.nozzles).selectinload(PrinterNozzle.catalog_item),
                selectinload(PrinterPreset.nozzles).selectinload(PrinterNozzle.tool),
                selectinload(PrinterPreset.tools).selectinload(PrinterTool.nozzles),
                selectinload(PrinterPreset.print_profiles),
                selectinload(PrinterPreset.maintenance_entries),
            )
            .order_by(PrinterPreset.is_active.desc(), PrinterPreset.name)
        )
    )


def format_hours(value: float | None, empty: str = "No tracked hours yet") -> str:
    if value is None or value <= 0:
        return empty
    if value >= 10:
        return f"{value:.0f} h"
    return f"{value:.1f} h"


def nozzle_tracked_hours(nozzle: PrinterNozzle) -> float:
    return max(0, nozzle.hours_before_tracking or 0) + sum(
        max(0, profile.print_duration_hours or 0)
        for profile in nozzle.print_profiles
    )


def printer_tracked_hours(printer: PrinterPreset) -> float:
    return max(0, printer.hours_before_tracking or 0) + sum(
        max(0, profile.print_duration_hours or 0)
        for profile in printer.print_profiles
    )


def active_printer_tools(printer: PrinterPreset) -> list[PrinterTool]:
    return sorted(
        [tool for tool in printer.tools if tool.is_active],
        key=lambda item: (item.tool_order, item.id),
    )


def installed_nozzle(printer: PrinterPreset, tool: PrinterTool | None = None) -> PrinterNozzle | None:
    candidates = [nozzle for nozzle in printer.nozzles if nozzle.installed and nozzle.is_active]
    if tool is not None:
        candidates = [nozzle for nozzle in candidates if nozzle.tool_id == tool.id]
    return next(iter(candidates), None)


def nullable_bool_label(value: bool | None, true_label: str = "Yes", false_label: str = "No") -> str:
    if value is None:
        return "Unknown"
    return true_label if value else false_label


def nozzle_payload(nozzle: PrinterNozzle) -> dict[str, Any]:
    tracked_hours = nozzle_tracked_hours(nozzle)
    catalog = nozzle.catalog_item
    max_temp = nozzle.max_temp_c if nozzle.max_temp_c is not None else (catalog.max_temp_c if catalog else None)
    abrasive_ready = nozzle.abrasive_ready
    if abrasive_ready is None and catalog:
        abrasive_ready = catalog.abrasive_ready
    return {
        "id": nozzle.id,
        "printer_id": nozzle.printer_id,
        "tool_id": nozzle.tool_id,
        "tool_name": nozzle.tool.name if nozzle.tool else "",
        "catalog_item_id": nozzle.catalog_item_id,
        "label": nozzle.label,
        "diameter_mm": nozzle.diameter_mm,
        "nozzle_material": nozzle.nozzle_material,
        "brand_product": nozzle.brand_product,
        "manufacturer": nozzle.manufacturer,
        "part_number": nozzle.part_number,
        "nozzle_system": nozzle.nozzle_system,
        "max_temp_c": max_temp,
        "max_temp_label": f"{max_temp:g} °C" if max_temp is not None else "Unknown",
        "abrasive_ready": abrasive_ready,
        "abrasive_ready_label": nullable_bool_label(abrasive_ready, "Abrasive-ready", "Not abrasive-ready"),
        "carbon_fibre_suitable": nozzle.carbon_fibre_suitable if nozzle.carbon_fibre_suitable is not None else (catalog.carbon_fibre_suitable if catalog else None),
        "glass_fibre_suitable": nozzle.glass_fibre_suitable if nozzle.glass_fibre_suitable is not None else (catalog.glass_fibre_suitable if catalog else None),
        "high_flow": nozzle.high_flow if nozzle.high_flow is not None else (catalog.high_flow if catalog else None),
        "inventory_status": nozzle.inventory_status or ("installed" if nozzle.installed else ("spare" if nozzle.is_active else "archived")),
        "installed": nozzle.installed,
        "is_active": nozzle.is_active,
        "installed_on": nozzle.installed_on.isoformat() if nozzle.installed_on else "",
        "hours_before_tracking": nozzle.hours_before_tracking,
        "tracked_hours": tracked_hours,
        "tracked_hours_label": format_hours(tracked_hours),
        "print_count": len(nozzle.print_profiles),
        "catalog_name": catalog.display_name if catalog else "",
        "notes": public_text(nozzle.notes),
    }


def tool_payload(tool: PrinterTool) -> dict[str, Any]:
    installed = next((nozzle for nozzle in tool.nozzles if nozzle.installed and nozzle.is_active), None)
    return {
        "id": tool.id,
        "printer_id": tool.printer_id,
        "name": tool.name,
        "tool_order": tool.tool_order,
        "is_active": tool.is_active,
        "max_hotend_c": tool.max_hotend_c,
        "nozzle_system": tool.nozzle_system,
        "supported_feed_routes": tool.supported_feed_routes,
        "notes": public_text(tool.notes),
        "installed_nozzle": nozzle_payload(installed) if installed else None,
        "nozzle_count": len([nozzle for nozzle in tool.nozzles if nozzle.is_active]),
    }


def maintenance_payload(entry: PrinterMaintenance) -> dict[str, Any]:
    return {
        "id": entry.id,
        "printer_id": entry.printer_id,
        "maintenance_date": entry.maintenance_date.isoformat(),
        "maintenance_type": entry.maintenance_type,
        "component": entry.component,
        "notes": public_text(entry.notes),
        "cost_eur": entry.cost_eur,
        "printer_hours": entry.printer_hours,
    }


def printer_payload(printer: PrinterPreset) -> dict[str, Any]:
    installed = installed_nozzle(printer)
    tracked_hours = printer_tracked_hours(printer)
    last_maintenance = next(iter(printer.maintenance_entries), None)
    tools = active_printer_tools(printer)
    return {
        "id": printer.id,
        "slug": printer.slug,
        "name": printer.name,
        "description": public_text(printer.description),
        "printer_type": printer.printer_type,
        "nozzle_max_c": printer.nozzle_max_c,
        "bed_max_c": printer.bed_max_c,
        "chamber_max_c": printer.chamber_max_c,
        "enclosed": printer.enclosed,
        "heated_chamber": printer.heated_chamber,
        "direct_drive": printer.direct_drive,
        "supports_flexible": printer.supports_flexible,
        "ams_capable": printer.ams_capable,
        "build_volume": printer.build_volume,
        "purchase_date": printer.purchase_date.isoformat() if printer.purchase_date else "",
        "serial_number": printer.serial_number,
        "hours_before_tracking": printer.hours_before_tracking,
        "tracked_hours": tracked_hours,
        "tracked_hours_label": format_hours(tracked_hours),
        "print_count": len(printer.print_profiles),
        "nozzle_count": len([nozzle for nozzle in printer.nozzles if nozzle.is_active]),
        "tool_count": len(tools),
        "tools": [tool_payload(tool) for tool in tools],
        "installed_nozzle": nozzle_payload(installed) if installed else None,
        "last_maintenance_date": last_maintenance.maintenance_date.isoformat() if last_maintenance else "",
        "nozzles": [nozzle_payload(nozzle) for nozzle in printer.nozzles],
        "maintenance_entries": [maintenance_payload(entry) for entry in printer.maintenance_entries],
        "notes": public_text(printer.notes),
        "is_active": printer.is_active,
    }


def printer_can_delete(printer: PrinterPreset) -> bool:
    return not printer.print_profiles and not printer.nozzles and not printer.maintenance_entries


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


def setting_text(settings: dict[str, Any], key: str) -> str:
    return clean_text(str(settings.get(key) or ""))


def material_identity_text(material: Material, settings: dict[str, Any]) -> str:
    return " ".join(
        clean_text(str(part)).lower()
        for part in (
            material.name,
            material.full_name,
            material.family,
            material.subfamily,
            settings.get("recommended_nozzle"),
        )
    )


def material_requires_abrasive(material: Material, settings: dict[str, Any]) -> bool:
    text = material_identity_text(material, settings)
    tokens = text_tokens(text)
    return token_has(tokens, "cf", "gf", "carbon", "glass", "fiber", "fibre", "abrasive", "filled") or text_has(
        text,
        "hardened",
        "tungsten",
        "ruby",
        "tc",
        "abrasive",
    )


def material_reinforcement_kind(material: Material) -> str:
    text = f"{material.name} {material.full_name} {material.subfamily}".lower()
    tokens = text_tokens(text)
    if token_has(tokens, "cf", "carbon") or text_has(text, "carbon fibre", "carbon fiber"):
        return "carbon"
    if token_has(tokens, "gf", "glass") or text_has(text, "glass fibre", "glass fiber"):
        return "glass"
    return ""


def material_is_flexible(material: Material) -> bool:
    family = clean_text(material.family).lower()
    subfamily = clean_text(material.subfamily).lower()
    name = clean_text(material.name).lower()
    return "elastomer" in family or "flex" in subfamily or "tpu" in name or "tpe" in name


def material_is_support(material: Material) -> bool:
    family = clean_text(material.family).lower()
    subfamily = clean_text(material.subfamily).lower()
    name = clean_text(material.name).lower()
    return "support" in family or "support" in subfamily or name in {"pva", "bvoh"}


def material_requires_enclosure(settings: dict[str, Any]) -> bool:
    chamber_max = parsed_max_number(settings.get("chamber"))
    chamber_text = setting_text(settings, "chamber").lower()
    if chamber_max is not None and chamber_max > 40:
        return True
    return text_has(chamber_text, "enclosure", "chamber", "heated") and not text_has(
        chamber_text,
        "not needed",
        "ambient",
        "cool",
    )


def nozzle_bool(nozzle: PrinterNozzle | None, key: str) -> bool | None:
    if nozzle is None:
        return None
    direct = getattr(nozzle, key)
    if direct is not None:
        return direct
    if nozzle.catalog_item is not None:
        return getattr(nozzle.catalog_item, key)
    material = clean_text(nozzle.nozzle_material).lower()
    label = f"{nozzle.label} {nozzle.brand_product} {nozzle.manufacturer}".lower()
    if key in {"abrasive_ready", "carbon_fibre_suitable", "glass_fibre_suitable"}:
        if text_has(material, "hardened", "ruby", "tungsten", "carbide") or text_has(label, "hardened", "ruby", "tungsten", "carbide", "abrasive"):
            return True
        if text_has(material, "brass", "stainless"):
            return False
    return None


def nozzle_temp_limit(nozzle: PrinterNozzle | None) -> float | None:
    if nozzle is None:
        return None
    if nozzle.max_temp_c is not None:
        return nozzle.max_temp_c
    if nozzle.catalog_item and nozzle.catalog_item.max_temp_c is not None:
        return nozzle.catalog_item.max_temp_c
    return None


def installed_nozzle_for_tool(printer: PrinterPreset, tool: PrinterTool | None) -> PrinterNozzle | None:
    return installed_nozzle(printer, tool) if tool is not None else installed_nozzle(printer)


def fallback_tool_payload(printer: PrinterPreset) -> dict[str, Any]:
    return {
        "id": None,
        "name": "Installed nozzle compatibility",
        "tool_order": 1,
        "max_hotend_c": printer.nozzle_max_c,
        "nozzle_system": "",
        "supported_feed_routes": "standard filament path",
        "notes": "",
    }


def evaluate_material_on_tool(
    material: Material,
    settings: dict[str, Any],
    printer: PrinterPreset,
    tool: PrinterTool | None,
) -> dict[str, Any]:
    nozzle = installed_nozzle_for_tool(printer, tool)
    tool_limit = (tool.max_hotend_c if tool is not None else printer.nozzle_max_c) or printer.nozzle_max_c
    nozzle_limit = nozzle_temp_limit(nozzle)
    effective_limit = min(tool_limit, nozzle_limit) if tool_limit and nozzle_limit is not None else tool_limit
    effective_confirmed = nozzle is not None and nozzle_limit is not None
    required_nozzle = parsed_max_number(settings.get("nozzle"))
    required_bed = parsed_max_number(settings.get("bed"))
    required_chamber = parsed_max_number(settings.get("chamber"))
    requires_enclosure = material_requires_enclosure(settings)
    requires_abrasive = material_requires_abrasive(material, settings)
    reinforcement = material_reinforcement_kind(material)
    flexible = material_is_flexible(material)
    moisture = parsed_number(public_text(parse_json(material.properties_json)).get("moisture_sensitivity"))
    ams_ok = truthy_setting(settings.get("ams_compatible"), truthy_setting(settings.get("aux_compatible"), False) and not flexible and not material_is_support(material))

    blockers: list[str] = []
    confirmations: list[str] = []
    cautions: list[str] = []
    strengths: list[str] = []

    tool_name = tool.name if tool is not None else "Installed nozzle compatibility"
    nozzle_label = nozzle.label if nozzle else "No installed nozzle"

    if nozzle is None:
        confirmations.append("No installed nozzle is assigned to this tool.")
    elif not effective_confirmed:
        confirmations.append("Installed nozzle maximum safe temperature is unknown.")

    if required_nozzle is not None:
        if effective_confirmed and effective_limit is not None and required_nozzle > effective_limit:
            blockers.append(f"Effective nozzle temperature limit is {effective_limit:g} C, below the material guide of {required_nozzle:g} C.")
        elif effective_confirmed:
            strengths.append("Effective nozzle temperature is sufficient.")
        else:
            confirmations.append("Nozzle temperature compatibility cannot be fully verified.")

    if required_bed is not None and printer.bed_max_c and required_bed > printer.bed_max_c:
        blockers.append(f"Bed temperature limit is {printer.bed_max_c:g} C, below the material guide of {required_bed:g} C.")
    elif required_bed is not None:
        strengths.append("Bed temperature is sufficient.")

    if requires_enclosure and not printer.enclosed:
        blockers.append("Enclosure is required or strongly recommended, but this printer is open-frame.")
    elif requires_enclosure:
        strengths.append("Enclosure is available.")

    if required_chamber is not None and required_chamber > 45:
        if printer.chamber_max_c and required_chamber > printer.chamber_max_c:
            blockers.append(f"Chamber capability is {printer.chamber_max_c:g} C, below the material guide of {required_chamber:g} C.")
        elif not printer.heated_chamber and required_chamber > 50:
            cautions.append("A warm chamber is recommended; confirm the real chamber temperature.")
        elif printer.heated_chamber:
            strengths.append("Heated chamber capability is available.")

    if flexible and not printer.supports_flexible:
        blockers.append("Flexible material support is not confirmed for this printer.")

    if requires_abrasive:
        abrasive_ready = nozzle_bool(nozzle, "abrasive_ready")
        if abrasive_ready is True:
            strengths.append("Abrasive-ready nozzle is installed.")
        elif abrasive_ready is False:
            blockers.append("Material needs an abrasive-ready or hardened nozzle.")
        else:
            confirmations.append("Abrasive-nozzle suitability is unknown.")

    if reinforcement == "carbon":
        carbon_ok = nozzle_bool(nozzle, "carbon_fibre_suitable")
        if carbon_ok is False:
            blockers.append("Installed nozzle is not marked suitable for carbon-fibre materials.")
        elif carbon_ok is None:
            confirmations.append("Carbon-fibre nozzle suitability is unknown.")
    elif reinforcement == "glass":
        glass_ok = nozzle_bool(nozzle, "glass_fibre_suitable")
        if glass_ok is False:
            blockers.append("Installed nozzle is not marked suitable for glass-fibre materials.")
        elif glass_ok is None:
            confirmations.append("Glass-fibre nozzle suitability is unknown.")

    if printer.ams_capable and not ams_ok:
        cautions.append("AMS / automatic feeder is not recommended for this material.")
    if moisture is not None and moisture >= 6:
        cautions.append("Filament should be dried and kept dry before printing.")
    if nozzle and nozzle.diameter_mm < 0.6 and requires_abrasive and text_has(setting_text(settings, "recommended_nozzle").lower(), "0.6", "preferred"):
        cautions.append("A larger nozzle diameter is recommended for this filled material.")

    if blockers:
        status = "not_recommended"
    elif confirmations:
        status = "needs_confirmation"
    elif cautions:
        status = "precautions"
    else:
        status = "recommended"

    return {
        "tool_id": tool.id if tool is not None else None,
        "tool_name": tool_name,
        "nozzle_id": nozzle.id if nozzle else None,
        "nozzle_label": nozzle_label,
        "status": status,
        "status_label": COMPATIBILITY_STATUS_LABELS[status],
        "effective_max_c": effective_limit,
        "effective_max_confirmed": effective_confirmed,
        "required_nozzle_c": required_nozzle,
        "blockers": blockers,
        "confirmations": confirmations,
        "cautions": cautions,
        "strengths": strengths,
        "reasons": strengths + confirmations + cautions + blockers,
    }


def printer_compatibility_summary(printer: PrinterPreset, tool_results: list[dict[str, Any]]) -> dict[str, Any]:
    if not tool_results:
        status = "needs_confirmation"
        best_result = {
            "status": status,
            "status_label": COMPATIBILITY_STATUS_LABELS[status],
            "reasons": ["No active print tool is configured for this printer."],
        }
    else:
        best_result = max(tool_results, key=lambda item: COMPATIBILITY_STATUS_RANK.get(item["status"], 0))
        status = best_result["status"]

    if status == "recommended":
        summary = f"Compatible with {printer.name}"
    elif status == "precautions":
        summary = f"Compatible with {printer.name} with limitations"
    elif status == "needs_confirmation":
        summary = f"Needs nozzle confirmation on {printer.name}"
    elif status == "not_supported":
        summary = f"Not supported by {printer.name}"
    else:
        summary = f"Not recommended for {printer.name}"

    return {
        "printer_id": printer.id,
        "printer_slug": printer.slug,
        "printer_name": printer.name,
        "status": status,
        "status_label": COMPATIBILITY_STATUS_LABELS[status],
        "summary": summary,
        "filter_key": f"printer-{printer.slug}",
        "is_compatible_filter_match": status in {"recommended", "precautions"},
        "best_result": best_result,
        "tool_results": tool_results,
    }


def material_compatibility(
    material: Material,
    settings: dict[str, Any],
    printers: list[PrinterPreset] | None = None,
) -> dict[str, Any]:
    nozzle_max = parsed_max_number(settings.get("nozzle"))
    bed_max = parsed_max_number(settings.get("bed"))
    chamber_max = parsed_max_number(settings.get("chamber"))
    direct_ok = truthy_setting(settings.get("main_compatible"), True)
    aux_ok = truthy_setting(settings.get("aux_compatible"), False)
    flexible = material_is_flexible(material)
    support = material_is_support(material)
    ams_ok = truthy_setting(settings.get("ams_compatible"), aux_ok and not flexible and not support)
    requires_enclosure = material_requires_enclosure(settings)

    filter_keys: list[str] = []
    if ams_ok:
        filter_keys.append("ams-compatible")
    if material_requires_abrasive(material, settings):
        filter_keys.append("hardened-nozzle")

    printer_results: list[dict[str, Any]] = []
    compatible_filter_keys: list[str] = []
    for printer in printers or []:
        tools = active_printer_tools(printer)
        tool_results = [
            evaluate_material_on_tool(material, settings, printer, tool)
            for tool in tools
        ] if tools else [evaluate_material_on_tool(material, settings, printer, None)]
        summary = printer_compatibility_summary(printer, tool_results)
        printer_results.append(summary)
        if summary["is_compatible_filter_match"]:
            compatible_filter_keys.append(summary["filter_key"])
            filter_keys.append(summary["filter_key"])

    preferred = max(printer_results, key=lambda item: COMPATIBILITY_STATUS_RANK.get(item["status"], 0)) if printer_results else None

    return {
        "direct_path": direct_ok,
        "aux_path": aux_ok,
        "ams": ams_ok,
        "requires_enclosure": requires_enclosure,
        "printer_matches": compatible_filter_keys,
        "printer_match_labels": [item["printer_name"] for item in printer_results if item["is_compatible_filter_match"]],
        "printer_results": printer_results,
        "preferred_printer_result": preferred,
        "summary_label": preferred["summary"] if preferred else "No saved printer selected",
        "compatible_filter_keys": compatible_filter_keys,
        "filter_keys": sorted(set(filter_keys)),
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
        score_number = max(0.0, min(10.0, score_number))
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


def product_filament_usage(product: FilamentProduct) -> tuple[float, float, float]:
    used_g = sum(max(0, profile.filament_used_g or 0) for profile in product.print_profiles)
    remaining_g = max(0, (product.spool_weight_g or 0) - used_g)
    remaining_percent = (remaining_g / product.spool_weight_g * 100) if product.spool_weight_g else 0
    return used_g, remaining_g, remaining_percent


def product_last_profile(product: FilamentProduct) -> PrintProfile | None:
    if not product.print_profiles:
        return None
    return sorted(product.print_profiles, key=lambda profile: (profile.printed_on, profile.id), reverse=True)[0]


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
        selectinload(FilamentProduct.print_profiles).selectinload(PrintProfile.printer_nozzle),
        selectinload(FilamentProduct.print_profiles).selectinload(PrintProfile.attachments),
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
    used_g, remaining_g, remaining_percent = product_filament_usage(product)
    last_profile = product_last_profile(product)
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
        "filament_used_g": used_g,
        "remaining_g": remaining_g,
        "remaining_percent": remaining_percent,
        "buy_again_label": "Would buy again" if product.favorite else "Needs more evidence",
        "latest_price_eur": latest,
        "price_per_kg": per_kg,
        "price_observed_on": observed.isoformat() if observed else None,
        "last_printed_on": last_profile.printed_on.isoformat() if last_profile else None,
        "last_profile_name": last_profile.profile_name if last_profile else "",
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


def attachment_payload(attachment: PrintAttachment) -> dict[str, Any]:
    return {
        "id": attachment.id,
        "original_filename": attachment.original_filename,
        "file_category": attachment.file_category,
        "mime_type": attachment.mime_type,
        "file_size": attachment.file_size,
        "size_label": f"{attachment.file_size / 1024 / 1024:.1f} MB"
        if attachment.file_size >= 1024 * 1024
        else f"{max(1, round(attachment.file_size / 1024))} KB",
        "uploaded_at": attachment.uploaded_at.isoformat(),
        "download_path": f"/attachments/{attachment.id}/download",
        "delete_path": f"/attachments/{attachment.id}/delete",
        "is_photo": attachment.file_category == "photo",
    }


def profile_payload(profile: PrintProfile) -> dict[str, Any]:
    return {
        "id": profile.id,
        "profile_name": profile.profile_name,
        "state": profile.state,
        "material_id": profile.material_id,
        "product_id": profile.product_id,
        "printer_name": profile.printer.name if profile.printer else "",
        "printer_id": profile.printer_id,
        "printer_nozzle_id": profile.printer_nozzle_id,
        "nozzle_label": profile.printer_nozzle.label if profile.printer_nozzle else "",
        "nozzle_diameter": profile.nozzle_diameter,
        "nozzle_temp": profile.nozzle_temp,
        "bed_temp": profile.bed_temp,
        "chamber_temp": profile.chamber_temp,
        "speed_mm_s": profile.speed_mm_s,
        "dryer_temp": profile.dryer_temp,
        "dryer_hours": profile.dryer_hours,
        "build_plate": profile.build_plate,
        "filament_used_g": profile.filament_used_g,
        "print_duration_hours": profile.print_duration_hours,
        "print_duration_label": format_hours(profile.print_duration_hours, "-"),
        "result_rating": profile.result_rating,
        "notes": profile.notes,
        "printed_on": profile.printed_on.isoformat(),
        "material_name": profile.material.name if profile.material else "",
        "material_slug": profile.material.slug if profile.material else "",
        "product_name": f"{profile.product.brand} {profile.product.product_name}" if profile.product else None,
        "product_spool_code": display_spool_code(profile.product) if profile.product else None,
        "product_spool_path": spool_path(profile.product) if profile.product else None,
        "attachments": [attachment_payload(attachment) for attachment in profile.attachments],
        "edit_path": f"/profiles/{profile.id}/edit",
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
    page_labels = {
        "dashboard": "Dashboard",
        "inventory": "My Spools & Prints",
        "calculator": "Cost Calculator",
        "materials": "Material Library",
        "guide": "Material Guide",
        "compare": "Compare Materials",
        "printers": "Printers",
        "settings": "Settings",
    }
    nav_groups = [
        SimpleNamespace(
            label="Workshop",
            items=[
                ("Dashboard", "/", "dashboard"),
                ("My Spools & Prints", "/inventory", "inventory"),
                ("Cost Calculator", "/calculator", "calculator"),
            ],
        ),
        SimpleNamespace(
            label="Material Database",
            items=[
                ("Material Library", "/materials", "materials"),
                ("Material Guide", "/guide", "guide"),
                ("Compare Materials", "/compare", "compare"),
            ],
        ),
        SimpleNamespace(
            label="System",
            items=[
                ("Printers", "/printers", "printers"),
                ("Settings", "/settings", "settings"),
            ],
        ),
    ]
    defaults = {
        "request": request,
        "nav": [
            ("Dashboard", "/", "dashboard"),
            ("Material Library", "/materials", "materials"),
            ("Material Guide", "/guide", "guide"),
            ("Compare", "/compare", "compare"),
            ("Cost Calculator", "/calculator", "calculator"),
            ("My Spools & Prints", "/inventory", "inventory"),
            ("Printers", "/printers", "printers"),
            ("Settings", "/settings", "settings"),
        ],
        "nav_groups": nav_groups,
        "page_label": page_labels.get(context.get("page_name", ""), context.get("page_name", "")),
        "score_labels": SCORE_LABELS,
        "today": date.today().isoformat(),
    }
    defaults.update(context)
    return templates.TemplateResponse(request, template, defaults)


@app.get("/")
def dashboard(request: Request, session: Session = Depends(get_session)):
    materials = all_materials(session)
    printers = active_printers(session)
    material_data = [material_payload(m, printers=printers) for m in materials]
    products = list(
        session.scalars(
            select(FilamentProduct)
            .options(
                selectinload(FilamentProduct.material),
                selectinload(FilamentProduct.price_entries),
                selectinload(FilamentProduct.print_profiles),
            )
            .where(FilamentProduct.is_active.is_(True))
            .order_by(FilamentProduct.favorite.desc(), FilamentProduct.brand, FilamentProduct.product_name)
        )
    )
    profiles = list(
        session.scalars(
            select(PrintProfile)
            .options(
                selectinload(PrintProfile.material),
                selectinload(PrintProfile.product),
                selectinload(PrintProfile.printer),
                selectinload(PrintProfile.printer_nozzle),
                selectinload(PrintProfile.attachments),
            )
            .order_by(PrintProfile.printed_on.desc(), PrintProfile.id.desc())
            .limit(6)
        )
    )
    product_rows = [
        {**product_payload(product), "material_name": product.material.name, "material_slug": product.material.slug}
        for product in products
    ]
    low_stock_products = [product for product in product_rows if product["remaining_percent"] <= 20]
    no_price_products = [product for product in product_rows if product["price_per_kg"] is None]
    untested_products = [product for product in product_rows if product["profile_count"] == 0]
    stats = {
        "materials": len(materials),
        "products": len(product_rows),
        "remaining_g": sum(product["remaining_g"] for product in product_rows),
        "low_stock": len(low_stock_products),
        "no_price": len(no_price_products),
        "untested_spools": len(untested_products),
        "tested_profiles": len(session.scalars(select(PrintProfile)).all()),
        "families": len({m.family for m in materials}),
        "owned_materials": len({product["material_id"] for product in product_rows}),
    }
    attention_items = []
    for product in low_stock_products[:4]:
        attention_items.append({
            "kind": "Low stock",
            "text": f"{product['spool_code']} has {product['remaining_g']:.1f} g remaining.",
            "href": product["spool_path"],
            "tone": "warning",
        })
    for product in no_price_products[:3]:
        attention_items.append({
            "kind": "Missing price",
            "text": f"{product['spool_code']} has no price history.",
            "href": product["spool_path"],
            "tone": "warning",
        })
    for product in untested_products[:3]:
        attention_items.append({
            "kind": "No print result recorded yet",
            "text": f"{product['spool_code']} is ready for its first saved print result.",
            "href": product["spool_path"],
            "tone": "neutral",
        })
    return page(
        request,
        "dashboard.html",
        page_name="dashboard",
        materials=material_data[:6],
        products=product_rows[:6],
        recent_profiles=[
            {**profile_payload(profile), "material_name": profile.material.name, "material_slug": profile.material.slug}
            for profile in profiles
        ],
        attention_items=attention_items[:6],
        stats=stats,
    )


def printer_detail_options():
    return (
        selectinload(PrinterPreset.nozzles).selectinload(PrinterNozzle.print_profiles),
        selectinload(PrinterPreset.nozzles).selectinload(PrinterNozzle.catalog_item),
        selectinload(PrinterPreset.nozzles).selectinload(PrinterNozzle.tool),
        selectinload(PrinterPreset.tools).selectinload(PrinterTool.nozzles),
        selectinload(PrinterPreset.maintenance_entries),
        selectinload(PrinterPreset.print_profiles).selectinload(PrintProfile.material),
        selectinload(PrinterPreset.print_profiles).selectinload(PrintProfile.product),
        selectinload(PrinterPreset.print_profiles).selectinload(PrintProfile.printer),
        selectinload(PrinterPreset.print_profiles).selectinload(PrintProfile.printer_nozzle),
        selectinload(PrinterPreset.print_profiles).selectinload(PrintProfile.attachments),
    )


def printer_or_404(session: Session, printer_id: int) -> PrinterPreset:
    printer = session.scalar(
        select(PrinterPreset)
        .options(*printer_detail_options())
        .where(PrinterPreset.id == printer_id)
    )
    if not printer:
        raise HTTPException(status_code=404, detail="Printer not found")
    return printer


def nozzle_or_404(session: Session, printer_id: int, nozzle_id: int) -> PrinterNozzle:
    nozzle = session.scalar(
        select(PrinterNozzle)
        .options(selectinload(PrinterNozzle.print_profiles))
        .where(PrinterNozzle.id == nozzle_id, PrinterNozzle.printer_id == printer_id)
    )
    if not nozzle:
        raise HTTPException(status_code=404, detail="Nozzle not found")
    return nozzle


def maintenance_or_404(session: Session, printer_id: int, entry_id: int) -> PrinterMaintenance:
    entry = session.scalar(
        select(PrinterMaintenance)
        .where(PrinterMaintenance.id == entry_id, PrinterMaintenance.printer_id == printer_id)
    )
    if not entry:
        raise HTTPException(status_code=404, detail="Maintenance entry not found")
    return entry


def blank_printer_payload() -> dict[str, Any]:
    return {
        "name": "",
        "description": "",
        "printer_type": "FDM / FFF",
        "nozzle_max_c": 300,
        "bed_max_c": 100,
        "chamber_max_c": 0,
        "enclosed": False,
        "heated_chamber": False,
        "direct_drive": True,
        "supports_flexible": True,
        "ams_capable": False,
        "build_volume": "",
        "purchase_date": "",
        "serial_number": "",
        "hours_before_tracking": 0,
        "notes": "",
        "is_active": True,
        "tools": [
            {
                "id": None,
                "name": "Main print tool",
                "tool_order": 1,
                "is_active": True,
                "max_hotend_c": 300,
                "nozzle_system": "",
                "supported_feed_routes": "standard filament path",
                "notes": "",
            }
        ],
    }


def blank_nozzle_payload(printer_id: int) -> dict[str, Any]:
    return {
        "id": None,
        "printer_id": printer_id,
        "tool_id": None,
        "catalog_item_id": None,
        "label": "",
        "diameter_mm": 0.4,
        "nozzle_material": "brass",
        "brand_product": "",
        "manufacturer": "",
        "part_number": "",
        "nozzle_system": "",
        "max_temp_c": "",
        "abrasive_ready": None,
        "carbon_fibre_suitable": None,
        "glass_fibre_suitable": None,
        "high_flow": None,
        "inventory_status": "spare",
        "installed": False,
        "is_active": True,
        "installed_on": "",
        "hours_before_tracking": 0,
        "notes": "",
    }


def blank_maintenance_payload(printer_id: int) -> dict[str, Any]:
    return {
        "id": None,
        "printer_id": printer_id,
        "maintenance_date": date.today().isoformat(),
        "maintenance_type": "service",
        "component": "",
        "notes": "",
        "cost_eur": "",
        "printer_hours": "",
    }


def unique_printer_slug(session: Session, name: str, current_printer_id: int | None = None) -> str:
    base_slug = slugify(name)
    slug = base_slug
    counter = 2
    while True:
        existing = session.scalar(select(PrinterPreset).where(PrinterPreset.slug == slug))
        if not existing or existing.id == current_printer_id:
            return slug
        slug = f"{base_slug}-{counter}"
        counter += 1


def normalize_form_list(values: list[str] | None) -> list[str]:
    return list(values or [])


def sync_printer_tools(
    printer: PrinterPreset,
    tool_ids: list[str] | None,
    tool_names: list[str] | None,
    tool_max_hotend_c: list[str] | None,
    tool_nozzle_systems: list[str] | None,
    tool_feed_routes: list[str] | None,
    tool_notes: list[str] | None,
    tool_is_active: list[str] | None,
) -> None:
    ids = normalize_form_list(tool_ids)
    names = normalize_form_list(tool_names)
    max_values = normalize_form_list(tool_max_hotend_c)
    systems = normalize_form_list(tool_nozzle_systems)
    routes = normalize_form_list(tool_feed_routes)
    notes = normalize_form_list(tool_notes)
    active_values = normalize_form_list(tool_is_active)
    existing = {tool.id: tool for tool in printer.tools}
    submitted_ids: set[int] = set()

    for index, name in enumerate(names):
        label = clean_text(name) or f"Tool {index + 1}"
        raw_id = ids[index] if index < len(ids) else ""
        tool = None
        if raw_id:
            try:
                tool_id = int(raw_id)
            except ValueError:
                tool_id = 0
            tool = existing.get(tool_id)
            if tool:
                submitted_ids.add(tool.id)
        if tool is None:
            tool = PrinterTool()
            printer.tools.append(tool)

        max_hotend = parse_optional_float(max_values[index] if index < len(max_values) else "")
        tool.name = label
        tool.tool_order = index + 1
        tool.max_hotend_c = max(0, max_hotend if max_hotend is not None else (printer.nozzle_max_c or 0))
        tool.nozzle_system = clean_text(systems[index] if index < len(systems) else "")
        tool.supported_feed_routes = clean_text(routes[index] if index < len(routes) else "")
        tool.notes = clean_text(notes[index] if index < len(notes) else "")
        tool.is_active = (active_values[index] if index < len(active_values) else "active") == "active"

    if not names:
        printer.tools.append(
            PrinterTool(
                printer=printer,
                name="Main print tool",
                tool_order=1,
                max_hotend_c=printer.nozzle_max_c or 300,
                supported_feed_routes="standard filament path",
            )
        )

    for tool in printer.tools:
        if tool.id and tool.id not in submitted_ids and names:
            tool.is_active = False


def update_nozzle_install_state(printer: PrinterPreset, installed_nozzle: PrinterNozzle | None) -> None:
    if installed_nozzle and installed_nozzle.is_active and installed_nozzle.installed:
        installed_nozzle.inventory_status = "installed"
        for nozzle in printer.nozzles:
            same_scope = (
                nozzle.tool_id == installed_nozzle.tool_id
                if installed_nozzle.tool_id is not None
                else nozzle.tool_id is None
            )
            if nozzle.id != installed_nozzle.id and same_scope:
                nozzle.installed = False
                if nozzle.inventory_status == "installed":
                    nozzle.inventory_status = "spare"
    elif installed_nozzle and not installed_nozzle.is_active:
        installed_nozzle.installed = False
        if installed_nozzle.inventory_status == "installed":
            installed_nozzle.inventory_status = "spare"


def tri_state_bool(value: str | None) -> bool | None:
    normalized = clean_text(value).lower()
    if normalized in {"yes", "true", "1", "on"}:
        return True
    if normalized in {"no", "false", "0", "off"}:
        return False
    return None


def nozzle_catalog_items(session: Session) -> list[NozzleCatalogItem]:
    return list(
        session.scalars(
            select(NozzleCatalogItem)
            .where(NozzleCatalogItem.is_active.is_(True))
            .order_by(NozzleCatalogItem.is_user_created, NozzleCatalogItem.manufacturer, NozzleCatalogItem.display_name)
        )
    )


def nozzle_catalog_payload(item: NozzleCatalogItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "display_name": item.display_name,
        "manufacturer": item.manufacturer,
        "model": item.model,
        "diameter_mm": item.diameter_mm,
        "nozzle_material": item.nozzle_material,
        "nozzle_system": item.nozzle_system,
        "max_temp_c": item.max_temp_c,
        "abrasive_ready": item.abrasive_ready,
        "carbon_fibre_suitable": item.carbon_fibre_suitable,
        "glass_fibre_suitable": item.glass_fibre_suitable,
        "high_flow": item.high_flow,
        "recommended_usage": item.recommended_usage,
        "source_reference": item.source_reference,
        "is_user_created": item.is_user_created,
    }


def apply_catalog_defaults(nozzle: PrinterNozzle, catalog: NozzleCatalogItem | None) -> None:
    if catalog is None:
        return
    nozzle.catalog_item = catalog
    if not nozzle.label:
        nozzle.label = catalog.display_name
    if not nozzle.manufacturer:
        nozzle.manufacturer = catalog.manufacturer
    if not nozzle.part_number:
        nozzle.part_number = catalog.model
    if not nozzle.nozzle_material:
        nozzle.nozzle_material = catalog.nozzle_material
    if not nozzle.nozzle_system:
        nozzle.nozzle_system = catalog.nozzle_system
    if not nozzle.diameter_mm and catalog.diameter_mm:
        nozzle.diameter_mm = catalog.diameter_mm
    if nozzle.max_temp_c is None:
        nozzle.max_temp_c = catalog.max_temp_c
    if nozzle.abrasive_ready is None:
        nozzle.abrasive_ready = catalog.abrasive_ready
    if nozzle.carbon_fibre_suitable is None:
        nozzle.carbon_fibre_suitable = catalog.carbon_fibre_suitable
    if nozzle.glass_fibre_suitable is None:
        nozzle.glass_fibre_suitable = catalog.glass_fibre_suitable
    if nozzle.high_flow is None:
        nozzle.high_flow = catalog.high_flow


def resolve_printer_tool(printer: PrinterPreset, tool_id: str | int | None) -> PrinterTool | None:
    tools = active_printer_tools(printer)
    if not tools:
        tool = PrinterTool(
            printer=printer,
            name="Main print tool",
            tool_order=1,
            max_hotend_c=printer.nozzle_max_c or 300,
            supported_feed_routes="standard filament path",
        )
        return tool
    try:
        wanted = int(tool_id or 0)
    except (TypeError, ValueError):
        wanted = 0
    if wanted:
        selected = next((tool for tool in tools if tool.id == wanted), None)
        if selected is None:
            raise HTTPException(status_code=400, detail="Selected print tool does not belong to this printer.")
        return selected
    return tools[0]


def resolve_catalog_item(session: Session, catalog_item_id: str | int | None) -> NozzleCatalogItem | None:
    try:
        wanted = int(catalog_item_id or 0)
    except (TypeError, ValueError):
        wanted = 0
    if not wanted:
        return None
    item = session.get(NozzleCatalogItem, wanted)
    if not item or not item.is_active:
        raise HTTPException(status_code=400, detail="Selected nozzle catalog item is not available.")
    return item


def upsert_custom_catalog_item(
    session: Session,
    create_custom_catalog: bool,
    label: str,
    manufacturer: str,
    part_number: str,
    diameter_mm: float,
    nozzle_material: str,
    nozzle_system: str,
    max_temp_c: float | None,
    abrasive_ready: bool | None,
    carbon_fibre_suitable: bool | None,
    glass_fibre_suitable: bool | None,
    high_flow: bool | None,
    notes: str,
) -> NozzleCatalogItem | None:
    if not create_custom_catalog:
        return None
    item = NozzleCatalogItem(
        display_name=clean_text(label) or "Custom nozzle",
        manufacturer=clean_text(manufacturer),
        model=clean_text(part_number),
        diameter_mm=max(0, diameter_mm) if diameter_mm else None,
        nozzle_material=clean_text(nozzle_material),
        nozzle_system=clean_text(nozzle_system),
        max_temp_c=max_temp_c,
        abrasive_ready=abrasive_ready,
        carbon_fibre_suitable=carbon_fibre_suitable,
        glass_fibre_suitable=glass_fibre_suitable,
        high_flow=high_flow,
        recommended_usage=clean_text(notes),
        source_reference="User-created custom nozzle definition.",
        is_user_created=True,
    )
    session.add(item)
    session.flush()
    return item


def apply_nozzle_form(
    session: Session,
    printer: PrinterPreset,
    nozzle: PrinterNozzle,
    *,
    tool_id: str,
    catalog_item_id: str,
    create_custom_catalog: bool,
    label: str,
    diameter_mm: float,
    nozzle_material: str,
    brand_product: str,
    manufacturer: str,
    part_number: str,
    nozzle_system: str,
    max_temp_c: str,
    abrasive_ready: str,
    carbon_fibre_suitable: str,
    glass_fibre_suitable: str,
    high_flow: str,
    inventory_status: str,
    is_active: bool,
    installed_on: str,
    hours_before_tracking: float,
    notes: str,
) -> None:
    if nozzle_material not in NOZZLE_MATERIAL_OPTIONS:
        nozzle_material = "other"
    if inventory_status not in NOZZLE_INVENTORY_STATUS_OPTIONS:
        inventory_status = "spare"

    parsed_max_temp = parse_optional_float(max_temp_c)
    abrasive_value = tri_state_bool(abrasive_ready)
    carbon_value = tri_state_bool(carbon_fibre_suitable)
    glass_value = tri_state_bool(glass_fibre_suitable)
    high_flow_value = tri_state_bool(high_flow)
    selected_tool = resolve_printer_tool(printer, tool_id)
    selected_catalog = upsert_custom_catalog_item(
        session,
        create_custom_catalog,
        label,
        manufacturer,
        part_number,
        diameter_mm,
        nozzle_material,
        nozzle_system,
        parsed_max_temp,
        abrasive_value,
        carbon_value,
        glass_value,
        high_flow_value,
        notes,
    ) or resolve_catalog_item(session, catalog_item_id)

    nozzle.printer = printer
    nozzle.tool = selected_tool
    nozzle.catalog_item = selected_catalog
    nozzle.label = clean_text(label) or clean_text(selected_catalog.display_name if selected_catalog else "") or "Nozzle"
    nozzle.diameter_mm = max(0, diameter_mm)
    nozzle.nozzle_material = nozzle_material
    nozzle.brand_product = clean_text(brand_product)
    nozzle.manufacturer = clean_text(manufacturer)
    nozzle.part_number = clean_text(part_number)
    nozzle.nozzle_system = clean_text(nozzle_system)
    nozzle.max_temp_c = parsed_max_temp
    nozzle.abrasive_ready = abrasive_value
    nozzle.carbon_fibre_suitable = carbon_value
    nozzle.glass_fibre_suitable = glass_value
    nozzle.high_flow = high_flow_value
    nozzle.inventory_status = inventory_status
    nozzle.is_active = is_active and inventory_status != "archived"
    nozzle.installed = nozzle.is_active and inventory_status == "installed"
    nozzle.installed_on = parse_optional_form_date(installed_on, "Install date")
    nozzle.hours_before_tracking = max(0, hours_before_tracking)
    nozzle.notes = clean_text(notes)
    apply_catalog_defaults(nozzle, selected_catalog)
    update_nozzle_install_state(printer, nozzle)


@app.get("/printers")
def printers_page(request: Request, session: Session = Depends(get_session)):
    printers = all_printers(session)
    active = [printer_payload(printer) for printer in printers if printer.is_active]
    archived = [printer_payload(printer) for printer in printers if not printer.is_active]
    return page(
        request,
        "printers.html",
        page_name="printers",
        printers=active,
        archived_printers=archived,
    )


@app.get("/printers/new")
def new_printer_form(request: Request):
    return page(
        request,
        "printer_form.html",
        page_name="printers",
        mode="create",
        printer=blank_printer_payload(),
    )


@app.post("/printers/new")
def create_printer(
    name: str = Form(...),
    description: str = Form(""),
    printer_type: str = Form("FDM / FFF"),
    nozzle_max_c: float = Form(300),
    bed_max_c: float = Form(100),
    chamber_max_c: float = Form(0),
    enclosed: bool = Form(False),
    heated_chamber: bool = Form(False),
    direct_drive: bool = Form(True),
    supports_flexible: bool = Form(True),
    ams_capable: bool = Form(False),
    build_volume: str = Form(""),
    purchase_date: str = Form(""),
    serial_number: str = Form(""),
    hours_before_tracking: float = Form(0),
    notes: str = Form(""),
    is_active: bool = Form(True),
    tool_ids: list[str] = Form(default=[]),
    tool_names: list[str] = Form(default=[]),
    tool_max_hotend_c: list[str] = Form(default=[]),
    tool_nozzle_systems: list[str] = Form(default=[]),
    tool_feed_routes: list[str] = Form(default=[]),
    tool_notes: list[str] = Form(default=[]),
    tool_is_active: list[str] = Form(default=[]),
    session: Session = Depends(get_session),
):
    printer = PrinterPreset(
        slug=unique_printer_slug(session, name),
        name=clean_text(name),
        description=clean_text(description),
        printer_type=clean_text(printer_type) or "FDM / FFF",
        nozzle_max_c=max(0, nozzle_max_c),
        bed_max_c=max(0, bed_max_c),
        chamber_max_c=max(0, chamber_max_c),
        enclosed=enclosed,
        heated_chamber=heated_chamber,
        direct_drive=direct_drive,
        supports_flexible=supports_flexible,
        ams_capable=ams_capable,
        build_volume=clean_text(build_volume),
        purchase_date=parse_optional_form_date(purchase_date, "Purchase date"),
        serial_number=clean_text(serial_number),
        hours_before_tracking=max(0, hours_before_tracking),
        notes=clean_text(notes),
        is_active=is_active,
    )
    session.add(printer)
    session.flush()
    sync_printer_tools(
        printer,
        tool_ids,
        tool_names,
        tool_max_hotend_c,
        tool_nozzle_systems,
        tool_feed_routes,
        tool_notes,
        tool_is_active,
    )
    session.commit()
    return RedirectResponse(f"/printers/{printer.id}", status_code=303)


@app.get("/printers/{printer_id}")
def printer_detail(printer_id: int, request: Request, session: Session = Depends(get_session)):
    printer = printer_or_404(session, printer_id)
    profiles = sorted(printer.print_profiles, key=lambda item: (item.printed_on, item.id), reverse=True)
    payload = printer_payload(printer)
    payload["can_delete"] = printer_can_delete(printer)
    return page(
        request,
        "printer_detail.html",
        page_name="printers",
        printer=payload,
        profiles=[profile_payload(profile) for profile in profiles[:12]],
    )


@app.get("/printers/{printer_id}/edit")
def edit_printer_form(printer_id: int, request: Request, session: Session = Depends(get_session)):
    printer = printer_or_404(session, printer_id)
    return page(
        request,
        "printer_form.html",
        page_name="printers",
        mode="edit",
        printer=printer_payload(printer),
    )


@app.post("/printers/{printer_id}/edit")
def update_printer(
    printer_id: int,
    name: str = Form(...),
    description: str = Form(""),
    printer_type: str = Form("FDM / FFF"),
    nozzle_max_c: float = Form(300),
    bed_max_c: float = Form(100),
    chamber_max_c: float = Form(0),
    enclosed: bool = Form(False),
    heated_chamber: bool = Form(False),
    direct_drive: bool = Form(True),
    supports_flexible: bool = Form(True),
    ams_capable: bool = Form(False),
    build_volume: str = Form(""),
    purchase_date: str = Form(""),
    serial_number: str = Form(""),
    hours_before_tracking: float = Form(0),
    notes: str = Form(""),
    is_active: bool = Form(False),
    tool_ids: list[str] = Form(default=[]),
    tool_names: list[str] = Form(default=[]),
    tool_max_hotend_c: list[str] = Form(default=[]),
    tool_nozzle_systems: list[str] = Form(default=[]),
    tool_feed_routes: list[str] = Form(default=[]),
    tool_notes: list[str] = Form(default=[]),
    tool_is_active: list[str] = Form(default=[]),
    session: Session = Depends(get_session),
):
    printer = printer_or_404(session, printer_id)
    printer.name = clean_text(name)
    printer.slug = unique_printer_slug(session, printer.name, current_printer_id=printer.id)
    printer.description = clean_text(description)
    printer.printer_type = clean_text(printer_type) or "FDM / FFF"
    printer.nozzle_max_c = max(0, nozzle_max_c)
    printer.bed_max_c = max(0, bed_max_c)
    printer.chamber_max_c = max(0, chamber_max_c)
    printer.enclosed = enclosed
    printer.heated_chamber = heated_chamber
    printer.direct_drive = direct_drive
    printer.supports_flexible = supports_flexible
    printer.ams_capable = ams_capable
    printer.build_volume = clean_text(build_volume)
    printer.purchase_date = parse_optional_form_date(purchase_date, "Purchase date")
    printer.serial_number = clean_text(serial_number)
    printer.hours_before_tracking = max(0, hours_before_tracking)
    printer.notes = clean_text(notes)
    printer.is_active = is_active
    sync_printer_tools(
        printer,
        tool_ids,
        tool_names,
        tool_max_hotend_c,
        tool_nozzle_systems,
        tool_feed_routes,
        tool_notes,
        tool_is_active,
    )
    session.commit()
    return RedirectResponse(f"/printers/{printer.id}", status_code=303)


@app.post("/printers/{printer_id}/archive")
def archive_printer(printer_id: int, return_to: str = Form(""), session: Session = Depends(get_session)):
    printer = printer_or_404(session, printer_id)
    printer.is_active = False
    session.commit()
    return RedirectResponse(return_to or f"/printers/{printer.id}", status_code=303)


@app.post("/printers/{printer_id}/restore")
def restore_printer(printer_id: int, return_to: str = Form(""), session: Session = Depends(get_session)):
    printer = printer_or_404(session, printer_id)
    printer.is_active = True
    session.commit()
    return RedirectResponse(return_to or f"/printers/{printer.id}", status_code=303)


@app.post("/printers/{printer_id}/delete")
def delete_printer(printer_id: int, session: Session = Depends(get_session)):
    printer = printer_or_404(session, printer_id)
    if not printer_can_delete(printer):
        printer.is_active = False
        session.commit()
        return RedirectResponse(f"/printers/{printer.id}", status_code=303)
    session.delete(printer)
    session.commit()
    return RedirectResponse("/printers", status_code=303)


@app.get("/printers/{printer_id}/nozzles/new")
def new_nozzle_form(printer_id: int, request: Request, session: Session = Depends(get_session)):
    printer = printer_or_404(session, printer_id)
    return page(
        request,
        "nozzle_form.html",
        page_name="printers",
        mode="create",
        printer=printer_payload(printer),
        nozzle=blank_nozzle_payload(printer.id),
        tools=[tool_payload(tool) for tool in active_printer_tools(printer)],
        nozzle_catalog=[nozzle_catalog_payload(item) for item in nozzle_catalog_items(session)],
        nozzle_material_options=NOZZLE_MATERIAL_OPTIONS,
        nozzle_status_options=NOZZLE_INVENTORY_STATUS_OPTIONS,
    )


@app.post("/printers/{printer_id}/nozzles/new")
def create_nozzle(
    printer_id: int,
    tool_id: str = Form(""),
    catalog_item_id: str = Form(""),
    create_custom_catalog: bool = Form(False),
    label: str = Form(...),
    diameter_mm: float = Form(0.4),
    nozzle_material: str = Form("brass"),
    brand_product: str = Form(""),
    manufacturer: str = Form(""),
    part_number: str = Form(""),
    nozzle_system: str = Form(""),
    max_temp_c: str = Form(""),
    abrasive_ready: str = Form("unknown"),
    carbon_fibre_suitable: str = Form("unknown"),
    glass_fibre_suitable: str = Form("unknown"),
    high_flow: str = Form("unknown"),
    inventory_status: str = Form("spare"),
    is_active: bool = Form(True),
    installed_on: str = Form(""),
    hours_before_tracking: float = Form(0),
    notes: str = Form(""),
    session: Session = Depends(get_session),
):
    printer = printer_or_404(session, printer_id)
    nozzle = PrinterNozzle(printer=printer, label=clean_text(label), diameter_mm=max(0, diameter_mm))
    session.add(nozzle)
    session.flush()
    apply_nozzle_form(
        session,
        printer,
        nozzle,
        tool_id=tool_id,
        catalog_item_id=catalog_item_id,
        create_custom_catalog=create_custom_catalog,
        label=label,
        diameter_mm=diameter_mm,
        nozzle_material=nozzle_material,
        brand_product=brand_product,
        manufacturer=manufacturer,
        part_number=part_number,
        nozzle_system=nozzle_system,
        max_temp_c=max_temp_c,
        abrasive_ready=abrasive_ready,
        carbon_fibre_suitable=carbon_fibre_suitable,
        glass_fibre_suitable=glass_fibre_suitable,
        high_flow=high_flow,
        inventory_status=inventory_status,
        is_active=is_active,
        installed_on=installed_on,
        hours_before_tracking=hours_before_tracking,
        notes=notes,
    )
    session.commit()
    return RedirectResponse(f"/printers/{printer.id}#nozzles", status_code=303)


@app.get("/printers/{printer_id}/nozzles/{nozzle_id}/edit")
def edit_nozzle_form(printer_id: int, nozzle_id: int, request: Request, session: Session = Depends(get_session)):
    printer = printer_or_404(session, printer_id)
    nozzle = nozzle_or_404(session, printer_id, nozzle_id)
    return page(
        request,
        "nozzle_form.html",
        page_name="printers",
        mode="edit",
        printer=printer_payload(printer),
        nozzle=nozzle_payload(nozzle),
        tools=[tool_payload(tool) for tool in active_printer_tools(printer)],
        nozzle_catalog=[nozzle_catalog_payload(item) for item in nozzle_catalog_items(session)],
        nozzle_material_options=NOZZLE_MATERIAL_OPTIONS,
        nozzle_status_options=NOZZLE_INVENTORY_STATUS_OPTIONS,
    )


@app.post("/printers/{printer_id}/nozzles/{nozzle_id}/edit")
def update_nozzle(
    printer_id: int,
    nozzle_id: int,
    tool_id: str = Form(""),
    catalog_item_id: str = Form(""),
    create_custom_catalog: bool = Form(False),
    label: str = Form(...),
    diameter_mm: float = Form(0.4),
    nozzle_material: str = Form("brass"),
    brand_product: str = Form(""),
    manufacturer: str = Form(""),
    part_number: str = Form(""),
    nozzle_system: str = Form(""),
    max_temp_c: str = Form(""),
    abrasive_ready: str = Form("unknown"),
    carbon_fibre_suitable: str = Form("unknown"),
    glass_fibre_suitable: str = Form("unknown"),
    high_flow: str = Form("unknown"),
    inventory_status: str = Form("spare"),
    is_active: bool = Form(False),
    installed_on: str = Form(""),
    hours_before_tracking: float = Form(0),
    notes: str = Form(""),
    session: Session = Depends(get_session),
):
    printer = printer_or_404(session, printer_id)
    nozzle = nozzle_or_404(session, printer_id, nozzle_id)
    apply_nozzle_form(
        session,
        printer,
        nozzle,
        tool_id=tool_id,
        catalog_item_id=catalog_item_id,
        create_custom_catalog=create_custom_catalog,
        label=label,
        diameter_mm=diameter_mm,
        nozzle_material=nozzle_material,
        brand_product=brand_product,
        manufacturer=manufacturer,
        part_number=part_number,
        nozzle_system=nozzle_system,
        max_temp_c=max_temp_c,
        abrasive_ready=abrasive_ready,
        carbon_fibre_suitable=carbon_fibre_suitable,
        glass_fibre_suitable=glass_fibre_suitable,
        high_flow=high_flow,
        inventory_status=inventory_status,
        is_active=is_active,
        installed_on=installed_on,
        hours_before_tracking=hours_before_tracking,
        notes=notes,
    )
    session.commit()
    return RedirectResponse(f"/printers/{printer.id}#nozzles", status_code=303)


@app.post("/printers/{printer_id}/nozzles/{nozzle_id}/retire")
def retire_nozzle(printer_id: int, nozzle_id: int, session: Session = Depends(get_session)):
    nozzle = nozzle_or_404(session, printer_id, nozzle_id)
    nozzle.is_active = False
    nozzle.installed = False
    nozzle.inventory_status = "removed"
    session.commit()
    return RedirectResponse(f"/printers/{printer_id}#nozzles", status_code=303)


@app.post("/printers/{printer_id}/nozzles/{nozzle_id}/delete")
def delete_nozzle(printer_id: int, nozzle_id: int, session: Session = Depends(get_session)):
    nozzle = nozzle_or_404(session, printer_id, nozzle_id)
    if nozzle.print_profiles:
        nozzle.is_active = False
        nozzle.installed = False
        nozzle.inventory_status = "archived"
    else:
        session.delete(nozzle)
    session.commit()
    return RedirectResponse(f"/printers/{printer_id}#nozzles", status_code=303)


@app.get("/printers/{printer_id}/maintenance/new")
def new_maintenance_form(printer_id: int, request: Request, session: Session = Depends(get_session)):
    printer = printer_or_404(session, printer_id)
    return page(
        request,
        "maintenance_form.html",
        page_name="printers",
        mode="create",
        printer=printer_payload(printer),
        entry=blank_maintenance_payload(printer.id),
        maintenance_type_options=MAINTENANCE_TYPE_OPTIONS,
    )


@app.post("/printers/{printer_id}/maintenance/new")
def create_maintenance(
    printer_id: int,
    maintenance_date: str = Form(""),
    maintenance_type: str = Form("service"),
    component: str = Form(""),
    notes: str = Form(""),
    cost_eur: str = Form(""),
    printer_hours: str = Form(""),
    session: Session = Depends(get_session),
):
    printer = printer_or_404(session, printer_id)
    if maintenance_type not in MAINTENANCE_TYPE_OPTIONS:
        maintenance_type = "other"
    session.add(
        PrinterMaintenance(
            printer_id=printer.id,
            maintenance_date=parse_form_date(maintenance_date, "Maintenance date"),
            maintenance_type=maintenance_type,
            component=clean_text(component),
            notes=clean_text(notes),
            cost_eur=parse_optional_nonnegative_float(cost_eur),
            printer_hours=parse_optional_nonnegative_float(printer_hours),
        )
    )
    session.commit()
    return RedirectResponse(f"/printers/{printer.id}#maintenance", status_code=303)


@app.get("/printers/{printer_id}/maintenance/{entry_id}/edit")
def edit_maintenance_form(printer_id: int, entry_id: int, request: Request, session: Session = Depends(get_session)):
    printer = printer_or_404(session, printer_id)
    entry = maintenance_or_404(session, printer_id, entry_id)
    return page(
        request,
        "maintenance_form.html",
        page_name="printers",
        mode="edit",
        printer=printer_payload(printer),
        entry=maintenance_payload(entry),
        maintenance_type_options=MAINTENANCE_TYPE_OPTIONS,
    )


@app.post("/printers/{printer_id}/maintenance/{entry_id}/edit")
def update_maintenance(
    printer_id: int,
    entry_id: int,
    maintenance_date: str = Form(""),
    maintenance_type: str = Form("service"),
    component: str = Form(""),
    notes: str = Form(""),
    cost_eur: str = Form(""),
    printer_hours: str = Form(""),
    session: Session = Depends(get_session),
):
    entry = maintenance_or_404(session, printer_id, entry_id)
    if maintenance_type not in MAINTENANCE_TYPE_OPTIONS:
        maintenance_type = "other"
    entry.maintenance_date = parse_form_date(maintenance_date, "Maintenance date")
    entry.maintenance_type = maintenance_type
    entry.component = clean_text(component)
    entry.notes = clean_text(notes)
    entry.cost_eur = parse_optional_nonnegative_float(cost_eur)
    entry.printer_hours = parse_optional_nonnegative_float(printer_hours)
    session.commit()
    return RedirectResponse(f"/printers/{printer_id}#maintenance", status_code=303)


@app.post("/printers/{printer_id}/maintenance/{entry_id}/delete")
def delete_maintenance(printer_id: int, entry_id: int, session: Session = Depends(get_session)):
    entry = maintenance_or_404(session, printer_id, entry_id)
    session.delete(entry)
    session.commit()
    return RedirectResponse(f"/printers/{printer_id}#maintenance", status_code=303)


@app.get("/api/printers/{printer_id}/nozzles")
def api_printer_nozzles(printer_id: int, session: Session = Depends(get_session)):
    printer = printer_or_404(session, printer_id)
    return JSONResponse([nozzle_payload(nozzle) for nozzle in printer.nozzles if nozzle.is_active])


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
            selectinload(Material.print_profiles).selectinload(PrintProfile.printer_nozzle),
            selectinload(Material.print_profiles).selectinload(PrintProfile.attachments),
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
            nozzles=[nozzle_option_payload(nozzle) for nozzle in nozzle_select_options(session)],
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
        nozzles=[nozzle_option_payload(nozzle) for nozzle in nozzle_select_options(session)],
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
    first_price_observed_on: str = Form(""),
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
        session.add(PriceEntry(
            product_id=product.id,
            price_eur=first_price_eur,
            observed_on=parse_form_date(first_price_observed_on, "Initial price date"),
            source_label="Initial manual price",
        ))
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


def price_or_404(session: Session, price_id: int) -> PriceEntry:
    entry = session.scalar(
        select(PriceEntry)
        .options(selectinload(PriceEntry.product).selectinload(FilamentProduct.material))
        .options(selectinload(PriceEntry.product).selectinload(FilamentProduct.price_entries))
        .options(selectinload(PriceEntry.product).selectinload(FilamentProduct.print_profiles))
        .where(PriceEntry.id == price_id)
    )
    if not entry:
        raise HTTPException(status_code=404, detail="Price entry not found")
    return entry


@app.get("/prices/{price_id}/edit")
def edit_price_form(price_id: int, request: Request, session: Session = Depends(get_session)):
    entry = price_or_404(session, price_id)
    return page(
        request,
        "price_form.html",
        page_name="inventory",
        entry=entry,
        product=spool_page_payload(entry.product),
    )


@app.post("/prices/{price_id}/edit")
def update_price(
    price_id: int,
    price_eur: float = Form(...),
    observed_on: str = Form(""),
    source_label: str = Form("Manual entry"),
    stock_note: str = Form(""),
    session: Session = Depends(get_session),
):
    entry = price_or_404(session, price_id)
    if price_eur < 0:
        raise HTTPException(status_code=400, detail="Price cannot be negative.")
    entry.price_eur = price_eur
    entry.observed_on = parse_form_date(observed_on, "Price date")
    entry.source_label = source_label.strip()
    entry.stock_note = stock_note.strip()
    return_to = spool_path(entry.product)
    session.commit()
    return RedirectResponse(return_to, status_code=303)


@app.post("/prices/{price_id}/delete")
def delete_price(price_id: int, session: Session = Depends(get_session)):
    entry = price_or_404(session, price_id)
    return_to = spool_path(entry.product)
    session.delete(entry)
    session.commit()
    return RedirectResponse(return_to, status_code=303)


def product_select_options(session: Session, current_product_id: int | None = None) -> list[dict[str, Any]]:
    products = list(
        session.scalars(
            select(FilamentProduct)
            .options(selectinload(FilamentProduct.material))
            .where(FilamentProduct.is_active.is_(True))
            .order_by(FilamentProduct.brand, FilamentProduct.product_name, FilamentProduct.id)
        )
    )
    if current_product_id and all(product.id != current_product_id for product in products):
        current = session.scalar(
            select(FilamentProduct)
            .options(selectinload(FilamentProduct.material))
            .where(FilamentProduct.id == current_product_id)
        )
        if current:
            products.append(current)
    return [
        {
            "id": product.id,
            "material_id": product.material_id,
            "label": f"{display_spool_code(product)} - {product.material.name} - {product.brand} {product.product_name}",
        }
        for product in products
    ]


def printer_select_options(session: Session, current_printer_id: int | None = None) -> list[PrinterPreset]:
    printers = active_printers(session)
    if current_printer_id and all(printer.id != current_printer_id for printer in printers):
        current = session.scalar(
            select(PrinterPreset)
            .options(
                selectinload(PrinterPreset.nozzles).selectinload(PrinterNozzle.print_profiles),
                selectinload(PrinterPreset.nozzles).selectinload(PrinterNozzle.catalog_item),
                selectinload(PrinterPreset.tools),
                selectinload(PrinterPreset.print_profiles),
                selectinload(PrinterPreset.maintenance_entries),
            )
            .where(PrinterPreset.id == current_printer_id)
        )
        if current:
            printers.append(current)
    return printers


def nozzle_select_options(session: Session, current_nozzle_id: int | None = None) -> list[PrinterNozzle]:
    nozzles = list(
        session.scalars(
            select(PrinterNozzle)
            .options(
                selectinload(PrinterNozzle.printer),
                selectinload(PrinterNozzle.tool),
                selectinload(PrinterNozzle.catalog_item),
                selectinload(PrinterNozzle.print_profiles),
            )
            .where(PrinterNozzle.is_active.is_(True))
            .order_by(PrinterNozzle.printer_id, PrinterNozzle.installed.desc(), PrinterNozzle.label)
        )
    )
    if current_nozzle_id and all(nozzle.id != current_nozzle_id for nozzle in nozzles):
        current = session.scalar(
            select(PrinterNozzle)
            .options(
                selectinload(PrinterNozzle.printer),
                selectinload(PrinterNozzle.tool),
                selectinload(PrinterNozzle.catalog_item),
                selectinload(PrinterNozzle.print_profiles),
            )
            .where(PrinterNozzle.id == current_nozzle_id)
        )
        if current:
            nozzles.append(current)
    return nozzles


def nozzle_option_payload(nozzle: PrinterNozzle) -> dict[str, Any]:
    tool_name = nozzle.tool.name if nozzle.tool else ""
    label_parts = [
        nozzle.printer.name if nozzle.printer else "Printer",
        tool_name,
        nozzle.label,
    ]
    return {
        **nozzle_payload(nozzle),
        "printer_name": nozzle.printer.name if nozzle.printer else "",
        "tool_name": tool_name,
        "label_with_printer": " - ".join(part for part in label_parts if part),
    }


def blank_profile_payload(material_id: int | None = None) -> dict[str, Any]:
    return {
        "id": None,
        "material_id": material_id,
        "product_id": None,
        "printer_id": None,
        "printer_nozzle_id": None,
        "profile_name": "",
        "state": "Dry",
        "nozzle_diameter": 0.4,
        "nozzle_temp": 0,
        "bed_temp": 0,
        "chamber_temp": 0,
        "speed_mm_s": 0,
        "dryer_temp": 0,
        "dryer_hours": 0,
        "build_plate": "",
        "filament_used_g": 0,
        "print_duration_hours": None,
        "result_rating": 3,
        "notes": "",
        "printed_on": date.today().isoformat(),
        "attachments": [],
    }


def resolve_profile_links(
    session: Session,
    material_id: int,
    product_id: str,
    printer_id: str,
    printer_nozzle_id: str,
    current_nozzle_id: int | None = None,
) -> tuple[int, int | None, int | None, int | None]:
    material_pk = material_id
    product_pk = int(product_id) if clean_text(product_id) else None
    printer_pk = int(printer_id) if clean_text(printer_id) else None
    nozzle_pk = int(printer_nozzle_id) if clean_text(printer_nozzle_id) else None

    if product_pk is not None:
        product = session.get(FilamentProduct, product_pk)
        if not product or not product.is_active:
            raise HTTPException(status_code=404, detail="Spool not found")
        material_pk = product.material_id
    else:
        material = session.scalar(select(Material).where(Material.id == material_pk, Material.is_active.is_(True)))
        if not material:
            raise HTTPException(status_code=404, detail="Material not found")

    if printer_pk is not None:
        printer = session.get(PrinterPreset, printer_pk)
        if not printer or not printer.is_active:
            raise HTTPException(status_code=404, detail="Printer not found")

    if nozzle_pk is not None:
        nozzle = session.get(PrinterNozzle, nozzle_pk)
        if not nozzle:
            raise HTTPException(status_code=404, detail="Nozzle not found")
        if not nozzle.is_active and nozzle.id != current_nozzle_id:
            raise HTTPException(status_code=400, detail="Retired nozzles cannot be selected for new print records.")
        if printer_pk is not None and nozzle.printer_id != printer_pk:
            raise HTTPException(status_code=400, detail="Selected nozzle does not belong to the selected printer.")
        printer_pk = nozzle.printer_id

    return material_pk, product_pk, printer_pk, nozzle_pk


def add_profile_attachments(session: Session, profile: PrintProfile, attachments: list[UploadFile]) -> None:
    for upload in attachments or []:
        attachment = store_profile_attachment(upload, profile.id)
        if attachment:
            session.add(attachment)


@app.get("/profiles/new")
def new_profile_form(request: Request, material_id: int | None = None, session: Session = Depends(get_session)):
    materials = list(
        session.scalars(
            select(Material)
            .where(Material.is_active.is_(True))
            .order_by(Material.family, Material.name)
        )
    )
    return page(
        request,
        "profile_form.html",
        page_name="inventory",
        mode="create",
        profile=blank_profile_payload(material_id),
        materials=materials,
        products=product_select_options(session),
        printers=printer_select_options(session),
        nozzles=[nozzle_option_payload(nozzle) for nozzle in nozzle_select_options(session)],
    )


@app.post("/profiles/new")
def create_profile(
    material_id: int = Form(...),
    profile_name: str = Form(...),
    product_id: str = Form(""),
    printer_id: str = Form(""),
    printer_nozzle_id: str = Form(""),
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
    print_duration_hours: str = Form(""),
    result_rating: int = Form(3),
    notes: str = Form(""),
    printed_on: str = Form(""),
    attachments: list[UploadFile] = File(default=[]),
    session: Session = Depends(get_session),
):
    material_pk, product_pk, printer_pk, nozzle_pk = resolve_profile_links(
        session, material_id, product_id, printer_id, printer_nozzle_id
    )
    profile = PrintProfile(
        material_id=material_pk,
        product_id=product_pk,
        printer_id=printer_pk,
        printer_nozzle_id=nozzle_pk,
        profile_name=profile_name.strip(),
        state=state,
        nozzle_diameter=nozzle_diameter,
        nozzle_temp=nozzle_temp,
        bed_temp=bed_temp,
        chamber_temp=chamber_temp,
        speed_mm_s=speed_mm_s,
        dryer_temp=dryer_temp,
        dryer_hours=dryer_hours,
        build_plate=build_plate.strip(),
        filament_used_g=max(0, filament_used_g),
        print_duration_hours=parse_optional_nonnegative_float(print_duration_hours),
        result_rating=max(1, min(5, result_rating)),
        notes=notes.strip(),
        printed_on=parse_form_date(printed_on, "Print date"),
    )
    session.add(profile)
    session.flush()
    add_profile_attachments(session, profile, attachments)
    session.commit()
    material = session.get(Material, profile.material_id)
    return RedirectResponse(f"/materials/{material.slug}#profiles" if material else "/inventory#profiles", status_code=303)


@app.post("/materials/{slug}/profiles")
def add_profile(
    slug: str,
    profile_name: str = Form(...),
    product_id: str = Form(""),
    printer_id: str = Form(""),
    printer_nozzle_id: str = Form(""),
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
    print_duration_hours: str = Form(""),
    result_rating: int = Form(3),
    notes: str = Form(""),
    printed_on: str = Form(""),
    attachments: list[UploadFile] = File(default=[]),
    session: Session = Depends(get_session),
):
    material = session.scalar(select(Material).where(Material.slug == slug))
    if not material:
        raise HTTPException(status_code=404, detail="Material not found")
    material_pk, product_pk, printer_pk, nozzle_pk = resolve_profile_links(
        session, material.id, product_id, printer_id, printer_nozzle_id
    )
    if material_pk != material.id:
        raise HTTPException(status_code=400, detail="Selected spool belongs to a different material.")
    profile = PrintProfile(
        material_id=material.id, product_id=product_pk, printer_id=printer_pk, printer_nozzle_id=nozzle_pk,
        profile_name=profile_name.strip(), state=state,
        nozzle_diameter=nozzle_diameter, nozzle_temp=nozzle_temp, bed_temp=bed_temp, chamber_temp=chamber_temp,
        speed_mm_s=speed_mm_s, dryer_temp=dryer_temp, dryer_hours=dryer_hours, build_plate=build_plate.strip(),
        filament_used_g=max(0, filament_used_g), print_duration_hours=parse_optional_nonnegative_float(print_duration_hours),
        result_rating=max(1, min(5, result_rating)),
        notes=notes.strip(), printed_on=parse_form_date(printed_on, "Print date"),
    )
    session.add(profile)
    session.flush()
    add_profile_attachments(session, profile, attachments)
    session.commit()
    return RedirectResponse(f"/materials/{slug}#profiles", status_code=303)


@app.get("/profiles/{profile_id}/edit")
def edit_profile_form(profile_id: int, request: Request, session: Session = Depends(get_session)):
    profile = session.scalar(
        select(PrintProfile)
        .options(
            selectinload(PrintProfile.material),
            selectinload(PrintProfile.product),
            selectinload(PrintProfile.printer),
            selectinload(PrintProfile.printer_nozzle),
            selectinload(PrintProfile.attachments),
        )
        .where(PrintProfile.id == profile_id)
    )
    if not profile:
        raise HTTPException(status_code=404, detail="Print result not found")
    materials = list(
        session.scalars(
            select(Material)
            .where(Material.is_active.is_(True))
            .order_by(Material.family, Material.name)
        )
    )
    return page(
        request,
        "profile_form.html",
        page_name="inventory",
        mode="edit",
        profile=profile_payload(profile),
        profile_material_slug=profile.material.slug if profile.material else "",
        materials=materials,
        products=product_select_options(session, profile.product_id),
        printers=printer_select_options(session, profile.printer_id),
        nozzles=[nozzle_option_payload(nozzle) for nozzle in nozzle_select_options(session, profile.printer_nozzle_id)],
    )


@app.post("/profiles/{profile_id}/edit")
def update_profile(
    profile_id: int,
    material_id: int = Form(...),
    profile_name: str = Form(...),
    product_id: str = Form(""),
    printer_id: str = Form(""),
    printer_nozzle_id: str = Form(""),
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
    print_duration_hours: str = Form(""),
    result_rating: int = Form(3),
    notes: str = Form(""),
    printed_on: str = Form(""),
    attachments: list[UploadFile] = File(default=[]),
    session: Session = Depends(get_session),
):
    profile = session.get(PrintProfile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Print result not found")
    material_pk, product_pk, printer_pk, nozzle_pk = resolve_profile_links(
        session,
        material_id,
        product_id,
        printer_id,
        printer_nozzle_id,
        current_nozzle_id=profile.printer_nozzle_id,
    )

    profile.material_id = material_pk
    profile.product_id = product_pk
    profile.printer_id = printer_pk
    profile.printer_nozzle_id = nozzle_pk
    profile.profile_name = profile_name.strip()
    profile.state = state
    profile.nozzle_diameter = nozzle_diameter
    profile.nozzle_temp = nozzle_temp
    profile.bed_temp = bed_temp
    profile.chamber_temp = chamber_temp
    profile.speed_mm_s = speed_mm_s
    profile.dryer_temp = dryer_temp
    profile.dryer_hours = dryer_hours
    profile.build_plate = build_plate.strip()
    profile.filament_used_g = max(0, filament_used_g)
    profile.print_duration_hours = parse_optional_nonnegative_float(print_duration_hours)
    profile.result_rating = max(1, min(5, result_rating))
    profile.notes = notes.strip()
    profile.printed_on = parse_form_date(printed_on, "Print date")
    session.flush()
    add_profile_attachments(session, profile, attachments)
    session.commit()

    material = session.get(Material, profile.material_id)
    return RedirectResponse(f"/materials/{material.slug}#profiles" if material else "/inventory", status_code=303)


@app.post("/profiles/{profile_id}/delete")
def delete_profile(profile_id: int, session: Session = Depends(get_session)):
    profile = session.scalar(
        select(PrintProfile)
        .options(selectinload(PrintProfile.material), selectinload(PrintProfile.attachments))
        .where(PrintProfile.id == profile_id)
    )
    if not profile:
        raise HTTPException(status_code=404, detail="Print result not found")
    material_slug = profile.material.slug if profile.material else ""
    attachment_paths = [attachment.stored_relative_path for attachment in profile.attachments]
    session.delete(profile)
    session.commit()
    for relative_path in attachment_paths:
        delete_stored_upload(relative_path)
    return RedirectResponse(f"/materials/{material_slug}#profiles" if material_slug else "/inventory", status_code=303)


@app.get("/attachments/{attachment_id}/download")
def download_attachment(attachment_id: int, session: Session = Depends(get_session)):
    attachment = session.get(PrintAttachment, attachment_id)
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")
    target = stored_upload_path(attachment.stored_relative_path)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Attachment file is missing")
    return FileResponse(
        target,
        media_type=attachment.mime_type or "application/octet-stream",
        filename=attachment.original_filename,
    )


@app.post("/attachments/{attachment_id}/delete")
def delete_attachment(
    attachment_id: int,
    return_to: str = Form(""),
    session: Session = Depends(get_session),
):
    attachment = session.get(PrintAttachment, attachment_id)
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")
    profile_id = attachment.print_profile_id
    relative_path = attachment.stored_relative_path
    session.delete(attachment)
    session.commit()
    delete_stored_upload(relative_path)
    return RedirectResponse(return_to or f"/profiles/{profile_id}/edit", status_code=303)


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
                selectinload(PrintProfile.printer_nozzle),
                selectinload(PrintProfile.attachments),
            )
            .order_by(PrintProfile.printed_on.desc(), PrintProfile.id.desc())
        )
    )
    active_products_payload = [
        {**product_payload(p), "material_name": p.material.name, "material_slug": p.material.slug}
        for p in active_rows
    ]
    archived_products_payload = [
        {**product_payload(p), "material_name": p.material.name, "material_slug": p.material.slug}
        for p in archived_rows
    ]
    return page(
        request, "inventory.html", page_name="inventory",
        products=active_products_payload,
        archived_products=archived_products_payload,
        profiles=[{**profile_payload(p), "material_name": p.material.name, "material_slug": p.material.slug} for p in profiles],
        inventory_stats={
            "active_spools": len(active_products_payload),
            "archived_spools": len(archived_products_payload),
            "remaining_g": sum(product["remaining_g"] for product in active_products_payload),
            "used_g": sum(product["filament_used_g"] for product in active_products_payload),
            "low_stock": sum(1 for product in active_products_payload if product["remaining_percent"] <= 20),
            "print_results": len(profiles),
        },
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

    printer = PrinterPreset(
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
    session.add(printer)
    session.flush()
    printer.tools.append(
        PrinterTool(
            name="Main print tool",
            tool_order=1,
            max_hotend_c=nozzle_max_c,
            supported_feed_routes="standard filament path",
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
    model_volume_mm3: float = 0,
    support_volume_mm3: float = 0,
    purge_g: float = 0,
    waste_percent: float = 0,
    used_g: float | None = None,
    support_g: float = 0,
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
    if used_g is not None and used_g > 0:
        raw_part_g = max(0, used_g)
        raw_support_g = max(0, support_g)
        purge_mass_g = max(0, purge_g)
        before_waste_g = raw_part_g + raw_support_g + purge_mass_g
        total_g = before_waste_g * (1 + max(0, waste_percent) / 100)
    else:
        raw_part_g = max(0, model_volume_mm3) * density / 1000
        raw_support_g = max(0, support_volume_mm3) * density / 1000
        purge_mass_g = max(0, purge_g)
        before_waste_g = raw_part_g + raw_support_g + purge_mass_g
        total_g = before_waste_g * (1 + max(0, waste_percent) / 100)
    waste_mass_g = max(0, total_g - before_waste_g)
    _, price_per_kg, _ = product_price(product)
    material_cost = (total_g / 1000 * price_per_kg) if price_per_kg is not None else None
    energy_cost = max(0, energy_kwh) * max(0, electricity_eur_kwh)
    return {
        "material": product.material.name,
        "product": f"{product.brand} {product.product_name}",
        "density_g_cm3": density,
        "part_mass_g": round(raw_part_g, 2),
        "support_mass_g": round(raw_support_g, 2),
        "purge_mass_g": round(purge_mass_g, 2),
        "waste_mass_g": round(waste_mass_g, 2),
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
                selectinload(PrintProfile.printer_nozzle),
                selectinload(PrintProfile.attachments),
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
