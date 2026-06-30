from __future__ import annotations

import os
import tempfile
import unittest
from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


_DATA_DIR = tempfile.TemporaryDirectory()
os.environ["MATERIAL_LAB_DATA_DIR"] = _DATA_DIR.name

from app.database import Base  # noqa: E402
from app.main import api_calculate, parse_form_date, product_filament_usage  # noqa: E402
from app.models import FilamentProduct, Material, PriceEntry, PrintProfile  # noqa: E402


class InventoryCalculatorTest(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine("sqlite:///:memory:", future=True)
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine, future=True)

    def test_parse_form_date_accepts_backdated_values(self) -> None:
        self.assertEqual(parse_form_date("2026-05-14", "Print date"), date(2026, 5, 14))

    def test_spool_usage_counts_logged_print_grams(self) -> None:
        with self.Session() as session:
            product = self._create_product(session)
            product.print_profiles.append(PrintProfile(material=product.material, profile_name="small", filament_used_g=125.5))
            product.print_profiles.append(PrintProfile(material=product.material, profile_name="large", filament_used_g=74.5))
            session.commit()

            used_g, remaining_g, remaining_percent = product_filament_usage(product)

        self.assertEqual(used_g, 200.0)
        self.assertEqual(remaining_g, 800.0)
        self.assertEqual(remaining_percent, 80.0)

    def test_calculator_prices_direct_used_grams(self) -> None:
        with self.Session() as session:
            product = self._create_product(session)
            session.commit()

            result = api_calculate(
                product_id=product.id,
                used_g=150,
                energy_kwh=0.5,
                electricity_eur_kwh=0.30,
                session=session,
            )

        self.assertEqual(result["total_mass_g"], 150)
        self.assertEqual(result["support_mass_g"], 0)
        self.assertEqual(result["material_cost_eur"], 2.29)
        self.assertEqual(result["energy_cost_eur"], 0.15)
        self.assertEqual(result["total_cost_eur"], 2.44)

    def _create_product(self, session):
        material = Material(
            slug="petg",
            name="PETG",
            full_name="Polyethylene terephthalate glycol",
            family="Copolyester",
            properties_json='{"density_g_cm3": 1.27}',
        )
        product = FilamentProduct(
            material=material,
            brand="ELEGOO",
            product_name="PETG PRO",
            spool_weight_g=1000,
        )
        product.price_entries.append(
            PriceEntry(price_eur=15.29, observed_on=date(2026, 6, 30), source_label="Manual")
        )
        session.add(product)
        session.flush()
        return product


if __name__ == "__main__":
    unittest.main()
