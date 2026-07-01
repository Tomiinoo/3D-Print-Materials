from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker


_DATA_DIR = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
os.environ.setdefault("MATERIAL_LAB_DATA_DIR", _DATA_DIR.name)

try:
    from fastapi.testclient import TestClient
except (ModuleNotFoundError, RuntimeError):  # pragma: no cover - local environments without httpx
    TestClient = None

from fastapi import HTTPException  # noqa: E402

from app.database import Base  # noqa: E402
from app.main import (  # noqa: E402
    app,
    material_compatibility,
    nozzle_tracked_hours,
    product_select_options,
    profile_payload,
    resolve_profile_links,
    stored_upload_path,
    update_nozzle_install_state,
    upload_root,
    validate_upload_filename,
)
from app.models import FilamentProduct, Material, PrinterMaintenance, PrinterNozzle, PrinterPreset, PrinterTool, PrintProfile  # noqa: E402


class PrinterReleaseTest(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine("sqlite:///:memory:", future=True)
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine, future=True)

    def test_existing_printer_can_be_edited_and_chamber_temperature_persists(self) -> None:
        with self.Session() as session:
            printer = PrinterPreset(slug="mk-test", name="MK Test", nozzle_max_c=280, bed_max_c=100)
            session.add(printer)
            session.commit()

            printer.name = "MK Test Edited"
            printer.description = "Enclosed workshop printer"
            printer.chamber_max_c = 55
            printer.heated_chamber = True
            session.commit()

            saved = session.scalar(select(PrinterPreset).where(PrinterPreset.slug == "mk-test"))
            self.assertEqual(saved.name, "MK Test Edited")
            self.assertEqual(saved.chamber_max_c, 55)
            self.assertTrue(saved.heated_chamber)

    def test_only_one_nozzle_can_be_marked_installed_per_printer(self) -> None:
        with self.Session() as session:
            printer = PrinterPreset(slug="printer", name="Printer")
            first = PrinterNozzle(printer=printer, label="0.4 brass", diameter_mm=0.4, installed=True)
            second = PrinterNozzle(printer=printer, label="0.6 steel", diameter_mm=0.6, installed=True)
            session.add_all([printer, first, second])
            session.flush()

            update_nozzle_install_state(printer, second)
            session.commit()

            self.assertFalse(first.installed)
            self.assertTrue(second.installed)

    def test_each_tool_can_have_its_own_installed_nozzle(self) -> None:
        with self.Session() as session:
            printer = PrinterPreset(slug="printer", name="Printer")
            first_tool = PrinterTool(printer=printer, name="Tool 1", tool_order=1, max_hotend_c=300)
            second_tool = PrinterTool(printer=printer, name="Tool 2", tool_order=2, max_hotend_c=300)
            first = PrinterNozzle(printer=printer, tool=first_tool, label="0.4 brass", diameter_mm=0.4, installed=True)
            second = PrinterNozzle(printer=printer, tool=second_tool, label="0.6 steel", diameter_mm=0.6, installed=True)
            session.add_all([printer, first_tool, second_tool, first, second])
            session.flush()

            update_nozzle_install_state(printer, first)
            update_nozzle_install_state(printer, second)
            session.commit()

            self.assertTrue(first.installed)
            self.assertTrue(second.installed)

    def test_effective_temperature_uses_lower_tool_and_nozzle_limit(self) -> None:
        with self.Session() as session:
            material = Material(slug="pc", name="PC", full_name="PC", family="High-temp")
            printer = PrinterPreset(slug="printer", name="Printer", nozzle_max_c=300, bed_max_c=120, enclosed=True)
            tool = PrinterTool(printer=printer, name="Main print tool", tool_order=1, max_hotend_c=300)
            nozzle = PrinterNozzle(
                printer=printer,
                tool=tool,
                label="0.4 confirmed nozzle",
                diameter_mm=0.4,
                installed=True,
                max_temp_c=280,
                abrasive_ready=False,
            )
            session.add_all([material, printer, tool, nozzle])
            session.commit()

            result = material_compatibility(material, {"nozzle": "290-300 C", "bed": "100 C"}, [printer])
            tool_result = result["printer_results"][0]["tool_results"][0]

            self.assertEqual(tool_result["effective_max_c"], 280)
            self.assertEqual(tool_result["status"], "not_recommended")
            self.assertTrue(any("280" in reason for reason in tool_result["blockers"]))

    def test_unknown_nozzle_temperature_needs_confirmation(self) -> None:
        with self.Session() as session:
            material = Material(slug="petg", name="PETG", full_name="PETG", family="Copolyester")
            printer = PrinterPreset(slug="printer", name="Printer", nozzle_max_c=300, bed_max_c=100)
            tool = PrinterTool(printer=printer, name="Main print tool", tool_order=1, max_hotend_c=300)
            nozzle = PrinterNozzle(printer=printer, tool=tool, label="unknown nozzle", diameter_mm=0.4, installed=True)
            session.add_all([material, printer, tool, nozzle])
            session.commit()

            result = material_compatibility(material, {"nozzle": "240-260 C", "bed": "80 C"}, [printer])
            self.assertEqual(result["printer_results"][0]["status"], "needs_confirmation")

    def test_abrasive_material_is_not_fully_approved_on_unsuitable_nozzle(self) -> None:
        with self.Session() as session:
            material = Material(slug="pla-cf", name="PLA-CF", full_name="PLA-CF", family="PLA", subfamily="Carbon fibre")
            printer = PrinterPreset(slug="printer", name="Printer", nozzle_max_c=300, bed_max_c=100)
            tool = PrinterTool(printer=printer, name="Main print tool", tool_order=1, max_hotend_c=300)
            nozzle = PrinterNozzle(
                printer=printer,
                tool=tool,
                label="0.4 brass",
                diameter_mm=0.4,
                nozzle_material="brass",
                installed=True,
                max_temp_c=300,
                abrasive_ready=False,
                carbon_fibre_suitable=False,
            )
            session.add_all([material, printer, tool, nozzle])
            session.commit()

            result = material_compatibility(
                material,
                {"nozzle": "210-240 C", "bed": "50 C", "recommended_nozzle": "0.6 mm hardened preferred"},
                [printer],
            )
            tool_result = result["printer_results"][0]["tool_results"][0]

            self.assertEqual(tool_result["status"], "not_recommended")
            self.assertTrue(any("abrasive-ready" in reason for reason in tool_result["blockers"]))

    def test_nozzle_hours_follow_print_duration_edits_and_deletes(self) -> None:
        with self.Session() as session:
            material = Material(slug="petg", name="PETG", full_name="PETG", family="Copolyester")
            printer = PrinterPreset(slug="printer", name="Printer")
            nozzle = PrinterNozzle(printer=printer, label="0.4 brass", diameter_mm=0.4, hours_before_tracking=5.5)
            profile = PrintProfile(
                material=material,
                printer=printer,
                printer_nozzle=nozzle,
                profile_name="test",
                print_duration_hours=2,
            )
            session.add_all([material, printer, nozzle, profile])
            session.commit()

            self.assertEqual(nozzle_tracked_hours(nozzle), 7.5)

            profile.print_duration_hours = 3.25
            session.commit()
            self.assertEqual(nozzle_tracked_hours(nozzle), 8.75)

            session.delete(profile)
            session.commit()
            self.assertEqual(nozzle_tracked_hours(nozzle), 5.5)

    def test_printer_specific_nozzle_filtering_is_enforced_on_save(self) -> None:
        with self.Session() as session:
            material = Material(slug="petg", name="PETG", full_name="PETG", family="Copolyester")
            first_printer = PrinterPreset(slug="first", name="First printer")
            second_printer = PrinterPreset(slug="second", name="Second printer")
            nozzle = PrinterNozzle(printer=first_printer, label="0.4 brass", diameter_mm=0.4)
            session.add_all([material, first_printer, second_printer, nozzle])
            session.commit()

            with self.assertRaises(HTTPException):
                resolve_profile_links(
                    session,
                    material.id,
                    "",
                    str(second_printer.id),
                    str(nozzle.id),
                )

    def test_historical_print_without_nozzle_remains_valid(self) -> None:
        with self.Session() as session:
            material = Material(slug="pla", name="PLA", full_name="PLA", family="PLA")
            profile = PrintProfile(material=material, profile_name="old profile", print_duration_hours=None)
            session.add_all([material, profile])
            session.commit()

            payload = profile_payload(profile)

            self.assertIsNone(payload["printer_nozzle_id"])
            self.assertEqual(payload["nozzle_label"], "")
            self.assertEqual(payload["print_duration_label"], "-")

    def test_edit_profile_payload_preserves_material_and_current_archived_product(self) -> None:
        with self.Session() as session:
            material = Material(slug="asa", name="ASA", full_name="ASA", family="Styrenic")
            product = FilamentProduct(
                material=material,
                brand="Bambu Lab",
                product_name="ASA",
                supplier="Bambu Lab EU",
                spool_code="S-003",
                is_active=False,
            )
            profile = PrintProfile(material=material, product=product, profile_name="old spool print")
            session.add_all([material, product, profile])
            session.commit()

            payload = profile_payload(profile)
            options = product_select_options(session, profile.product_id)

            self.assertEqual(payload["material_id"], material.id)
            self.assertEqual(payload["product_id"], product.id)
            self.assertIn(product.id, {option["id"] for option in options})

    def test_maintenance_record_crud(self) -> None:
        with self.Session() as session:
            printer = PrinterPreset(slug="printer", name="Printer")
            entry = PrinterMaintenance(
                printer=printer,
                maintenance_date=date(2026, 6, 1),
                maintenance_type="part replaced",
                component="hotend",
                notes="Replaced hotend",
                cost_eur=29.99,
                printer_hours=120,
            )
            session.add_all([printer, entry])
            session.commit()

            entry.component = "complete hotend"
            session.commit()
            self.assertEqual(session.get(PrinterMaintenance, entry.id).component, "complete hotend")

            session.delete(entry)
            session.commit()
            self.assertEqual(session.scalars(select(PrinterMaintenance)).all(), [])

    def test_attachment_validation_and_storage_path_are_safe(self) -> None:
        extension, category, max_bytes = validate_upload_filename("part-photo.webp")
        self.assertEqual((extension, category, max_bytes), (".webp", "photo", 20 * 1024 * 1024))

        extension, category, max_bytes = validate_upload_filename("fixture.3mf")
        self.assertEqual((extension, category, max_bytes), (".3mf", "model", 100 * 1024 * 1024))

        with self.assertRaises(HTTPException):
            validate_upload_filename("../escape.jpg")
        with self.assertRaises(HTTPException):
            validate_upload_filename("part.exe")

        target = stored_upload_path("print-profiles/1/example.stl")
        self.assertIn(upload_root().resolve(), target.parents)

    @unittest.skipIf(TestClient is None, "fastapi TestClient requires httpx")
    def test_dashboard_guide_compare_and_core_routes_return_200(self) -> None:
        routes = ["/", "/inventory", "/printers", "/printers/new", "/materials", "/guide", "/compare", "/calculator", "/settings"]
        with TestClient(app) as client:
            for route in routes:
                with self.subTest(route=route):
                    self.assertEqual(client.get(route).status_code, 200)


