#!/bin/sh
set -eu

PROJECT_DIR="/home/pipi/material-lab"
BACKUP_DIR="/home/pipi"
LOCAL_URL="http://127.0.0.1:8080/"

usage() {
    echo "Usage: ./scripts/deploy-material-lab.sh v2.2" >&2
}

die() {
    echo "ERROR: $*" >&2
    exit 1
}

if [ "$#" -ne 1 ]; then
    usage
    exit 64
fi

TAG="$1"

for command_name in git tar date docker curl; do
    if ! command -v "$command_name" >/dev/null 2>&1; then
        die "$command_name is required but was not found."
    fi
done

cd "$PROJECT_DIR" || die "Cannot enter $PROJECT_DIR."

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    die "$PROJECT_DIR is not a Git working tree."
fi

if [ -n "$(git status --porcelain)" ]; then
    echo "Git working tree is not clean. Commit, stash or remove local changes first:" >&2
    git status --short >&2
    exit 1
fi

if [ ! -d data ]; then
    die "Cannot back up ./data because it does not exist."
fi

TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
SAFE_TAG="$(printf '%s' "$TAG" | tr -c 'A-Za-z0-9._-' '_')"
BACKUP_FILE="$BACKUP_DIR/material-lab-data-$SAFE_TAG-$TIMESTAMP.tar.gz"

echo "Creating data backup: $BACKUP_FILE"
tar -czf "$BACKUP_FILE" data

echo "Fetching tags from origin..."
git fetch origin --tags

if ! git rev-parse -q --verify "refs/tags/$TAG" >/dev/null; then
    die "Tag '$TAG' does not exist."
fi

TAG_COMMIT="$(git rev-list -n 1 "refs/tags/$TAG")"

echo "Checking out $TAG ($TAG_COMMIT)..."
git checkout --detach "$TAG_COMMIT"

echo "Building and starting Material Lab..."
if ! docker compose up -d --build; then
    echo "Docker Compose failed to build or start Material Lab." >&2
    echo "Recent material-lab container logs:" >&2
    docker compose logs --tail=150 material-lab >&2 || true
    exit 1
fi

echo "Waiting up to 60 seconds for $LOCAL_URL to return HTTP 200..."
SUCCESS=0
SECONDS_WAITED=0
while [ "$SECONDS_WAITED" -lt 60 ]; do
    HTTP_STATUS="$(curl -fsS -o /dev/null -w '%{http_code}' "$LOCAL_URL" 2>/dev/null || true)"
    if [ "$HTTP_STATUS" = "200" ]; then
        SUCCESS=1
        break
    fi
    SECONDS_WAITED=$((SECONDS_WAITED + 1))
    sleep 1
done

if [ "$SUCCESS" -ne 1 ]; then
    echo "Material Lab did not become healthy within 60 seconds." >&2
    echo "Recent material-lab container logs:" >&2
    docker compose logs --tail=150 material-lab >&2
    exit 1
fi

CURRENT_COMMIT="$(git rev-parse HEAD)"

echo "Deployment successful."
echo "Deployed tag: $TAG"
echo "Current commit: $CURRENT_COMMIT"
echo "Backup file: $BACKUP_FILE"
echo "Local URL: $LOCAL_URL"
