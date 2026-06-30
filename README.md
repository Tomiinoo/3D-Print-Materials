# Material Lab

Material Lab is a private, local-first material and filament management app for 3D printing.
It stores material data, exact products, spool prices, printer presets, print profiles, personal results, source notes, and engineering trade-offs in one place.

It exists because "I think this filament is probably fine" is not a process. It is a mood with a nozzle temperature.

## Current Status

This project is usable as a local workshop app, but it is not a polished public SaaS product and it is not a certified engineering database.

Use it for:

- comparing polymer families and filament variants;
- tracking exact supplier products and spool prices;
- assigning inventory-style spool numbers;
- storing printer compatibility and print settings;
- recording personal print results;
- keeping source/evidence notes beside real material values;
- making better shortlists before buying material.

Do not use it as:

- a certified design-allowables database;
- a public internet service without authentication;
- a replacement for the exact manufacturer TDS for the exact spool/product you buy;
- an excuse to skip testing a loaded printed part.

## How The App Works

Material Lab is a FastAPI web app with Jinja templates, SQLAlchemy models, SQLite storage, vanilla JavaScript, and custom CSS.

At startup the app:

1. opens the configured SQLite database;
2. creates missing tables with SQLAlchemy;
3. seeds default materials and printer presets without intentionally wiping your existing records;
4. serves local pages such as Material Library, Material Guide, Compare, Inventory, Calculator, Settings, and the V2 material preview routes.

The browser UI talks to the same local FastAPI app. Most pages are normal server-rendered HTML, with JavaScript used for interactive filtering, comparison charts, guide ranking, toggles, and small workflow helpers.

## Where Your Data Is Saved

SQLite is the source of truth.

On a normal local Python run, the default database path is:

```text
app/data/material_lab.sqlite3
```

When running with Docker Compose, the container sets `MATERIAL_LAB_DATA_DIR=/data`, and the host folder is:

```text
./data/material_lab.sqlite3
```

You can override the data location with:

```text
MATERIAL_LAB_DATA_DIR=/path/to/your/data
```

The repository is configured to ignore private data folders and SQLite files. That means your app code can go to GitHub, while your personal material notes, prices, spools, and print results stay local.

Still, do backups. SQLite is reliable; human confidence is the part that usually needs supervision.

## Backup

Use Settings in the app for:

- JSON export;
- SQLite backup.

Also copy the persistent data folder before any serious update:

```text
app/data/
```

or, for Docker Compose:

```text
data/
```

If you run this on a Raspberry Pi, back up the Pi `data` folder before deploying changes. Do not delete it unless you are deliberately resetting the app.

## Local Development

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

Open:

```text
http://127.0.0.1:8000
```

Use port 8000 for local development. The Raspberry Pi Docker setup uses port 8080, so do not confuse the two and accidentally celebrate against the wrong app.

## Raspberry Pi Deployment

Pushing to GitHub does not automatically update the Raspberry Pi. Git is not a teleportation device, despite how confidently developers stare at terminals.

The Pi only changes when you intentionally update it, for example by pulling/copying the reviewed code on the Pi and rebuilding the Docker Compose app. See:

```text
docs/DEPLOY_ON_PI.md
```

Before doing that:

1. test locally;
2. review `git diff`;
3. back up the Pi database;
4. deploy only when you are comfortable with the exact changes.

## Is It Ready To Push?

It can be ready to push to a private Git repository after review, but pushing should only store source code and docs.

Before pushing, check:

```powershell
git diff --check
git status
```

Make sure these are not staged or committed:

- `data/`
- `app/data/`
- `backups/`
- `uploads/`
- `*.sqlite`
- `*.sqlite3`
- `.env`

Do not push straight to production from excitement. Excitement is useful for motivation, not release management.

## Safety And Privacy

Material Lab is local-first. It does not need an account or cloud service for normal operation.

That does not make it magically secure.

Safer use:

- run it on your PC or Raspberry Pi inside your home network;
- use Tailscale or a reverse proxy with authentication for remote access;
- keep the SQLite database out of Git;
- back up before updates;
- treat source URLs, prices, notes, and print results as private workshop data.

Unsafe use:

- port-forwarding the app directly to the internet;
- committing the SQLite database;
- deploying unreviewed migrations to the Pi;
- assuming approximate catalog values are manufacturer-certified data.

## Implemented Features

- Material Library with search, quick filters, printer/path compatibility, real engineering values, and family/variant cards.
- Material Guide with requirement scoring, printer/path filtering, and advanced real-value filters for heat, price, tensile strength, and stiffness.
- Compare page with family grouping, selectable materials, score/real-value modes, bar charts, radar profile, and trade-off map controls.
- Material detail pages with real values, score orientation, chemistry display, source/evidence drawers, confidence strip, readiness checklist, spool workflow, products, price history, and print profiles.
- Inventory page for exact products, spool-style tracking, supplier prices, printer/profile history, and "buy again" decisions.
- Calculator for real product price, mass/volume, supports, purge, waste, and optional energy cost.
- Settings page for local database location, backups, exports, and printer presets.
- V2 material preview routes for the newer evidence-first data model.

## Engineering Warning

The seeded and catalog values are useful for selection, comparison, and planning. They are not certified design values.

Exact performance changes with manufacturer, grade, color, filler content, drying, print orientation, nozzle, chamber, annealing, and the specific part geometry. For a critical part, confirm the exact product TDS and test the final printed design.

## Home Assistant

For a normal Raspberry Pi Docker host, use Docker Compose. If you run Home Assistant OS and deliberately want this inside the Supervisor, the `home-assistant-addon/` folder is a starter local-app package. Read its README first. Docker Compose is the simpler route when you have a standard Debian/Pi host.