class MigrationUpgradeTest(unittest.TestCase):
    def run_alembic(self, data_dir: Path, *args: str) -> None:
        env = os.environ.copy()
        env["MATERIAL_LAB_DATA_DIR"] = str(data_dir)
        result = subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=Path(__file__).resolve().parents[1],
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            self.fail(result.stdout + result.stderr)

    def table_columns(self, db_path: Path, table: str) -> set[str]:
        with sqlite3.connect(db_path) as connection:
            return {row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')}

    def test_fresh_upgrade_old_upgrade_and_restart_are_idempotent(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as fresh_dir:
            fresh_path = Path(fresh_dir)
            self.run_alembic(fresh_path, "upgrade", "head")
            self.run_alembic(fresh_path, "upgrade", "head")
            db_path = fresh_path / "material_lab.sqlite3"
            self.assertIn("printer_nozzle_id", self.table_columns(db_path, "print_profiles"))
            self.assertIn("chamber_max_c", self.table_columns(db_path, "printer_presets"))

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as old_dir:
            old_path = Path(old_dir)
            self.run_alembic(old_path, "upgrade", "9c1d2e3f4a5b")
            self.run_alembic(old_path, "upgrade", "head")
            db_path = old_path / "material_lab.sqlite3"
            self.assertIn("print_duration_hours", self.table_columns(db_path, "print_profiles"))
            with sqlite3.connect(db_path) as connection:
                tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertIn("printer_nozzles", tables)
            self.assertIn("printer_maintenance", tables)
            self.assertIn("print_attachments", tables)


if __name__ == "__main__":
    unittest.main()
