# Deploy Material Lab on your Raspberry Pi

Pushing to GitHub does not automatically update the Raspberry Pi. The Pi runs whatever code is currently on the Pi until you deliberately update it.

Before deploying anything, back up the Pi data folder. The app code is replaceable. Your spool prices, tests and notes are not replaceable unless you backed them up like a sensible future person.

## Option A — recommended: Docker Compose on Raspberry Pi OS / Debian

1. Install Docker Engine and the Docker Compose plugin on the Pi.
2. Copy the extracted `material-lab` folder to the Pi, for example to `/opt/material-lab`.
3. Make sure the persistent data folder exists:

```bash
mkdir -p /opt/material-lab/data
```

4. Run:

```bash
cd /opt/material-lab
docker compose up -d --build
docker compose ps
docker compose logs -f
```

5. Open: `http://<PI-IP>:8080`

Docker Compose sets `MATERIAL_LAB_DATA_DIR=/data` inside the container and maps the host folder like this:

```text
./data:/data
```

So the Pi database lives at:

```text
/opt/material-lab/data/material_lab.sqlite3
```

The first start creates that database if it does not exist. Never delete the `data` directory unless you want to reset the app.

### Update after changing code

Safe update flow:

```text
1. Test the code locally.
2. Review git diff.
3. Back up /opt/material-lab/data.
4. Copy or pull the reviewed code on the Pi.
5. Rebuild the Docker Compose app.
6. Open the app and verify materials, inventory, prices and settings.
```

```bash
cd /opt/material-lab
docker compose up -d --build
```

This rebuilds the app container. It should not delete the database because the database is in the mounted `data` folder.

### Backup

- Download a JSON export from **Settings** in the app.
- Also copy the `data` directory to your NAS / backup destination.
- Do this before major code changes and before any database migration.

Example:

```bash
cd /opt/material-lab
tar -czf material-lab-data-backup-$(date +%Y%m%d-%H%M%S).tar.gz data
```

## Option B — Home Assistant OS / Supervisor

Use the self-contained `home-assistant-addon/` package only when you run Home Assistant OS / Supervisor and deliberately want this installed as a local Home Assistant app. Read `home-assistant-addon/README.md` first.

## Access from outside home

Use Tailscale or a reverse proxy with authentication. Do not simply port-forward port 8080 from your router.

The app is designed as a private workshop tool, not as an internet-facing service. If you expose it publicly without authentication, the security model is basically "please be nice", which is not a security model.
