from __future__ import annotations

import html
import json
import math
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any


APP_DIR = Path(__file__).resolve().parent
MAPPING_PATH = APP_DIR / "static" / "data" / "polymer_structure_mapping_all_catalog.json"


TYPE_LABELS = {
    "repeat_unit": "Exact repeating unit",
    "representative_repeat": "Representative repeat",
    "copolymer_schematic": "Copolymer schematic",
    "block_copolymer_schematic": "Copolymer schematic",
    "blend_schematic": "Blend schematic",
    "blend_or_graft_schematic": "Graft-polymer schematic",
    "blend_or_network_schematic": "Blend schematic",
    "graft_copolymer_schematic": "Graft-polymer schematic",
    "segmented_polymer_schematic": "Segmented polymer schematic",
    "family_schematic": "Polymer-family schematic",
    "modifier_only": "Modifier only — base resin required",
}

BASE_LABELS = {
    "abs_graft": "ABS",
    "asa_graft": "ASA",
    "bvoh": "BVOH",
    "copolyester_generic": "copolyester",
    "eva": "EVA",
    "hips": "HIPS",
    "lcp": "LCP family",
    "modifier_only": "base resin required",
    "pa11": "PA11",
    "pa12": "PA12",
    "pa6": "PA6",
    "pa610": "PA610",
    "pa612": "PA612",
    "pa66": "PA66",
    "pa_copolymer": "polyamide copolymer",
    "pa_generic": "polyamide",
    "paht": "PAHT family",
    "pbt": "PBT",
    "pc": "PC",
    "pc_abs_blend": "PC + ABS",
    "pc_blend_generic": "PC blend",
    "pc_pbt_blend": "PC + PBT",
    "pc_pet_blend": "PC + PET",
    "pc_ptfe_blend": "PC + PTFE",
    "pe": "PE",
    "peek": "PEEK",
    "pei": "PEI",
    "pekk": "PEKK",
    "pesu": "PESU",
    "pet": "PET",
    "petg_copolyester": "PETG / copolyester",
    "pla": "PLA",
    "pmma": "PMMA",
    "polystyrene": "PS",
    "pom": "POM",
    "pp": "PP",
    "ppa": "PPA family",
    "pps": "PPS",
    "ppsu": "PPSU",
    "psu": "PSU",
    "pva": "PVA",
    "pvb": "PVB",
    "pvdf": "PVDF",
    "san_random": "SAN",
    "sbs": "SBS",
    "sebs": "SEBS",
    "soft_pla": "PLA blend",
    "support_breakaway": "breakaway support",
    "tpc_segmented": "TPC",
    "tpe_generic": "TPE family",
    "tpu_segmented": "TPU",
    "tpv_blend": "TPV",
}

