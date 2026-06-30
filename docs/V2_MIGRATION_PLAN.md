# Material Lab V2 — Migration Plan

**Status:** Draft
**Purpose:** Upgrade the prototype database into the V2 engineering-data system without losing personal data, material edits, prices, notes, print profiles, or future uploaded files.

---

## 1. Non-negotiable safety rules

1. Never delete or recreate the live SQLite database during an upgrade.
2. Never deploy an untested schema change directly to the Raspberry Pi.
3. Back up the Pi database before every production migration.
4. Test migrations first against a copied database.
5. Preserve existing records wherever possible.
6. Do not invent ownership of a spool from an existing product or price record.
7. Keep old data available until the V2 replacement has been checked manually.
8. Personal live data must never be committed to GitHub.

---

## 2. Current prototype database

Current persistent database location on the Raspberry Pi:

```text
~/material-lab/data/material_lab.sqlite3
```

Current prototype tables:

```text
materials
filament_products
price_entries
print_profiles
```

Current application startup behaviour:

```text
Base.metadata.create_all(...)
seed_materials(...)
```

This is acceptable for the prototype but not sufficient for safe V2 schema changes.

---

## 3. V2 migration system

Material Lab V2 will use database migrations.

Each migration is a small, versioned instruction such as:

```text
Create a new table.
Add a field.
Copy old data into a new structure.
Create an index.
Preserve historical records.
```

Migration sequence:

```text
Current prototype database
→ migration 001: add migration tracking
→ migration 002: material families and material variants
→ migration 003: property records and sources
→ migration 004: products, suppliers and price observations
→ migration 005: physical spools and inventory
→ migration 006: print profiles and print results
→ migration 007: calculated score rules
```

The migration tool will be Alembic, which is designed for SQLAlchemy applications.

---

## 4. Production deployment safety procedure

Before any V2 database migration on the Pi:

```text
1. Stop or place the application into maintenance mode.
2. Copy the SQLite database to a timestamped backup file.
3. Verify that the backup file exists and is non-zero in size.
4. Pull the tested code from GitHub.
5. Run the migration.
6. Start Material Lab.
7. Verify materials, prices, profiles and inventory in the browser.
8. Keep the pre-migration database backup until the upgrade is confirmed.
```

Example future backup naming:

```text
material_lab_pre_v2_2026-06-28_1845.sqlite3
```

---

## 5. Planned V2 data mapping

### Existing `Material`

Current generic `Material` records become V2 **Material Variants**.

Examples:

```text
PETG
PA6-CF
ASA
PPA-CF
```

A new **Material Family** record will be created from the current family value.

Example:

```text
Current:
family = Polyamide
name = PA6-CF

V2:
Material Family = Polyamide
Material Variant = PA6-CF
```

Existing material descriptions, recommended settings, chemistry fields, sources, notes and active status must be retained.

---

### Existing `properties_json`

Current JSON values will be imported as initial reference values.

Examples:

```text
density_g_cm3
hdt_c
continuous_service_c
tensile_mpa
modulus_gpa
moisture sensitivity
water resistance
chemical resistance
UV resistance
```

V2 will gradually convert these into proper property records containing:

```text
Value
Unit
Material state
Test condition
Test standard
Source type
Source reference
Confidence
Notes
```

The old JSON must remain readable until the imported values are checked.

---

### Existing `FilamentProduct`

Current products remain manufacturer product records.

Examples:

```text
Bambu Lab PETG HF
Bambu Lab PA6-CF
Bambu Lab ASA
```

Current product colour, spool mass and supplier information are not automatically proof of a real spool owned by the user.

Therefore:

```text
Existing product
→ migrated as Product

Existing price entry
→ migrated as Product Price Observation

Existing physical spool
→ created only when explicitly added or confirmed by the user
```

---

### Existing `PriceEntry`

Price entries remain historical price observations.

V2 expands each observation with:

```text
Currency
Supplier
Product URL
Net filament mass
Calculated price per kilogram
Shipping included
Observed or purchased
Stock note
Date
```

Existing values should be retained as:

```text
Currency = EUR
Shipping included = unknown
Type = legacy observed price
```

---

### Existing `PrintProfile`

The current prototype mixes profile settings and real result information.

V2 separates:

```text
Print Profile
→ reusable settings recommendation

Print Result / Personal Test
→ one actual printed outcome
```

Existing records should first migrate as **legacy personal print results**, because they already include:

```text
Printed date
Result rating
Notes
```

A reusable profile may later be created from a successful print result.

---

## 6. What must not happen

The V2 migration must never:

```text
Delete all materials
Overwrite your edited temperature settings
Reset your price history
Assume every product is owned
Convert estimated scores into fake measured values
Replace your personal notes with seed data
Destroy the current database without a verified backup
```

---

## 7. Development and production flow

```text
Windows PC
→ develop and test V2 safely

GitHub branch
→ stores reviewed source code and documentation

Raspberry Pi
→ runs the stable deployed version

Pi data directory
→ holds the real database and personal information
→ is backed up separately
```

The V2 branch remains separate from the running stable branch until a tested release is ready.

---

## 8. Initial V2 implementation order

1. Add Alembic migration support.
2. Create automatic database backup tooling.
3. Create material family and material variant tables.
4. Create property, source and measurement tables.
5. Create supplier, product and price-observation tables.
6. Create physical-spool inventory tables.
7. Split print profiles from real print results.
8. Implement calculated score rules.
9. Replace prototype pages gradually.
10. Migrate the Pi only after the new system has been tested locally.
