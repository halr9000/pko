# pko — Pinokio CLI

**Vision**: Automate Pinokio from anywhere. Enable agentic operations regardless of where the agent runs — local machine, remote server, or CI pipeline.

## Architecture Decision: Python

**Chosen: Python** (via `uv`/`uvx`)

| Factor | Python | TypeScript/Node |
|--------|--------|-----------------|
| Agent-native tooling | Hermes, Codex, Claude Code are all Python-native | Requires Node runtime |
| Zero-install | `uvx pko` (faster, more reliable) | `npx pko` (slower, npm overhead) |
| HTTP client | `httpx` — async, HTTP/2, connection pooling | `fetch`/`axios` — fine |
| WebSocket | `websockets` library — mature, stable | `ws` — also fine |
| CLI framework | `typer` + `rich` — beautiful output | `commander` + `ink` — also fine |
| Codebase coupling | No shared code with pinokiod (Node.js) | Would share nothing anyway |
| **Winner** | **✓** | |

**Key insight**: The CLI is a *client* to pinokiod's HTTP + WebSocket APIs. There's no tight integration that benefits from sharing Node.js with the pinokiod server. Python's agent ecosystem (Hermes, Codex, Claude Code all speak Python tooling natively) is the deciding factor.

## API Surface Grouped by Phase

### Phase 1 — App Lifecycle (Core)

| Operation | pinokiod API | Method |
|-----------|-------------|--------|
| List installed apps | Read `~/pinokio/api/` directory | `GET /pinokio/fs?drive=api&path=/` |
| Install app from git | `POST /pinokio/fs` (git clone) | HTTP POST multipart |
| Start app | WebSocket `{uri: ..., mode: "run"}` | WS → `kernel.api.process()` |
| Stop app | WebSocket `{method: "kernel.api.stop", params: {uri}}` | WS → `kernel.api.stop()` |
| Delete app | `POST /pinokio/delete` | HTTP POST |
| Check app status | WebSocket `{uri: ..., status: true}` | WS → `kernel.api.running` |
| App info / metadata | Read `pinokio.js` from app dir | `GET /pinokio/fs?drive=api&path=app/index.json` |
| List running apps | Read `kernel.api.running` | WS → status check |
| Disk usage | `GET /du/:name` | HTTP GET |

### Phase 2 — Config & Environment

| Operation | pinokiod API | Method |
|-----------|-------------|--------|
| Get global config | Read `~/pinokio/ENVIRONMENT` | `GET /pinokio/fs?drive=api&path=../ENVIRONMENT` |
| Set config var | Write to `ENVIRONMENT` | `POST /pinokio/fs` (write) |
| System info | `GET /pinokio/info` | HTTP GET |
| App env vars | Read `~/pinokio/api/<app>/ENVIRONMENT` | `GET /pinokio/fs?drive=api&path=<app>/ENVIRONMENT` |
| Port management | `GET /pinokio/port` | HTTP GET |
| Restart server | `POST /restart` | HTTP POST |
| Health check | `GET /check` | HTTP GET |
| Logs | `GET /getlog?logpath=...` | HTTP GET |
| Proxy management | `GET /proxy`, `POST /proxy` | HTTP GET/POST |
| Cloudflare tunnel | `POST /publish`, `POST /unpublish` | HTTP POST |

### Phase 3 — Community & Discover

| Operation | pinokiod API | Method |
|-----------|-------------|--------|
| Discover apps | `https://beta.pinokio.co` (external) | HTTP GET (external) |
| Install from community | Git clone from GitHub | Git via HTTP |
| Search community apps | GitHub API / beta.pinokio.co | External |
| App notifications | Community platform | Future |

## Architecture