EXACT_REPEAT_TEMPLATES = {
    "pla": {
        "groups": [("label", "O"), ("label", "CH"), ("label", "C")],
        "side_groups": [(1, "CH3", "up"), (2, "O", "up_double")],
    },
    "pet": {
        "groups": [("label", "O-CH2-CH2-O"), ("label", "C"), ("ring", "p-phenylene"), ("label", "C")],
        "side_groups": [(1, "O", "up_double"), (3, "O", "up_double")],
    },
    "pbt": {
        "groups": [("label", "O-(CH2)4-O"), ("label", "C"), ("ring", "p-phenylene"), ("label", "C")],
        "side_groups": [(1, "O", "up_double"), (3, "O", "up_double")],
    },
    "pa6": {
        "groups": [("label", "NH"), ("label", "(CH2)5"), ("label", "C")],
        "side_groups": [(2, "O", "up_double")],
    },
    "pa11": {
        "groups": [("label", "NH"), ("label", "(CH2)10"), ("label", "C")],
        "side_groups": [(2, "O", "up_double")],
    },
    "pa12": {
        "groups": [("label", "NH"), ("label", "(CH2)11"), ("label", "C")],
        "side_groups": [(2, "O", "up_double")],
    },
    "pa66": {
        "groups": [("label", "NH"), ("label", "(CH2)6"), ("label", "NH"), ("label", "C"), ("label", "(CH2)4"), ("label", "C")],
        "side_groups": [(3, "O", "up_double"), (5, "O", "up_double")],
    },
    "pa610": {
        "groups": [("label", "NH"), ("label", "(CH2)6"), ("label", "NH"), ("label", "C"), ("label", "(CH2)8"), ("label", "C")],
        "side_groups": [(3, "O", "up_double"), (5, "O", "up_double")],
    },
    "pa612": {
        "groups": [("label", "NH"), ("label", "(CH2)6"), ("label", "NH"), ("label", "C"), ("label", "(CH2)10"), ("label", "C")],
        "side_groups": [(3, "O", "up_double"), (5, "O", "up_double")],
    },
    "pc": {
        "groups": [("label", "O"), ("ring", "phenylene"), ("label", "C(CH3)2"), ("ring", "phenylene"), ("label", "O"), ("label", "C")],
        "side_groups": [(5, "O", "up_double")],
    },
    "peek": {
        "groups": [("label", "O"), ("ring", "phenylene"), ("label", "O"), ("ring", "phenylene"), ("label", "C"), ("ring", "phenylene")],
        "side_groups": [(4, "O", "up_double")],
    },
    "pps": {
        "groups": [("ring", "p-phenylene"), ("label", "S")],
    },
    "pe": {"groups": [("label", "CH2"), ("label", "CH2")]},
    "pp": {
        "groups": [("label", "CH2"), ("label", "CH")],
        "side_groups": [(1, "CH3", "up")],
    },
    "pva": {
        "groups": [("label", "CH2"), ("label", "CH")],
        "side_groups": [(1, "OH", "up")],
    },
    "pvdf": {"groups": [("label", "CH2"), ("label", "CF2")]},
    "pom": {"groups": [("label", "CH2"), ("label", "O")]},
    "pmma": {
        "groups": [("label", "CH2"), ("label", "C")],
        "side_groups": [(1, "CH3", "up"), (1, "C(=O)OCH3", "down")],
    },
    "polystyrene": {
        "groups": [("label", "CH2"), ("label", "CH")],
        "side_groups": [(1, "phenyl", "ring_up")],
    },
}


def normalize_material_name(value: str | None) -> str:
    text = unicodedata.normalize("NFKC", value or "").lower()
    text = text.replace("+", " plus ")
    text = re.sub(r"\bpolyamide\s+(\d+)\b", r"pa\1", text)
    text = re.sub(r"\bnylon\s+(\d+)\b", r"pa\1", text)
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _record_value(material_record: Any, *keys: str) -> str:
    for key in keys:
        if isinstance(material_record, dict):
            value = material_record.get(key)
        else:
            value = getattr(material_record, key, None)
        if value:
            return str(value)
    return ""


def _candidate_names(material_record: Any) -> list[str]:
    raw_values = [
        _record_value(material_record, "material_name", "name", "short_name"),
        _record_value(material_record, "full_name"),
        _record_value(material_record, "slug").replace("-", " "),
    ]
    candidates: list[str] = []
    for raw in raw_values:
        raw = raw.strip()
        if not raw:
            continue
        candidates.append(raw)
        if "/" in raw:
            candidates.extend(part.strip() for part in raw.split("/") if part.strip())

    seen = set()
    unique: list[str] = []
    for candidate in candidates:
        key = normalize_material_name(candidate)
        if key and key not in seen:
            unique.append(candidate)
            seen.add(key)
    return unique


