from __future__ import annotations

import unittest

from app.catalog import CATALOG_RECORDS
from app.polymer_structure_resolver import (
    load_structure_mapping,
    resolve_polymer_structure,
    validate_catalog_structure_mappings,
)


class PolymerStructureMappingTest(unittest.TestCase):
    def test_supplied_mapping_covers_current_catalog(self) -> None:
        result = validate_catalog_structure_mappings()
        self.assertEqual(result["total"], 191)
        self.assertEqual(result["resolved"], 191)
        self.assertEqual(result["missing"], [])

    def test_every_assignment_targets_existing_structure_key(self) -> None:
        mapping = load_structure_mapping()
        structures = set(mapping["structures"])
        missing_keys = {
            name: assignment["structure_key"]
            for name, assignment in mapping["material_assignments"].items()
            if assignment["structure_key"] not in structures
        }
        self.assertEqual(missing_keys, {})

    def test_catalog_record_names_match_mapping_count(self) -> None:
        names = [record["Material"] for record in CATALOG_RECORDS]
        self.assertEqual(len(names), 191)
        self.assertEqual(len(set(names)), 191)

    def test_acceptance_examples_resolve_honestly(self) -> None:
        cases = {
            "PLA": ("pla", "Exact repeating unit"),
            "PLA-CF": ("pla", "Exact repeating unit"),
            "PETG": ("petg_copolyester", "Copolymer schematic"),
            "ABS": ("abs_graft", "Graft-polymer schematic"),
            "ASA": ("asa_graft", "Graft-polymer schematic"),
            "TPU 95A": ("tpu_segmented", "Segmented polymer schematic"),
            "PA6": ("pa6", "Exact repeating unit"),
            "PA66-CF": ("pa66", "Exact repeating unit"),
            "PPA-CF": ("ppa", "Representative repeat"),
            "PC": ("pc", "Exact repeating unit"),
            "PC-ABS": ("pc_abs_blend", "Blend schematic"),
            "PPS-CF": ("pps", "Exact repeating unit"),
            "PEEK-CF": ("peek", "Exact repeating unit"),
            "PVA": ("pva", "Exact repeating unit"),
            "Carbon Fiber Filled": ("modifier_only", "Modifier only — base resin required"),
        }
        for material_name, (structure_key, type_label) in cases.items():
            with self.subTest(material_name=material_name):
                resolved = resolve_polymer_structure({"name": material_name})
                self.assertFalse(resolved["fallback"])
                self.assertEqual(resolved["structure_key"], structure_key)
                self.assertEqual(resolved["type_label"], type_label)

    def test_variant_additives_stay_outside_base_repeat_unit(self) -> None:
        resolved = resolve_polymer_structure({"name": "PLA-CF", "classification": "Carbon fibre"})
        self.assertEqual(resolved["structure_key"], "pla")
        self.assertEqual(resolved["iupac_style_name"], "poly(2-hydroxypropanoic acid)")
        self.assertIn("Carbon-fibre filled", resolved["additives"])
        self.assertIn("not part of the PLA repeat unit", resolved["structural_relation"])

    def test_iupac_style_name_is_exposed_for_schematic_records(self) -> None:
        resolved = resolve_polymer_structure({"name": "PETG"})
        self.assertEqual(resolved["type_label"], "Copolymer schematic")
        self.assertEqual(
            resolved["iupac_style_name"],
            "glycol-modified polyethylene terephthalate copolyester",
        )

    def test_v2_alias_style_name_resolves_without_changing_record(self) -> None:
        resolved = resolve_polymer_structure({"name": "PA6 / Nylon 6", "slug": "pa6"})
        self.assertFalse(resolved["fallback"])
        self.assertEqual(resolved["matched_material_name"], "PA6")
        self.assertEqual(resolved["structure_key"], "pa6")


if __name__ == "__main__":
    unittest.main()
