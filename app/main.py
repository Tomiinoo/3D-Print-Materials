from __future__ import annotations

import json
import shutil
import sqlite3
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .database import Base, DB_PATH, DATA_DIR, SessionLocal, engine, get_session
from .models import FilamentProduct, Material, PriceEntry, PrintProfile
from .seed import seed_materials
from .v2_routes import router as v2_router

APP_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        seed_materials(session)
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


def parse_json(raw: str | None, fallback: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        return json.loads(raw or "{}")
    except json.JSONDecodeError:
        return fallback or {}


def product_price(product: FilamentProduct) -> tuple[float | None, float | None, date | None]:
    if not product.price_entries:
        return None, None, None
    entry = sorted(product.price_entries, key=lambda x: (x.observed_on, x.id), reverse=True)[0]
    price_per_kg = (entry.price_eur / product.spool_weight_g * 1000) if product.spool_weight_g else None
    return entry.price_eur, price_per_kg, entry.observed_on


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
        "spool_weight_g": product.spool_weight_g,
        "notes": product.notes,
        "favorite": product.favorite,
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


def material_payload(material: Material, include_products: bool = True) -> dict[str, Any]:
    props = parse_json(material.properties_json)
    setting = parse_json(material.settings_json)
    scores = props.get("scores", {})
    data: dict[str, Any] = {
        "id": material.id,
        "slug": material.slug,
        "name": material.name,
        "full_name": material.full_name,
        "family": material.family,
        "subfamily": material.subfamily,
        "family_color": material.family_color,
        "formula": material.formula,
        "repeat_unit": material.repeat_unit,
        "description": material.description,
        "best_for": material.best_for,
        "avoid_for": material.avoid_for,
        "settings": setting,
        "properties": props,
        "scores": scores,
        "source_notes": material.source_notes,
        "product_count": len(material.products),
    }
    if include_products:
        data["products"] = [product_payload(p) for p in material.products]
    return data


def profile_payload(profile: PrintProfile) -> dict[str, Any]:
    return {
        "id": profile.id,
        "profile_name": profile.profile_name,
        "state": profile.state,
        "nozzle_diameter": profile.nozzle_diameter,
        "nozzle_temp": profile.nozzle_temp,
        "bed_temp": profile.bed_temp,
        "chamber_temp": profile.chamber_temp,
        "speed_mm_s": profile.speed_mm_s,
        "dryer_temp": profile.dryer_temp,
        "dryer_hours": profile.dryer_hours,
        "build_plate": profile.build_plate,
        "result_rating": profile.result_rating,
        "notes": profile.notes,
        "printed_on": profile.printed_on.isoformat(),
        "product_name": f"{profile.product.brand} {profile.product.product_name}" if profile.product else None,
    }


def all_materials(session: Session) -> list[Material]:
    return list(
        session.scalars(
            select(Material)
            .options(selectinload(Material.products).selectinload(FilamentProduct.price_entries))
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
    material_data = [material_payload(m) for m in materials]
    stats = {
        "materials": len(materials),
        "products": sum(len(m.products) for m in materials),
        "tested_profiles": len(session.scalars(select(PrintProfile)).all()),
        "families": len({m.family for m in materials}),
    }
    return page(request, "dashboard.html", page_name="dashboard", materials=material_data, stats=stats)


@app.get("/materials")
def materials_page(request: Request, session: Session = Depends(get_session)):
    materials = [material_payload(m) for m in all_materials(session)]
    families = sorted({m["family"] for m in materials})
    return page(request, "materials.html", page_name="materials", materials=materials, families=families)


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
    return page(
        request, "material_form.html", page_name="materials", mode="create", material=None,
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
    source_notes: str = Form(""),
    session: Session = Depends(get_session),
):
    slug = slug.strip().lower().replace(" ", "-")
    if session.scalar(select(Material).where(Material.slug == slug)):
        raise HTTPException(status_code=409, detail="This material slug already exists.")
    try:
        json.loads(settings_json)
        json.loads(properties_json)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Settings / properties JSON is invalid: {exc.msg}")
    mat = Material(
        name=name.strip(), slug=slug, full_name=full_name.strip(), family=family.strip(), subfamily=subfamily.strip(),
        family_color=family_color.strip() or "#64748b", formula=formula.strip(), repeat_unit=repeat_unit.strip(),
        description=description.strip(), best_for=best_for.strip(), avoid_for=avoid_for.strip(), settings_json=settings_json,
        properties_json=properties_json, source_notes=source_notes.strip(),
    )
    session.add(mat)
    session.commit()
    return RedirectResponse(f"/materials/{mat.slug}", status_code=303)


@app.get("/materials/{slug}")
def material_detail(slug: str, request: Request, session: Session = Depends(get_session)):
    material = session.scalar(
        select(Material)
        .options(
            selectinload(Material.products).selectinload(FilamentProduct.price_entries),
            selectinload(Material.print_profiles).selectinload(PrintProfile.product),
        )
        .where(Material.slug == slug)
    )
    if not material:
        raise HTTPException(status_code=404, detail="Material not found")
    payload = material_payload(material)
    profiles = [profile_payload(p) for p in material.print_profiles]
    return page(request, "material_detail.html", page_name="materials", material=payload, profiles=profiles)


@app.post("/materials/{slug}/products")
def add_product(
    slug: str,
    brand: str = Form(...),
    product_name: str = Form(...),
    supplier: str = Form(""),
    url: str = Form(""),
    color_name: str = Form(""),
    spool_weight_g: float = Form(1000),
    first_price_eur: float | None = Form(None),
    notes: str = Form(""),
    favorite: bool = Form(False),
    session: Session = Depends(get_session),
):
    material = session.scalar(select(Material).where(Material.slug == slug))
    if not material:
        raise HTTPException(status_code=404, detail="Material not found")
    product = FilamentProduct(
        material_id=material.id, brand=brand.strip(), product_name=product_name.strip(), supplier=supplier.strip(), url=url.strip(),
        color_name=color_name.strip(), spool_weight_g=spool_weight_g, notes=notes.strip(), favorite=favorite,
    )
    session.add(product)
    session.flush()
    if first_price_eur is not None and first_price_eur > 0:
        session.add(PriceEntry(product_id=product.id, price_eur=first_price_eur, observed_on=date.today(), source_label="Initial manual price"))
    session.commit()
    return RedirectResponse(f"/materials/{slug}#products", status_code=303)


@app.post("/products/{product_id}/prices")
def add_price(
    product_id: int,
    price_eur: float = Form(...),
    observed_on: date = Form(date.today()),
    source_label: str = Form("Manual entry"),
    stock_note: str = Form(""),
    session: Session = Depends(get_session),
):
    product = session.get(FilamentProduct, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    session.add(PriceEntry(
        product_id=product_id, price_eur=price_eur, observed_on=observed_on,
        source_label=source_label.strip(), stock_note=stock_note.strip(),
    ))
    session.commit()
    return RedirectResponse(f"/materials/{product.material.slug}#products", status_code=303)


@app.post("/materials/{slug}/profiles")
def add_profile(
    slug: str,
    profile_name: str = Form(...),
    product_id: int | None = Form(None),
    state: str = Form("Dry"),
    nozzle_diameter: float = Form(0.4),
    nozzle_temp: float = Form(0),
    bed_temp: float = Form(0),
    chamber_temp: float = Form(0),
    speed_mm_s: float = Form(0),
    dryer_temp: float = Form(0),
    dryer_hours: float = Form(0),
    build_plate: str = Form(""),
    result_rating: int = Form(3),
    notes: str = Form(""),
    printed_on: date = Form(date.today()),
    session: Session = Depends(get_session),
):
    material = session.scalar(select(Material).where(Material.slug == slug))
    if not material:
        raise HTTPException(status_code=404, detail="Material not found")
    profile = PrintProfile(
        material_id=material.id, product_id=product_id, profile_name=profile_name.strip(), state=state,
        nozzle_diameter=nozzle_diameter, nozzle_temp=nozzle_temp, bed_temp=bed_temp, chamber_temp=chamber_temp,
        speed_mm_s=speed_mm_s, dryer_temp=dryer_temp, dryer_hours=dryer_hours, build_plate=build_plate.strip(),
        result_rating=max(1, min(5, result_rating)), notes=notes.strip(), printed_on=printed_on,
    )
    session.add(profile)
    session.commit()
    return RedirectResponse(f"/materials/{slug}#profiles", status_code=303)


@app.get("/guide")
def guide_page(request: Request, session: Session = Depends(get_session)):
    materials = [material_payload(m, include_products=False) for m in all_materials(session)]
    return page(request, "guide.html", page_name="guide", materials=materials)


@app.get("/compare")
def compare_page(request: Request, session: Session = Depends(get_session)):
    materials = [material_payload(m, include_products=False) for m in all_materials(session)]
    return page(request, "compare.html", page_name="compare", materials=materials, materials_json=json.dumps(materials))


@app.get("/calculator")
def calculator_page(request: Request, session: Session = Depends(get_session)):
    materials = all_materials(session)
    product_rows = []
    for material in materials:
        for product in material.products:
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
            .order_by(FilamentProduct.favorite.desc(), FilamentProduct.brand, FilamentProduct.product_name)
        )
    )
    profiles = list(
        session.scalars(
            select(PrintProfile)
            .options(selectinload(PrintProfile.material), selectinload(PrintProfile.product))
            .order_by(PrintProfile.printed_on.desc(), PrintProfile.id.desc())
        )
    )
    return page(
        request, "inventory.html", page_name="inventory",
        products=[{**product_payload(p), "material_name": p.material.name, "material_slug": p.material.slug} for p in products],
        profiles=[{**profile_payload(p), "material_name": p.material.name, "material_slug": p.material.slug} for p in profiles],
    )


@app.get("/settings")
def settings_page(request: Request, session: Session = Depends(get_session)):
    materials = all_materials(session)
    return page(
        request, "settings.html", page_name="settings", db_path=str(DB_PATH), data_dir=str(DATA_DIR),
        material_count=len(materials), product_count=sum(len(m.products) for m in materials),
    )


@app.get("/api/materials")
def api_materials(session: Session = Depends(get_session)):
    return JSONResponse([material_payload(m) for m in all_materials(session)])


@app.get("/api/materials/{slug}")
def api_material(slug: str, session: Session = Depends(get_session)):
    material = session.scalar(
        select(Material)
        .options(selectinload(Material.products).selectinload(FilamentProduct.price_entries))
        .where(Material.slug == slug)
    )
    if not material:
        raise HTTPException(status_code=404, detail="Material not found")
    return JSONResponse(material_payload(material))


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
    all_profiles = list(session.scalars(select(PrintProfile).options(selectinload(PrintProfile.product))).all())
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
