from __future__ import annotations

import sqlite3
import subprocess
import sys

from .database import DB_PATH


BASELINE_REVISION = "bee771ab1c79"
ENGINEERING_CORE_REVISION = "5c97e2fd405e"
SPOOL_REVISION = "8a7c4d9f2b31"
PRINTER_PROFILE_REVISION = "9c1d2e3f4a5b"

CORE_TABLES = {
    "materials",
    "filament_products",
    "price_entries",
    "print_profiles",
}
V2_TABLES = {
    "material_families",
    "material_variants",
    "property_definitions",
    "material_property_records",
}


def table_names(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    ).fetchall()
    return {row[0] for row in rows}


def column_names(connection: sqlite3.Connection, table_name: str) -> set[str]:
    try:
        rows = connection.execute(f'PRAGMA table_info("{table_name}")').fetchall()
    except sqlite3.DatabaseError:
        return set()
    return {row[1] for row in rows}


def current_alembic_version(connection: sqlite3.Connection) -> str | None:
    if "alembic_version" not in table_names(connection):
        return None
    row = connection.execute("SELECT version_num FROM alembic_version LIMIT 1").fetchone()
    return str(row[0]) if row and row[0] else None


def revision_for_untracked_schema(
    tables: set[str],
    filament_columns: set[str],
    profile_columns: set[str],
) -> str | None:
    if not CORE_TABLES.issubset(tables):
        return None

    has_v2_schema = V2_TABLES.issubset(tables)
    has_spool_schema = {"spool_code", "is_active"}.issubset(filament_columns)
    has_printer_schema = (
        "printer_presets" in tables
        and {"printer_id", "filament_used_g"}.issubset(profile_columns)
    )

    if has_v2_schema and has_spool_schema and has_printer_schema:
        return PRINTER_PROFILE_REVISION
    if has_v2_schema and has_spool_schema:
        return SPOOL_REVISION
    if has_v2_schema:
        return ENGINEERING_CORE_REVISION
    return BASELINE_REVISION


def main() -> None:
    if not DB_PATH.exists():
        print(f"Material Lab: no database exists yet at {DB_PATH}; Alembic will create it.")
        return

    with sqlite3.connect(DB_PATH) as connection:
        tables = table_names(connection)
        user_tables = {name for name in tables if not name.startswith("sqlite_")}
        if not user_tables:
            print(f"Material Lab: database at {DB_PATH} is empty; Alembic will create it.")
            return

        version = current_alembic_version(connection)
        if version:
            print(f"Material Lab: database already tracked by Alembic at {version}.")
            return

        revision = revision_for_untracked_schema(
            tables,
            column_names(connection, "filament_products"),
            column_names(connection, "print_profiles"),
        )

    if revision is None:
        print(
            "Material Lab: existing database is not a recognized Material Lab schema; "
            "leaving it unstamped so Alembic can fail clearly if incompatible."
        )
        return

    print(
        "Material Lab: existing database has Material Lab tables but no Alembic "
        f"revision; stamping {revision} before upgrade."
    )
    subprocess.run([sys.executable, "-m", "alembic", "stamp", revision], check=True)


if __name__ == "__main__":
    main()
