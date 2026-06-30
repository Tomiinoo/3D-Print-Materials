# Material Lab

Material Lab is a private, local-first web app for managing 3D-printing materials, filaments, spools, printer presets, print profiles, prices, and personal print results.

It is designed as a practical workshop tool: one place to compare material families, track exact products, record what worked on a specific printer, and make better material choices before buying or printing.

## Purpose

Material Lab helps with tasks such as:

* comparing polymer families and filament variants;
* tracking exact supplier products, spool prices, and availability;
* assigning and managing spool inventory numbers;
* storing printer compatibility and recommended print settings;
* recording personal print results, failures, and notes;
* keeping manufacturer sources and evidence beside technical values;
* comparing engineering trade-offs such as heat resistance, stiffness, strength, moisture sensitivity, and cost;
* building shortlists for a specific use case or print requirement.

The app is intended for personal use, a home workshop, or a small lab environment.

## Current Status

Material Lab is functional as a local workshop application.

It is not intended to be a public SaaS product, a certified engineering database, or a replacement for manufacturer documentation.

Use the app as a structured decision and documentation tool. For critical parts, always verify the exact manufacturer data sheet for the exact filament product and test the final printed part under realistic conditions.

## Main Features

* Material Library with search, filters, printer compatibility, polymer-family information, and engineering values.
* Material Guide with requirement scoring and filtering for material properties such as temperature resistance, price, tensile strength, stiffness, and printability.
* Compare page with material selection, family grouping, real-value and score-based comparison modes, bar charts, radar charts, and trade-off maps.
* Material detail pages with technical values, chemistry information, evidence sources, confidence indicators, readiness checklists, exact products, spool tracking, price history, and print profiles.
* Inventory page for tracking exact filament products, spool quantities, supplier pricing, printer history, and repeat-purchase decisions.
* Calculator for estimating filament cost, mass, volume, support material, purge material, waste, and optional electricity cost.
* Settings page for printer presets, exports, database backups, and local data configuration.
* V2 material preview routes for the newer evidence-first material data model.

## Technical Stack

Material Lab is built with:

* FastAPI
* Jinja templates
* SQLAlchemy
* SQLite
* Vanilla JavaScript
* Custom CSS

Most pages are server-rendered HTML. JavaScript is used for interactive filtering, comparison tools, guide ranking, charts, toggles, and small workflow helpers.

## How the App Starts

When the app starts, it:

1. opens the configured SQLite database;
2. creates missing tables through SQLAlchemy;
3. seeds default material data and printer presets without intentionally removing existing records;
4. serves the local application pages.

The main sections include Material Library, Material Guide, Compare, Inventory, Calculator, Settings, and V2 material preview routes.

## Data Storage

SQLite is the source of truth for the app.

For a normal local Python installation, the default database location is:

```text
app/data/material_lab.sqlite3
```

When using Docker Compose, the container uses:

```text
MATERIAL_LAB_DATA_DIR=/data
```

The persistent database on the host is stored at:

```text
./data/material_lab.sqlite3
```

You can set a custom data directory with:

```text
MATERIAL_LAB_DATA_DIR=/path/to/your/data
```

The repository is configured so that private data folders and SQLite databases can remain outside Git. This allows the application code and documentation to be version-controlled while personal prices, spool records, notes, and print results stay local.

## Backups

Use the Settings page to create:

* JSON exports;
* SQLite backups.

Before a significant update, also make a manual copy of the persistent data folder.

For a local Python installation:

```text
app/data/
```

For Docker Compose:

```text
data/
```

When running Material Lab on a Raspberry Pi, back up the `data` folder before deploying updates. Do not delete the folder unless you intentionally want to reset the application database.

## Local Development

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

Open the application in your browser:

```text
http://127.0.0.1:8000
```

Port `8000` is intended for local development.

## Raspberry Pi Deployment

The Raspberry Pi deployment uses Docker Compose and normally exposes the app on port `8080`.

Pushing changes to GitHub does not automatically update the Raspberry Pi. The Pi must be updated deliberately by pulling or copying the reviewed code and rebuilding the Docker Compose application.

Deployment instructions are available in:

```text
docs/DEPLOY_ON_PI.md
```

Before deploying changes:

1. test the changes locally;
2. review the Git diff;
3. back up the Raspberry Pi database;
4. deploy only the changes you have reviewed.

## Git and Private Data

Before pushing changes to a repository, check:

```powershell
git diff --check
git status
```

Do not stage or commit private data such as:

* `data/`
* `app/data/`
* `backups/`
* `uploads/`
* `*.sqlite`
* `*.sqlite3`
* `.env`

The source code and documentation can be stored in Git, while personal workshop data should remain local and be backed up separately.

## Privacy and Security

Material Lab is designed to run locally and does not require an account or cloud service for normal use.

For safer operation:

* run it on a local PC or Raspberry Pi inside your home network;
* use Tailscale or an authenticated reverse proxy for remote access;
* keep the SQLite database outside Git;
* create backups before updates;
* treat source links, prices, notes, and print results as private data.

Avoid directly exposing the app to the public internet through port forwarding without proper authentication and access controls.

## Engineering Data Disclaimer

The seeded catalog data and material values are intended for comparison, planning, and material selection.

They are not certified design allowables.

Actual performance can vary depending on:

* manufacturer and product grade;
* color and filler content;
* filament drying;
* nozzle type and nozzle temperature;
* chamber temperature;
* print orientation;
* layer height and wall structure;
* annealing;
* part geometry;
* print settings;
* environmental conditions.

For a loaded, safety-relevant, heat-critical, or long-term functional part, confirm the exact product technical data sheet and test the final printed part.

## Home Assistant

For a normal Raspberry Pi running Debian or another standard Linux distribution, Docker Compose is the recommended deployment method.

The `home-assistant-addon/` folder contains a starter package for users who intentionally want to run Material Lab inside Home Assistant Supervisor. Read the add-on documentation before using that route.
