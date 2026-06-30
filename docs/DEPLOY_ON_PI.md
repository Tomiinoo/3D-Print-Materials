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

On every container start, the Docker entrypoint runs:

```bash
python -m app.migration_preflight
alembic upgrade head
```

The preflight only handles old Material Lab databases that have known tables but no `alembic_version` row. It stamps the closest known revision so Alembic can apply the remaining migrations. It does not delete, recreate, reset or overwrite `/data/material_lab.sqlite3`.

This is safe to run repeatedly. If the database is already at the latest migration, Alembic does nothing. If preflight or migration fails, the container exits and the app does not start.

### Update after changing code

Safe release update flow:

1. Test the code locally.
2. Review git diff.
3. Back up `/opt/material-lab/data`.
4. Pull or copy the reviewed code on the Pi.
5. Rebuild and restart the Docker Compose app.
6. Check the container logs and Alembic revision.
7. Open the app and verify materials, inventory, prices and settings.

Exact update commands for a Git checkout on the Pi:

```bash
cd /opt/material-lab
tar -czf material-lab-data-backup-$(date +%Y%m%d-%H%M%S).tar.gz data
git pull --ff-only
docker compose build material-lab
docker compose up -d material-lab
docker compose logs --tail=120 material-lab
docker compose exec material-lab alembic current
```

If you update by copying files instead of Git, replace `git pull --ff-only` with your copy step, then run the same Docker commands.

This rebuilds the app container. It must not delete the database because the database is in the mounted `data` folder.

### Rollback

Rollback should restore both the old application code and the matching database backup. Do not try to downgrade a live SQLite database in place.

Use the backup created before the release:

```bash
cd /opt/material-lab
docker compose down
mv data data.failed-$(date +%Y%m%d-%H%M%S)
tar -xzf /path/to/material-lab-data-backup-YYYYMMDD-HHMMSS.tar.gz
git checkout <previous-good-commit>
docker compose build material-lab
docker compose up -d material-lab
docker compose logs --tail=120 material-lab
docker compose exec material-lab alembic current
```

The `mv data ...` step keeps the failed-release database for inspection instead of deleting it.

### Migration verification before release

These checks use temporary host folders mounted as `/data`. They do not touch `/opt/material-lab/data`.

Build the image to test:

```bash
cd /opt/material-lab
docker build -t material-lab:verify .
```

Fresh empty database:

```bash
fresh_dir=$(mktemp -d)
docker rm -f material-lab-verify-fresh >/dev/null 2>&1 || true
docker run --rm -d --name material-lab-verify-fresh -p 18080:8080 -v "$fresh_dir:/data" material-lab:verify
sleep 8
curl -fsS http://127.0.0.1:18080/settings >/dev/null
docker exec material-lab-verify-fresh alembic current
docker logs material-lab-verify-fresh --tail=80
docker rm -f material-lab-verify-fresh
```

Older database migration:

```bash
old_dir=$(mktemp -d)
cp /path/to/pre-update/material_lab.sqlite3 "$old_dir/material_lab.sqlite3"
docker rm -f material-lab-verify-old >/dev/null 2>&1 || true
docker run --rm -d --name material-lab-verify-old -p 18081:8080 -v "$old_dir:/data" material-lab:verify
sleep 8
curl -fsS http://127.0.0.1:18081/settings >/dev/null
docker exec material-lab-verify-old alembic current | grep "(head)"
docker logs material-lab-verify-old --tail=80
docker rm -f material-lab-verify-old
```

Already-migrated database restart:

```bash
docker rm -f material-lab-verify-current >/dev/null 2>&1 || true
docker run --rm -d --name material-lab-verify-current -p 18082:8080 -v "$old_dir:/data" material-lab:verify
sleep 8
curl -fsS http://127.0.0.1:18082/settings >/dev/null
docker exec material-lab-verify-current alembic current | grep "(head)"
docker logs material-lab-verify-current --tail=80
docker rm -f material-lab-verify-current
```

The third check reuses `old_dir` after the second check has migrated it. It proves that starting the same version again is idempotent.

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
