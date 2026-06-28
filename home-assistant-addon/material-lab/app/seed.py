from __future__ import annotations

import json
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import FilamentProduct, Material, PriceEntry


SOURCE_X2D = "X2D technical specifications and filament compatibility guidance (Bambu Lab)."
SOURCE_DRY = "Drying values are starting guidance; use the exact spool technical data sheet for a critical part."


def settings(nozzle, bed, chamber, drying, speed, nozzle_size="0.4 mm TC", main=True, aux=True, cooling="Material profile default"):
    return {
        "nozzle": nozzle,
        "bed": bed,
        "chamber": chamber,
        "drying": drying,
        "speed": speed,
        "recommended_nozzle": nozzle_size,
        "main_compatible": main,
        "aux_compatible": aux,
        "cooling": cooling,
    }


def properties(
    density, hdt, continuous, moisture, water, flame, chemical, uv, creep,
    dry_scores, wet_scores=None, tensile=None, modulus=None, impact=None, shrinkage=None,
):
    return {
        "density_g_cm3": density,
        "mass_g_mm3": round(density / 1000, 5),
        "hdt_c": hdt,
        "continuous_service_c": continuous,
        "moisture_sensitivity": moisture,
        "water_resistance": water,
        "flame_resistance": flame,
        "chemical_resistance": chemical,
        "uv_resistance": uv,
        "creep_resistance": creep,
        "tensile_mpa": tensile,
        "modulus_gpa": modulus,
        "impact_note": impact,
        "shrinkage_note": shrinkage,
        "scores": {"dry": dry_scores, "wet": wet_scores or dry_scores},
    }


def score(rig_xy, str_xy, rig_z, layer, impact, heat, chemical, water, moisture_tol, printable, creep, uv, price):
    return {
        "rigidity_xy": rig_xy,
        "strength_xy": str_xy,
        "rigidity_z": rig_z,
        "layer_adhesion": layer,
        "impact_resistance": impact,
        "heat_resistance": heat,
        "chemical_resistance": chemical,
        "water_resistance": water,
        "moisture_tolerance": moisture_tol,
        "printability": printable,
        "creep_resistance": creep,
        "uv_resistance": uv,
        "price_range": price,
    }