@lru_cache(maxsize=1)
def load_structure_mapping() -> dict[str, Any]:
    return json.loads(MAPPING_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _normalized_assignment_index() -> dict[str, str]:
    mapping = load_structure_mapping()
    assignments = mapping.get("material_assignments", {})
    return {
        normalize_material_name(name): name
        for name in assignments
        if normalize_material_name(name)
    }


def _find_assignment(material_record: Any) -> tuple[str, dict[str, Any]] | tuple[None, None]:
    assignments = load_structure_mapping().get("material_assignments", {})

    for candidate in _candidate_names(material_record):
        if candidate in assignments:
            return candidate, assignments[candidate]

    normalized_index = _normalized_assignment_index()
    for candidate in _candidate_names(material_record):
        normalized = normalize_material_name(candidate)
        mapped_name = normalized_index.get(normalized)
        if mapped_name:
            return mapped_name, assignments[mapped_name]

    return None, None


def _infer_additive_badges(material_name: str, classification: str, assignment: dict[str, Any]) -> list[str]:
    explicit = assignment.get("additives")
    badges: list[str] = []
    if isinstance(explicit, list):
        badges.extend(str(item) for item in explicit if item)
    elif explicit and str(explicit).lower() != "see material name":
        badges.append(str(explicit))

    haystack = f"{material_name} {classification}".lower()
    checks = [
        (("cf", "carbon fiber", "carbon fibre"), "Carbon-fibre filled"),
        (("gf", "glass fiber", "glass fibre"), "Glass-fibre filled"),
        (("aramid", "kevlar"), "Aramid-fibre reinforcement"),
        (("basalt",), "Basalt-fibre reinforcement"),
        (("esd",), "ESD formulation"),
        (("conductive",), "Conductive formulation"),
        (("fr", "flame-retardant", "flame retardant"), "Flame-retardant formulation"),
        (("glow", "phosphorescent"), "Glow pigment additive"),
        (("magnetic", "iron"), "Magnetic mineral filler"),
        (("metal", "aluminum", "aluminium", "brass", "bronze", "copper", "steel", "tungsten"), "Metal-filled formulation"),
        (("wood", "cork", "bamboo", "hemp", "coffee", "shell"), "Natural-filler formulation"),
        (("ceramic", "mineral", "stone"), "Mineral/ceramic filler"),
        (("foaming", "aero", "lw-"), "Foaming formulation"),
        (("recycled",), "Recycled feedstock"),
        (("support", "breakaway"), "Support formulation"),
        (("matte", "silk", "pro", "tough", "plus", "hf", "hs", "dynamic", "transparent"), "Formulation grade"),
    ]
    padded = f" {haystack.replace('-', ' ')} "
    for needles, label in checks:
        if any(needle in padded for needle in needles) and label not in badges:
            badges.append(label)

    if assignment.get("structure_key") == "modifier_only" and not badges:
        badges.append(material_name)

    base_material = normalize_material_name(material_name)
    if base_material in {"pva", "bvoh", "hips"} and "Support formulation" in badges:
        badges.remove("Support formulation")

    return badges


def _fallback_structure(material_record: Any) -> dict[str, Any]:
    material_name = _record_value(material_record, "material_name", "name", "short_name") or "Unknown material"
    return {
        "material_name": material_name,
        "matched_material_name": "",
        "structure_key": "",
        "structure_title": "Chemical structure not yet curated",
        "iupac_style_name": "",
        "render_mode": "fallback",
        "type_label": "Chemical structure not yet curated",
        "formula": "",
        "chemistry_status": "missing local mapping",
        "diagram_note": "This record has no local canonical-structure mapping yet.",
        "structural_relation": "",
        "additives": [],
        "base_chemistry_label": "",
        "variant_label": "",
        "svg_asset_url": "",
        "svg_markup": "",
        "fallback": True,
    }


def resolve_polymer_structure(material_record: Any) -> dict[str, Any]:
    material_name = _record_value(material_record, "material_name", "name", "short_name") or "Unknown material"
    classification = _record_value(material_record, "classification", "subfamily", "family")
    matched_name, assignment = _find_assignment(material_record)
    if not assignment:
        return _fallback_structure(material_record)

    mapping = load_structure_mapping()
    structure_key = assignment["structure_key"]
    structure = mapping.get("structures", {}).get(structure_key)
    if structure is None:
        return _fallback_structure(material_record)

    render_mode = structure.get("render_mode", "")
    additives = _infer_additive_badges(material_name, classification, assignment)
    base_label = BASE_LABELS.get(structure_key, structure.get("short_label") or structure.get("title", structure_key))
    structural_relation = assignment.get("structural_relation", "")
    if not structural_relation and additives and structure_key != "modifier_only":
        structural_relation = f"{base_label} base chemistry with a separate formulation or additive package; additives are not part of the repeat unit."
    elif not structural_relation and render_mode != "repeat_unit":
        structural_relation = structure.get("chemistry_status", "")

    resolved = {
        "material_name": material_name,
        "matched_material_name": matched_name,
        "structure_key": structure_key,
        "structure_title": structure.get("title", "Polymer structure"),
        "iupac_style_name": structure.get("iupac_style_name", ""),
        "render_mode": render_mode,
        "type_label": TYPE_LABELS.get(render_mode, "Polymer-family schematic"),
        "formula": structure.get("formula", ""),
        "chemistry_status": structure.get("chemistry_status", ""),
        "diagram_note": structure.get("diagram_note", ""),
        "structural_relation": structural_relation,
        "additives": additives,
        "base_chemistry_label": (
            "Base resin required"
            if structure_key == "modifier_only"
            else f"Base chemistry: {base_label}"
        ),
        "variant_label": f"Variant: {', '.join(additives)}" if additives else "",
        "svg_asset_url": "",
        "fallback": False,
    }
    resolved["svg_markup"] = render_structure_svg(resolved)
    return resolved


def validate_catalog_structure_mappings(catalog_names: list[str] | None = None) -> dict[str, Any]:
    if catalog_names is None:
        from .catalog import CATALOG_RECORDS

        catalog_names = [str(record.get("Material", "")).strip() for record in CATALOG_RECORDS]

    missing = [
        name
        for name in catalog_names
        if resolve_polymer_structure({"name": name})["fallback"]
    ]
    return {
        "total": len(catalog_names),
        "resolved": len(catalog_names) - len(missing),
        "missing": missing,
    }


def _svg_text(value: str) -> str:
    return html.escape(value or "", quote=True)


def _group(x: float, y: float, label: str, width: float = 68) -> str:
    return (
        f'<rect class="chem-label-box" x="{x - width / 2:g}" y="{y - 18:g}" width="{width:g}" height="36" rx="10" />'
        f'<text class="chem-label" x="{x:g}" y="{y + 4:g}" text-anchor="middle">{_svg_text(label)}</text>'
    )


def _ring(cx: float, cy: float, radius: float = 26, label: str = "") -> str:
    points = []
    for index in range(6):
        angle = math.pi / 6 + index * math.pi / 3
        points.append(f"{cx + radius * math.cos(angle):g},{cy + radius * math.sin(angle):g}")
    inner = []
    for index in range(6):
        angle = math.pi / 6 + index * math.pi / 3
        inner.append(f"{cx + (radius - 7) * math.cos(angle):g},{cy + (radius - 7) * math.sin(angle):g}")
    return (
        f'<polygon class="chem-ring" points="{" ".join(points)}" />'
        f'<polygon class="chem-ring-inner" points="{" ".join(inner)}" />'
        f'<text class="chem-ring-label" x="{cx:g}" y="{cy + radius + 15:g}" text-anchor="middle">{_svg_text(label)}</text>'
    )


def _bond(x1: float, y1: float, x2: float, y2: float, dashed: bool = False) -> str:
    cls = "chem-bond chem-bond--dashed" if dashed else "chem-bond"
    return f'<line class="{cls}" x1="{x1:g}" y1="{y1:g}" x2="{x2:g}" y2="{y2:g}" />'


def _brackets() -> str:
    return (
        '<path class="chem-bracket" d="M42 92 h-16 v116 h16" />'
        '<path class="chem-bracket" d="M478 92 h16 v116 h-16" />'
        '<text class="chem-n" x="492" y="226">n</text>'
    )


def _carbonyl(x: float, y: float, direction: str) -> str:
    if direction == "up_double":
        return (
            _bond(x - 4, y - 18, x - 4, y - 48)
            + _bond(x + 4, y - 18, x + 4, y - 48)
            + f'<text class="chem-atom" x="{x:g}" y="{y - 58:g}" text-anchor="middle">O</text>'
        )
    return ""


def _side_group(x: float, y: float, label: str, direction: str) -> str:
    if direction == "up_double":
        return _carbonyl(x, y, direction)
    if direction == "ring_up":
        return _bond(x, y - 18, x, y - 44) + _ring(x, y - 78, 22, "phenyl")
    dy = -50 if direction == "up" else 50
    text_y = y + dy - 8 if direction == "up" else y + dy + 12
    return (
        _bond(x, y + (-18 if direction == "up" else 18), x, y + dy)
        + f'<text class="chem-atom" x="{x:g}" y="{text_y:g}" text-anchor="middle">{_svg_text(label)}</text>'
    )


def _render_repeat_unit_svg(resolved: dict[str, Any]) -> str:
    key = resolved["structure_key"]
    template = EXACT_REPEAT_TEMPLATES.get(key)
    title = _svg_text(resolved["structure_title"])
    desc = _svg_text(resolved["diagram_note"])
    formula = _svg_text(resolved["formula"])

    if not template:
        return _render_family_svg(resolved)

    groups = template["groups"]
    y = 145
    start = 82
    end = 438
    step = (end - start) / max(1, len(groups) - 1)
    xs = [start + index * step for index in range(len(groups))]
    pieces = [_brackets()]
    for index in range(len(groups) - 1):
        pieces.append(_bond(xs[index] + 34, y, xs[index + 1] - 34, y))
    for index, (kind, label) in enumerate(groups):
        if kind == "ring":
            pieces.append(_ring(xs[index], y, 27, label))
        else:
            pieces.append(_group(xs[index], y, label, 96 if len(label) > 8 else 68))
    for index, label, direction in template.get("side_groups", []):
        if 0 <= index < len(xs):
            pieces.append(_side_group(xs[index], y, label, direction))

    return f"""
<svg class="polymer-svg" viewBox="0 0 520 300" role="img" aria-label="{title}">
  <title>{title}</title>
  <desc>{desc}</desc>
  <rect class="chem-canvas" x="1" y="1" width="518" height="298" rx="18" />
  <text class="chem-mode" x="26" y="34">Exact repeating unit</text>
  {''.join(pieces)}
  <text class="chem-formula" x="260" y="270" text-anchor="middle">{formula}</text>
</svg>
""".strip()


def _block(x: float, y: float, w: float, h: float, label: str, dashed: bool = False) -> str:
    cls = "chem-block chem-block--dashed" if dashed else "chem-block"
    return (
        f'<rect class="{cls}" x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" rx="14" />'
        f'<text class="chem-block-label" x="{x + w / 2:g}" y="{y + h / 2 + 4:g}" text-anchor="middle">{_svg_text(label)}</text>'
    )


def _render_family_svg(resolved: dict[str, Any]) -> str:
    title = _svg_text(resolved["structure_title"])
    desc = _svg_text(resolved["diagram_note"])
    formula = _svg_text(resolved["formula"])
    type_label = _svg_text(resolved["type_label"])
    mode = resolved["render_mode"]

    if mode == "modifier_only":
        visual = (
            '<path class="chem-fibre" d="M96 102 C168 54 218 184 302 132 S398 72 444 168" />'
            '<path class="chem-fibre chem-fibre--muted" d="M86 172 C160 116 230 224 310 172 S405 122 452 214" />'
            + _block(154, 112, 212, 58, "Base resin required", True)
        )
    elif "graft" in mode:
        visual = (
            '<ellipse class="chem-domain" cx="230" cy="148" rx="126" ry="48" />'
            '<text class="chem-domain-label" x="230" y="153" text-anchor="middle">rubber / backbone domain</text>'
            + _bond(244, 105, 338, 67)
            + _bond(278, 122, 398, 106)
            + _bond(248, 191, 370, 228)
            + _block(332, 42, 126, 44, "SAN graft", False)
            + _block(388, 84, 92, 44, "styrene / AN", True)
            + _block(350, 212, 124, 44, "graft chain", False)
        )
    elif "blend" in mode:
        visual = (
            _block(78, 104, 156, 82, "component A", False)
            + '<text class="chem-plus" x="260" y="154" text-anchor="middle">+</text>'
            + _block(286, 104, 156, 82, "component B", True)
        )
    elif "segmented" in mode or "block" in mode:
        visual = (
            _block(62, 116, 104, 56, "hard segment", False)
            + _block(178, 116, 132, 56, "soft segment", True)
            + _block(322, 116, 104, 56, "hard segment", False)
            + _bond(166, 144, 178, 144)
            + _bond(310, 144, 322, 144)
        )
    elif "copolymer" in mode:
        visual = (
            _block(62, 116, 122, 56, "repeat A", False)
            + _block(198, 116, 122, 56, "variable comonomer", True)
            + _block(334, 116, 122, 56, "repeat B", False)
            + _bond(184, 144, 198, 144, True)
            + _bond(320, 144, 334, 144, True)
        )
    else:
        visual = (
            _brackets()
            + _group(150, 145, "R", 58)
            + _bond(184, 145, 252, 145, True)
            + _group(286, 145, "polymer motif", 128)
            + _bond(350, 145, 410, 145, True)
            + _group(438, 145, "R'", 58)
        )

    return f"""
<svg class="polymer-svg" viewBox="0 0 520 300" role="img" aria-label="{title}">
  <title>{title}</title>
  <desc>{desc}</desc>
  <rect class="chem-canvas" x="1" y="1" width="518" height="298" rx="18" />
  <text class="chem-mode" x="26" y="34">{type_label}</text>
  <text class="chem-variation-tag" x="494" y="34" text-anchor="end">composition varies by grade</text>
  {visual}
  <text class="chem-formula" x="260" y="270" text-anchor="middle">{formula}</text>
</svg>
""".strip()


def render_structure_svg(resolved: dict[str, Any]) -> str:
    if resolved.get("fallback"):
        return ""
    if resolved.get("render_mode") == "repeat_unit":
        return _render_repeat_unit_svg(resolved)
    return _render_family_svg(resolved)
