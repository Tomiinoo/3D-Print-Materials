# Home Assistant local app package

This folder now contains a self-contained local Home Assistant app build for **aarch64** Raspberry Pi systems and **amd64** systems.

## Practical recommendation

- **Raspberry Pi OS / Debian / normal Docker host:** use the root `docker-compose.yml`. It is the simplest and most predictable route.
- **Home Assistant OS / Supervisor:** copy the contents of `home-assistant-addon/` into a Git repository, add that repository under **Settings → Apps → App store → ⋮ → Repositories**, then install **Material Lab**. The first local build happens on the Pi; later, publish prebuilt aarch64 images for quicker updates.

The database lives in the app `/data` mapping, so it is included in Home Assistant backups. The app is exposed on port `8080` by default.

This package uses a standard Docker image and does not use Home Assistant internal APIs. It is simply a locally managed web application.