def seed_materials(session: Session) -> None:
    if session.scalar(select(Material.id).limit(1)):
        return

    rows = [
        dict(
            slug="pla", name="PLA", full_name="Polylactic acid", family="PLA", subfamily="Base polymer", family_color="#9b5de5",
            formula="(C₃H₄O₂)ₙ", repeat_unit="[—O—CH(CH₃)—C(=O)—]ₙ",
            description="Easy-printing bio-based polyester for prototypes, jigs and visual parts. The default low-risk material when heat is not involved.",
            best_for="Fast prototypes, visual parts, indoor jigs, dimensionally crisp shapes.", avoid_for="Hot cars, sun-loaded mechanisms, parts carrying load for a long time.",
            settings=settings("200–230 °C", "35–55 °C", "Cool / 20–35 °C", "50 °C · 6–8 h", "60–250 mm/s"),
            properties=properties(1.24, 57, 45, 2, 4, 1, 3, 2, 2, score(5,5,4,4,2,2,3,4,8,10,2,2,2), tensile="40–55 MPa", modulus="2.7–3.2 GPa", impact="Brittle compared with PETG, ASA and nylon", shrinkage="Very low"),
        ),
        dict(
            slug="pla-tough", name="PLA Tough", full_name="Impact-modified polylactic acid", family="PLA", subfamily="Toughened", family_color="#9b5de5",
            formula="(C₃H₄O₂)ₙ + impact modifier", repeat_unit="[—O—CH(CH₃)—C(=O)—]ₙ",
            description="Toughened PLA blend with better resistance to handling damage than normal PLA, while retaining easy printing.",
            best_for="Indoor clips, functional prototypes, parts that need more toughness than standard PLA.", avoid_for="High heat, outdoor sun, chemically aggressive environments.",
            settings=settings("210–240 °C", "35–55 °C", "Cool / 20–35 °C", "50 °C · 6–8 h", "60–220 mm/s"),
            properties=properties(1.24, 60, 50, 2, 4, 1, 3, 2, 2, score(5,5,4,4,5,2,3,4,8,9,2,2,3), tensile="40–50 MPa", modulus="2.3–2.8 GPa", impact="Much better than base PLA", shrinkage="Very low"),
        ),
        dict(
            slug="pla-cf", name="PLA-CF", full_name="Carbon-fibre-reinforced polylactic acid", family="PLA", subfamily="Carbon fibre", family_color="#9b5de5",
            formula="PLA + chopped carbon fibre", repeat_unit="[—O—CH(CH₃)—C(=O)—]ₙ + CF",
            description="Matte, stiff, low-warp PLA composite. Carbon fibre improves surface quality and stiffness, not high-temperature capability.",
            best_for="Stiff jigs, fixtures, cosmetic-functional brackets, dimensionally stable large PLA parts.", avoid_for="Impact parts, living hinges, hot environments, parts loaded through Z layers.",
            settings=settings("210–240 °C", "35–45 °C", "25–45 °C", "50–60 °C · 6–8 h", "40–160 mm/s", "0.4 mm TC accepted · 0.6 mm TC preferred"),
            properties=properties(1.22, 55, 45, 3, 5, 1, 3, 2, 3, score(8,6,4,3,2,2,3,5,7,7,3,2,4), tensile="~38 MPa", modulus="~3.95 GPa", impact="Stiff, not tough", shrinkage="Low"),
        ),
        dict(
            slug="petg", name="PETG", full_name="Glycol-modified polyethylene terephthalate", family="PETG", subfamily="Base polymer", family_color="#00b4d8",
            formula="(C₁₀H₁₂O₄)ₙ", repeat_unit="[—O—CH₂—CH₂—O—C(=O)—C₆H₄—C(=O)—]ₙ",
            description="The default practical functional filament: good toughness, water resistance and simple printing without ABS-like warping.",
            best_for="General brackets, enclosures, containers, workshop parts, moderate outdoor service.", avoid_for="High continuous heat, precision friction pairs, highly loaded long-term springs.",
            settings=settings("230–260 °C", "65–80 °C", "Cool / 20–35 °C", "60–70 °C · 6–8 h", "60–300 mm/s"),
            properties=properties(1.27, 69, 60, 3, 8, 2, 5, 5, 4, score(5,5,5,6,6,4,5,8,7,9,4,5,3), tensile="34–50 MPa", modulus="2.0–2.2 GPa", impact="Good general toughness", shrinkage="Low to moderate"),
        ),
        dict(
            slug="petg-cf", name="PETG-CF", full_name="Carbon-fibre-reinforced glycol-modified polyethylene terephthalate", family="PETG", subfamily="Carbon fibre", family_color="#00b4d8",
            formula="PETG + chopped carbon fibre", repeat_unit="[PETG repeat unit]ₙ + CF",
            description="Stiffer, more dimensionally stable PETG for fixtures and brackets where normal PETG flexes too much.",
            best_for="Stiff low-warp brackets, technical covers, moderate outdoor functional parts.", avoid_for="Impact-heavy components and flexible snap features.",
            settings=settings("250–275 °C", "70–85 °C", "25–45 °C", "60–70 °C · 6–8 h", "40–160 mm/s", "0.4 mm TC accepted · 0.6 mm TC preferred"),
            properties=properties(1.25, 74, 65, 3, 8, 2, 5, 5, 5, score(7,6,5,4,3,5,5,8,7,7,5,5,5), tensile="~46 MPa", modulus="~2.29 GPa", impact="Reduced versus PETG", shrinkage="Low"),
        ),
        dict(
            slug="tpu-95a", name="TPU 95A", full_name="Thermoplastic polyurethane, Shore 95A", family="Elastomer", subfamily="Flexible", family_color="#f59e0b",
            formula="Polyurethane elastomer", repeat_unit="[—R—NH—C(=O)—O—R′—]ₙ",
            description="Tough flexible elastomer for grip, damping and impact absorption. Normal TPU belongs in the main direct-drive hotend.",
            best_for="Feet, tyres, bumpers, flexible couplers, cable strain relief, seals.", avoid_for="Stiff brackets, tight dimensional fits, the auxiliary Bowden path.",
            settings=settings("220–250 °C", "30–50 °C", "Cool / <30 °C", "65–75 °C · 6–8 h", "20–80 mm/s", "0.4 mm TC · MAIN / LEFT only", True, False, "Low fan; slow controlled printing"),
            properties=properties(1.22, 0, 80, 6, 9, 2, 6, 4, 7, score(1,4,1,8,10,3,6,9,4,5,8,4,5), tensile="27–35 MPa", modulus="Elastomer", impact="Excellent energy absorption", shrinkage="Low"),
        ),
        dict(
            slug="abs", name="ABS", full_name="Acrylonitrile butadiene styrene", family="Styrenic", subfamily="Base polymer", family_color="#ef476f",
            formula="ABS terpolymer", repeat_unit="[styrene-co-acrylonitrile-co-butadiene]ₙ",
            description="Classic tough engineering plastic. In an actively heated X2D chamber it becomes a very practical inexpensive functional material.",
            best_for="Enclosures, functional workshop parts, moderate-heat brackets, impact-tolerant assemblies.", avoid_for="Outdoor UV exposure, poorly ventilated rooms, very large unsupported flat parts.",
            settings=settings("250–270 °C", "90–100 °C", "50–65 °C", "75–85 °C · 6–8 h", "40–180 mm/s", "0.4 mm TC", True, True, "Low to moderate fan"),
            properties=properties(1.05, 87, 80, 4, 7, 2, 5, 2, 5, score(5,6,5,6,8,5,5,7,6,6,5,2,3), tensile="35–45 MPa", modulus="2.0–2.3 GPa", impact="Good impact tolerance", shrinkage="Moderate to high"),
        ),
        dict(
            slug="abs-gf", name="ABS-GF", full_name="Glass-fibre-reinforced acrylonitrile butadiene styrene", family="Styrenic", subfamily="Glass fibre", family_color="#ef476f",
            formula="ABS + chopped glass fibre", repeat_unit="[ABS terpolymer]ₙ + GF",
            description="Stiff, low-warp ABS composite for technical housings and fixtures where standard ABS feels too flexible.",
            best_for="Stiff warm-chamber fixtures, technical housings and tooling.", avoid_for="Impact-heavy or thin flexing components.",
            settings=settings("260–280 °C", "90–100 °C", "55–65 °C", "75–85 °C · 6–8 h", "35–140 mm/s", "0.6 mm TC preferred", True, True, "Low fan"),
            properties=properties(1.08, 99, 90, 4, 7, 2, 5, 2, 6, score(7,6,5,4,3,6,5,7,6,5,6,2,5), tensile="~36 MPa", modulus="~3.0–3.5 GPa", impact="Lower than ABS", shrinkage="Moderate; fibre reduces warp"),
        ),
        dict(
            slug="asa", name="ASA", full_name="Acrylonitrile styrene acrylate", family="Styrenic", subfamily="UV-stable", family_color="#ef476f",
            formula="ASA terpolymer", repeat_unit="[styrene-co-acrylonitrile-co-acrylate rubber]ₙ",
            description="The outdoor version of ABS: similar processing but much better UV stability and weather resistance.",
            best_for="Outdoor brackets, vehicle exterior components, sun-exposed enclosures, garden or roof parts.", avoid_for="Poorly ventilated rooms, parts that must stay very flexible.",
            settings=settings("250–270 °C", "90–100 °C", "50–65 °C", "75–85 °C · 6–8 h", "40–180 mm/s", "0.4 mm TC", True, True, "Low fan"),
            properties=properties(1.07, 100, 85, 4, 8, 2, 5, 9, 6, score(5,6,5,6,6,6,5,8,6,6,5,9,4), tensile="40–50 MPa", modulus="2.1–2.4 GPa", impact="Moderate toughness", shrinkage="Moderate"),
        ),
        dict(
            slug="asa-cf", name="ASA-CF", full_name="Carbon-fibre-reinforced acrylonitrile styrene acrylate", family="Styrenic", subfamily="Carbon fibre", family_color="#ef476f",
            formula="ASA + chopped carbon fibre", repeat_unit="[ASA terpolymer]ₙ + CF",
            description="Stiff weather-resistant composite with excellent surface finish and reduced warping.",
            best_for="Outdoor stiff brackets, covers and technical exterior assemblies.", avoid_for="Anything that needs to flex or absorb a sharp impact.",
            settings=settings("260–285 °C", "90–100 °C", "55–65 °C", "75–85 °C · 6–8 h", "35–140 mm/s", "0.6 mm TC preferred", True, True, "Low fan"),
            properties=properties(1.02, 110, 95, 4, 8, 2, 5, 9, 7, score(8,6,5,3,3,7,5,8,6,5,7,9,6), tensile="~34 MPa", modulus="~3.74 GPa", impact="Reduced versus ASA", shrinkage="Low to moderate"),
        ),
        dict(
            slug="pc", name="PC", full_name="Polycarbonate", family="High-temp amorphous", subfamily="Base polymer", family_color="#4361ee",
            formula="(C₁₆H₁₄O₃)ₙ", repeat_unit="[—O—C₆H₄—C(CH₃)₂—C₆H₄—O—C(=O)—]ₙ",
            description="Strong, tough, heat-resistant engineering material. Moisture control and careful adhesion matter more than with PETG.",
            best_for="Heated enclosures, guards, strong indoor brackets, electrical housings, tough heat-resistant parts.", avoid_for="Easy beginner prints, long outdoor UV service without a UV-stable grade.",
            settings=settings("270–300 °C", "90–110 °C", "55–65 °C", "75–85 °C · 6–8 h", "30–120 mm/s", "0.4 mm TC", True, True, "Low fan"),
            properties=properties(1.20, 110, 100, 6, 7, 2, 5, 4, 7, score(7,7,6,6,8,8,5,7,4,4,7,4,7), tensile="55–65 MPa", modulus="~2.3 GPa", impact="Very tough when dry", shrinkage="Moderate; adhesion critical"),
        ),
        dict(
            slug="pa6", name="PA6 / Nylon 6", full_name="Polyamide 6 (nylon 6)", family="Polyamide", subfamily="Base polymer", family_color="#06a77d",
            formula="(C₆H₁₁NO)ₙ", repeat_unit="[—NH—(CH₂)₅—C(=O)—]ₙ",
            description="Tough, fatigue-resistant nylon for mechanisms and impact parts. It absorbs moisture rapidly, which changes both printing and service behaviour.",
            best_for="Wear parts, clips, living hinges, impact mechanisms, gears under moderate load.", avoid_for="Tight tolerance parts left wet, very stiff structural brackets, decorative surfaces.",
            settings=settings("250–285 °C", "70–100 °C", "45–65 °C", "75–85 °C · 8–12 h", "30–120 mm/s", "0.4 mm TC", True, True, "Low fan"),
            properties=properties(1.12, 65, 70, 10, 6, 2, 6, 3, 7, score(4,7,5,8,10,5,6,6,1,5,8,3,6), score(3,5,4,7,9,4,6,6,0,3,7,3,6), tensile="45–70 MPa dry; lower conditioned", modulus="1.0–1.8 GPa", impact="Very high", shrinkage="Moderate"),
        ),
        dict(
            slug="pa6-cf", name="PA6-CF", full_name="Carbon-fibre-reinforced polyamide 6", family="Polyamide", subfamily="Carbon fibre", family_color="#06a77d",
            formula="PA6 + chopped carbon fibre", repeat_unit="[—NH—(CH₂)₅—C(=O)—]ₙ + CF",
            description="The classic 3D-printed structural nylon composite: high stiffness, strong dry performance and dramatically lower warp than unfilled PA6.",
            best_for="Structural brackets, robot parts, machine components, heat-loaded fixtures.", avoid_for="Thin springy parts, impact-first components, printing with wet filament.",
            settings=settings("280–300 °C", "80–100 °C", "55–65 °C", "75–85 °C · 8–12 h", "30–110 mm/s", "0.6 mm TC preferred", True, False, "Low fan"),
            properties=properties(1.09, 186, 130, 10, 6, 2, 7, 3, 9, score(9,9,6,4,3,8,7,6,0,4,9,3,8), score(7,7,5,3,2,7,7,6,0,2,8,3,8), tensile="~102 MPa dry", modulus="~5.46 GPa", impact="Stiff rather than impact-first", shrinkage="Low for nylon due to CF"),
        ),
        dict(
            slug="pa6-gf", name="PA6-GF", full_name="Glass-fibre-reinforced polyamide 6", family="Polyamide", subfamily="Glass fibre", family_color="#06a77d",
            formula="PA6 + chopped glass fibre", repeat_unit="[—NH—(CH₂)₅—C(=O)—]ₙ + GF",
            description="Glass-filled nylon for stiff functional parts and electrical insulation behaviour. Similar handling discipline to PA6-CF.",
            best_for="Stiff functional components, electrical fixtures, warm mechanical parts.", avoid_for="Wear contact against soft mating parts and flexible impact parts.",
            settings=settings("280–300 °C", "80–100 °C", "55–65 °C", "75–85 °C · 8–12 h", "30–110 mm/s", "0.6 mm TC preferred", True, False, "Low fan"),
            properties=properties(1.14, 182, 125, 10, 6, 2, 7, 3, 8, score(8,8,6,4,3,8,7,6,0,4,8,3,7), score(6,6,5,3,2,7,7,6,0,2,7,3,7), tensile="~75 MPa dry", modulus="~3.67 GPa", impact="Stiff; lower impact than PA6", shrinkage="Low for nylon due to GF"),
        ),
        dict(
            slug="paht-cf", name="PAHT-CF", full_name="High-temperature carbon-fibre-reinforced polyamide", family="Polyamide", subfamily="High-temperature CF", family_color="#06a77d",
            formula="High-temperature polyamide + carbon fibre", repeat_unit="[—NH—R—C(=O)—]ₙ + CF",
            description="One of the best balanced high-performance X2D materials: stiff, strong and heat resistant with manageable warping when properly dried.",
            best_for="High-temperature machine brackets, tooling, automotive-style technical parts, stiff load-bearing assemblies.", avoid_for="Impact bumpers, wet storage, casual fast printing without temperature control.",
            settings=settings("280–300 °C", "80–100 °C", "55–65 °C", "75–85 °C · 8–12 h", "25–100 mm/s", "0.6 mm TC preferred", True, False, "Low fan"),
            properties=properties(1.06, 194, 150, 9, 7, 2, 8, 4, 9, score(9,8,6,4,3,9,8,7,1,4,9,4,9), score(7,6,5,3,2,8,8,7,0,2,8,4,9), tensile="~92 MPa dry", modulus="~4.23 GPa", impact="Structural, not a bumper material", shrinkage="Low for a high-temperature nylon"),
        ),
        dict(
            slug="pet-cf", name="PET-CF", full_name="Carbon-fibre-reinforced polyethylene terephthalate", family="Polyester composite", subfamily="Carbon fibre", family_color="#43aa8b",
            formula="PET + chopped carbon fibre", repeat_unit="[—O—CH₂—CH₂—O—C(=O)—C₆H₄—C(=O)—]ₙ + CF",
            description="High-HDT, stiff polyester composite with very good dimensional stability and chemical resistance for a high-performance X2D part.",
            best_for="High-heat fixtures, precision technical parts, chemically exposed structural brackets.", avoid_for="High-impact parts, relaxed moisture handling, small 0.4 mm fibre-heavy details.",
            settings=settings("280–300 °C", "80–100 °C", "55–65 °C", "75–85 °C · 8–12 h", "25–90 mm/s", "0.6 mm TC preferred", True, False, "Low fan"),
            properties=properties(1.29, 205, 165, 7, 8, 2, 8, 6, 9, score(9,8,6,4,3,9,8,8,2,4,9,6,9), score(8,7,5,3,2,8,8,8,1,3,8,6,9), tensile="~74 MPa", modulus="~5.32 GPa", impact="Stiff and dimensionally stable", shrinkage="Low to moderate"),
        ),
        dict(
            slug="ppa-cf", name="PPA-CF", full_name="Carbon-fibre-reinforced polyphthalamide", family="High-performance polyamide", subfamily="Carbon fibre", family_color="#d63384",
            formula="Aromatic polyamide + chopped carbon fibre", repeat_unit="[—NH—Ar—C(=O)—]ₙ + CF",
            description="The maximum practical X2D engineering material for heat, stiffness and dry structural load. It requires serious drying and operates near the 300 °C X2D ceiling.",
            best_for="Highest-heat structural brackets, technical powertrain-adjacent fixtures, premium engineering parts.", avoid_for="Casual printing, soft impact parts, use through the auxiliary filament path.",
            settings=settings("290–300 °C", "100–110 °C", "60–65 °C", "100–140 °C · 8–12 h", "20–80 mm/s", "0.6 mm TC strongly recommended · MAIN / LEFT only", True, False, "Low fan; dry enclosure / dry feed"),
            properties=properties(1.25, 227, 180, 10, 7, 4, 9, 5, 10, score(10,10,7,5,4,10,9,7,0,2,10,5,10), score(8,8,6,4,3,9,9,7,0,1,9,5,10), tensile="~168 MPa dry", modulus="~9.86 GPa", impact="Very stiff; use a tougher polymer when impact is primary", shrinkage="Low due to CF; drying is critical"),
        ),
        dict(
            slug="pva", name="PVA", full_name="Polyvinyl alcohol", family="Water-soluble support", subfamily="Support material", family_color="#64748b",
            formula="(C₂H₄O)ₙ", repeat_unit="[—CH₂—CH(OH)—]ₙ",
            description="Water-soluble support material for complex geometry, not a structural part material.",
            best_for="Dissolvable support interfaces, captive geometry, clean internal channels.", avoid_for="Finished parts, humidity exposure, casual open-spool storage.",
            settings=settings("190–220 °C", "35–50 °C", "Cool / <35 °C", "75–85 °C · 8–12 h", "20–60 mm/s", "0.4 mm dedicated hotend", True, True, "Low fan; preserve dryness"),
            properties=properties(1.23, 0, 0, 10, 0, 0, 2, 1, 0, score(2,1,2,3,1,1,2,0,0,3,1,1,9), score(1,0,1,1,0,0,1,0,0,0,0,0,9), tensile="Not structural", modulus="Not structural", impact="Not structural", shrinkage="N/A"),
        ),
    ]

    for data in rows:
        mat = Material(
            slug=data["slug"], name=data["name"], full_name=data["full_name"], family=data["family"],
            subfamily=data["subfamily"], family_color=data["family_color"], formula=data["formula"],
            repeat_unit=data["repeat_unit"], description=data["description"], best_for=data["best_for"],
            avoid_for=data["avoid_for"], settings_json=json.dumps(data["settings"]), properties_json=json.dumps(data["properties"]),
            source_notes=f"{SOURCE_X2D} {SOURCE_DRY}",
        )
        session.add(mat)

    session.flush()

    # Seed only three example products so the user immediately sees how prices, spool choice and calculator links work.
    petg = session.scalar(select(Material).where(Material.slug == "petg"))
    pa6cf = session.scalar(select(Material).where(Material.slug == "pa6-cf"))
    asa = session.scalar(select(Material).where(Material.slug == "asa"))
    examples = [
        (petg, "Bambu Lab", "PETG HF", "Bambu Lab EU", "", "Black", 1000, 23.99, "Example entry — replace with your own price or add more suppliers."),
        (pa6cf, "Bambu Lab", "PA6-CF", "Bambu Lab EU", "", "Black", 1000, 49.99, "Example engineering spool. Dry before every serious print."),
        (asa, "Bambu Lab", "ASA", "Bambu Lab EU", "", "Black", 1000, 27.99, "Example outdoor material entry."),
    ]
    for material, brand, product_name, supplier, url, colour, weight, price, notes in examples:
        if not material:
            continue
        product = FilamentProduct(
            material_id=material.id, brand=brand, product_name=product_name, supplier=supplier,
            url=url, color_name=colour, spool_weight_g=weight, notes=notes, favorite=True,
        )
        session.add(product)
        session.flush()
        session.add(PriceEntry(product_id=product.id, price_eur=price, observed_on=date.today(), source_label="Seed example"))

    session.commit()