```
pko/
├── src/pko/
│   ├── __init__.py          # Version, exports
│   ├── __main__.py          # `python -m pko` entry
│   ├── main.py              # Typer CLI app
│   ├── client.py            # HTTP + WebSocket client to pinokiod
│   ├── discover.py          # Instance discovery (local + remote)
│   ├── config.py            # pko config (profiles, connections)
│   ├── models.py            # Data models / types
│   ├── app.py               # App lifecycle operations
│   ├── system.py            # System/config operations
│   ├── community.py         # Community/discover operations
│   └── ws.py                # WebSocket session management
├── skills/
│   ├── pko-install.md       # Agent skill: install an app
│   ├── pko-start.md         # Agent skill: start/stop apps
│   └── pko-discover.md      # Agent skill: search & discover apps
├── AGENTS.md                # Agent entry point (Hermes/Codex/Claude Code)
├── pyproject.toml            # Build config
├── README.md                # User docs
└── PLAN.md                  # This file
```

## Quick Start

### CLI
```bash
# Zero-install (recommended)
uvx pko discover
uvx pko list
uvx pko install comfyui --from pinokiocomputer/ComfyUI

# Connect to remote
uvx pko connect remote.local:42000
uvx pko --host 192.168.1.50:42000 list
```

### Agent Skills
```bash
# Install via npx skills ecosystem
npx skills add path/to/pko --skill pko-discover
npx skills add path/to/pko --skill pko-install
npx skills add path/to/pko --skill pko-start

# Once published to GitHub
npx skills add owner/pko
```

## Upstream Contribution Strategy

To make pko easy to maintain as pinokiod evolves:

1. **OpenAPI spec PR to pinokiod** — If an OpenAPI spec doesn't exist yet, we can contribute one. The HTTP endpoints are well-defined Express routes. The WebSocket protocol is well-documented in the codebase. Having an OpenAPI spec would let us auto-generate the client layer.

2. **Pinokio.js schema PR** — The pinokio.js script format deserves a formal JSON Schema. This would let us validate scripts and eventually auto-generate launcher templates from the CLI.

3. **Discovery mechanism PR** — Add mDNS/Bonjour or a simple advertised endpoint so `pko discover` can find instances on the local network without manual config.

## Design Principles

- **Minimal deps**: `typer`, `httpx`, `websockets`, `rich` — 4 core dependencies
- **Async-first**: httpx async client + websockets async for streaming
- **Composable**: Each command is a small function that can be called programmatically by agents
- **Discoverable**: `pko discover` scans common ports, `pko connect` for manual config
- **Documented**: AGENTS.md + skills/ for agent consumption, README for humans

## Installing Pinokio (for dev/testing)

`pinokiod` is an npm package — no Electron/AppImage needed for headless operation.

```bash
npm install -g pinokiod --prefix ~/.local
mkdir -p ~/pinokio
```

### systemd user service

```ini
# ~/.config/systemd/user/pinokiod.service
[Unit]
Description=Pinokio Daemon (headless)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/node /home/user/.local/lib/node_modules/pinokiod/script/index.js
Restart=on-failure
RestartSec=5
Environment=NODE_ENV=production
Environment=PINOKIO_HOME=%h/pinokio
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
```

```bash
systemctl --user daemon-reload
systemctl --user enable --now pinokiod.service
```

## Testing

### Unit tests (no external deps)
```bash
uv run pytest tests/ -v -m "not integration"
```

### Integration tests (requires pinokiod)
```bash
# Local instance (default)
uv run pytest tests/ -v -m "integration"

# Remote instance
PKO_TEST_HOST=mando PKO_TEST_PORT=42000 uv run pytest tests/ -v -m "integration"
```

Tests marked `@pytest.mark.integration` auto-skip if the target is unreachable.

### Test findings (v0.1.0)

**All 41 tests pass (36 unit + 5 integration).**

Bugs discovered:
- **pinokiod #1**: `/pinokio/fs?drive=api&path=/` returns 500 on fresh install (tries to stat `/index.html` before homedir is fully initialized). pko handles this gracefully (returns `[]`).
- **pinokiod #2**: `/pinokio/info` shows empty `homedir` on fresh npm install. Server works but missing env setup.
- Both are upstream pinokiod quirks, not pko bugs.