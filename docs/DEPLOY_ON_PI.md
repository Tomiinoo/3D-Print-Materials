# Deploy Material Lab on your Raspberry Pi

## Option A — recommended: Docker Compose on Raspberry Pi OS / Debian

1. Install Docker Engine and the Docker Compose plugin on the Pi.
2. Copy the extracted `material-lab` folder to the Pi, for example to `/opt/material-lab`.
3. Run:

```bash
cd /opt/material-lab
docker compose up -d --build
docker compose ps
docker compose logs -f
```

4. Open: `http://<PI-IP>:8080`

The first start creates `data/material_lab.sqlite3`. Never delete the `data` directory unless you want to reset the app.

### Update after changing code

```bash
cd /opt/material-lab
docker compose up -d --build
```

### Backup

- Download a JSON export from **Settings** in the app.
- Also copy the `data` directory to your NAS / backup destination.

## Option B — Home Assistant OS / Supervisor

Use the self-contained `home-assistant-addon/` package only when you run Home Assistant OS / Supervisor and deliberately want this installed as a local Home Assistant app. Read `home-assistant-addon/README.md` first.

## Access from outside home

Use Tailscale or a reverse proxy with authentication. Do not simply port-forward port 8080 from your router.
