# Material Lab — X2D Engineering Filament Database

A self-hosted material library, spool-price tracker, engineering comparison tool and print-cost calculator.
It is deliberately designed as a local-first app: all materials, test profiles, supplier prices and notes live in SQLite on your Pi.

## First launch on Raspberry Pi / Debian / Docker host

```bash
git clone <your-repository-url> material-lab
cd material-lab
docker compose up -d --build
```

Open `http://<your-pi-ip>:8080`.

Your persistent data is in `./data/material_lab.sqlite3`. Back it up by copying the `data` folder or use the in-app JSON export.

## What is implemented in this first version

- Dark blue / purple responsive engineering UI.
- Searchable material library with family and CF/GF styling.
- Material detail pages: repeat unit, printing settings, drying, data cards, decision notes and engineering score bars.
- Product / spool entries: brand, supplier, URL, spool mass, price, notes and multiple price-history entries.
- Saved real print profiles: nozzle, bed, chamber, dryer, speed, build plate, result rating and notes.
- Comparison page: dry vs moisture-conditioned state, radar chart, grouped bar chart and heat-vs-impact scatter chart.
- Calculator: exact filament product price, volume, support volume, purge, waste and optional energy cost.
- New material form built around a flexible JSON property block, so the database can grow without changing the schema every time.
- JSON export and local backup endpoint.

## Deliberate first-version limit: live prices

Live shop scraping is not enabled by default. Retailer pages change frequently, some block automation, and scraping can make a local tool unreliable. The app is already structured for it: each product has a source URL and price history. Add a connector per trusted retailer later, or import prices manually until you know which shops matter.

## Important engineering warning

The seeded scores and values are material-selection guidance, not certified design allowables. Exact values vary by grade, manufacturer, colour, fibre content, drying condition and printed orientation. Validate a final part in its final print orientation and under the real load/temperature.

## Home Assistant

For a normal Raspberry Pi Docker host, use `docker compose` above. If you run Home Assistant OS and want it inside the Supervisor, the `home-assistant-addon/` folder is a starter local-app repository. See its README before using it; Docker Compose is the simpler route when you have a standard Debian/Pi host.
