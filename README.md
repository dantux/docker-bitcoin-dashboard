# Docker Bitcoin Dashboard

A lightweight, self-hosted dashboard for a Bitcoin Knots node running in
Docker. The backend talks to Knots over its private Docker network and serves a
responsive, dependency-free web interface.

## Features

- Node sync, chain, connection, mempool, fee, uptime, and disk statistics
- Latest block cards and a detailed peer table
- Docker-native Bitcoin RPC connectivity
- Optional Electrs, Tor, mempool explorer, and host-metrics integrations
- Capability-driven UI that hides disabled integrations
- Dark and light themes with persistent browser preference
- Cached background collection to avoid excessive RPC traffic
- Docker health and readiness endpoints
- Docker secret support for the RPC password

## Architecture

The browser only talks to the dashboard's `/api/status` endpoint. The Python
backend performs authenticated JSON-RPC calls to Knots, collects enabled
optional integrations, and refreshes a shared cache every 30 seconds. The
frontend refreshes from that cache every 60 seconds.

The dashboard does not require access to the Docker socket.

## Quick start

### 1. Prepare configuration

```bash
cp .env.example .env
mkdir -p secrets
install -m 600 /dev/null secrets/bitcoin_rpc_password
nano secrets/bitcoin_rpc_password
```

Set `BITCOIN_RPC_USER` in `.env` and place only its plain-text password in the
secret file. Both files are excluded from Git.

The default configuration expects:

- Knots container DNS name: `bitcoin-knots`
- Knots RPC port: `8332`
- Existing Docker network: `bitcoinknots_default`
- Dashboard port: `8335`

Adjust these values in `.env` when your Compose project uses different names.

### 2. Ensure Knots accepts private-network RPC

Knots must bind RPC inside its container and allow connections from the Docker
network. Keep port `8332` private to Docker whenever possible; the dashboard
does not need it published on the host.

Use dedicated dashboard RPC credentials. Store the salted `rpcauth` value with
Knots and keep the corresponding plain-text password only in the dashboard's
Docker secret.

### 3. Start the dashboard

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f dashboard
```

Open `http://your-server:8335`.

## Building a release image

The current application version is stored in `VERSION`. Build metadata is
recorded as standard OCI image labels:

```bash
docker build \
  --build-arg APP_VERSION="$(cat VERSION)" \
  --build-arg VCS_REF="$(git rev-parse HEAD)" \
  --build-arg BUILD_DATE="$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --tag "docker-bitcoin-dashboard:$(cat VERSION)" \
  --tag docker-bitcoin-dashboard:latest \
  .
```

The Python base image is pinned by digest for repeatable builds. Update that
digest deliberately when incorporating upstream Python or Debian security
updates.

## Optional integrations

All optional integrations default to disabled. Disabled services are not
queried and their UI elements are hidden.

### Electrs

```env
ELECTRS_ENABLED=true
ELECTRS_METRICS_URL=http://electrs:4224
```

Electrs must share a Docker network with the dashboard and expose Prometheus
metrics containing `electrs_index_height{type="tip"}`.

### Tor

```env
TOR_ENABLED=true
```

Tor status is derived from Knots' `getnetworkinfo` response. The dashboard
reports Tor as running when Knots says the onion network is reachable, and it
shows an onion address when Knots advertises one.

### Mempool explorer

```env
MEMPOOL_EXPLORER_ENABLED=true
MEMPOOL_EXPLORER_URL=http://your-server:8080
```

This enables the link from the mempool metric to a separate explorer. Bitcoin's
own mempool transaction count remains visible even when the explorer is
disabled.

### Host metrics

```env
HOST_METRICS_ENABLED=true
CPU_TEMP_PATH=/sys/class/thermal/thermal_zone0/temp
LOADAVG_PATH=/proc/loadavg
```

Only enable this when those paths expose the intended host data to the
container. No broad host filesystem or Docker socket mount is included by
default.

### Disk warning

Set `DISK_MONITOR_PATH` to a path mounted into the dashboard container and set
`DISK_WARNING_FREE_GB` to the desired threshold. Knots' own blockchain size is
always obtained over RPC and does not require a filesystem mount.

## Main configuration

| Variable | Default | Purpose |
|---|---|---|
| `BITCOIN_RPC_URL` | `http://bitcoin-knots:8332` | Knots RPC endpoint |
| `BITCOIN_RPC_USER` | required | Dedicated RPC username |
| `BITCOIN_RPC_PASSWORD_FILE` | `/run/secrets/bitcoin_rpc_password` | Secret inside the container |
| `BITCOIN_DOCKER_NETWORK` | `bitcoinknots_default` | Existing Docker network name |
| `DASHBOARD_IMAGE` | `docker-bitcoin-dashboard` | Image repository used by Compose |
| `DASHBOARD_IMAGE_TAG` | `local` | Image tag used by Compose |
| `DASHBOARD_BIND_ADDRESS` | `0.0.0.0` | Published host address |
| `DASHBOARD_PORT` | `8335` | Published dashboard port |
| `NODE_NAME` | `bitcoin-knots` | Name displayed in the UI |
| `REFRESH_INTERVAL_SECONDS` | `30` | Backend cache refresh interval |

See `.env.example` for all optional settings.

## Endpoints

- `/api/status` — cached node, integration, and feature data
- `/healthz` — dashboard process liveness
- `/readyz` — returns HTTP 200 only after successful Knots RPC collection

## Development and tests

The application requires Python 3.8 or newer and has no third-party Python
dependencies.

```bash
python3 -m unittest discover -s tests -v
node --check app.js
docker compose config
docker build -t docker-bitcoin-dashboard:test .
```

## Security notes

- Never commit `.env`, RPC passwords, cookie files, or populated examples.
- Do not publish Knots RPC port `8332` to untrusted networks.
- Use a dedicated RPC identity and restrict its allowed methods where supported.
- Keep the dashboard behind a trusted LAN, VPN, or authenticated reverse proxy.
- The container runs as an unprivileged user with all Linux capabilities
  dropped and a read-only root filesystem.

## License

MIT
