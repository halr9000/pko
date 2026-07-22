# pko — Pinokio CLI

**Automate Pinokio from anywhere.** `pko` is a cross-platform CLI for managing Pinokio instances — install apps, start/stop them, check system info, and more — all from the terminal or an AI agent.

```bash
uvx pko discover           # Find Pinokio instances on your network
uvx pko list               # List installed apps
uvx pko status hello-world # Check if an app is running
```

> `uvx` runs a Python tool with zero install, via [uv](https://docs.astral.sh/uv/). See the [Quick Start](#quick-start).

---

# For End Users

## What is pko?

pko is a command-line tool that talks to a running Pinokio instance. If you use Pinokio's desktop app (the browser-based interface), pko gives you the same control from your terminal — useful for scripting, remote access over SSH, or when you don't want to open a browser.

## Prerequisites

- **Python 3.10+** with [uv](https://docs.astral.sh/uv/) (recommended) or pip
- A running Pinokio instance (default: `localhost:42000`)

New to uv? Install it:
```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

## Quick Start

### Zero-install (uv — no setup needed)

```bash
# Find Pinokio instances on your network
uvx pko discover

# Connect to one (saves it as your default)
uvx pko connect 192.168.1.50:42000

# List installed apps
uvx pko list

# Check system info
uvx pko info
```

### Install for repeated use

```bash
# With uv
uv tool install pko
pko discover

# With pip
pip install pko
pko discover
```

## Commands

### Finding and connecting

```bash
# Scan localhost for Pinokio instances
pko discover

# Scan a remote host
pko discover --host 192.168.1.50

# Save a server as default
pko connect 192.168.1.50:42000
pko connect 10.0.0.5:42000 --name secondary
```

### Managing apps

All examples use [pinokio-hello-world](https://github.com/halr9000/pinokio-hello-world) — a minimal Gradio app that's quick to install and test with.

```bash
# List installed apps
pko list

# Install an app from a git URL
pko install https://github.com/halr9000/pinokio-hello-world

# Check if an app is running
pko status hello-world

# See all apps' running/stopped state at once
pko status --all

# See app details (title, disk usage, running state)
pko inspect hello-world

# Start an app (streams its terminal output)
pko start hello-world

# Stop a running app
pko stop hello-world

# Delete an app
pko delete hello-world
```

### System

```bash
# System info (platform, version, GPU, memory)
pko info
pko info --json

# View configuration
pko config

# View logs (path depends on your instance; try listing the app's log dir first)
pko logs --path stdout.txt --tail 50

# Restart the server
pko restart
```

### Remote instances

Every command accepts `--host` and `--port`:

```bash
pko --host 192.168.1.50 list
pko --host 10.0.0.5 info
```

Or set environment variables:

```bash
export PKO_HOST=192.168.1.50
export PKO_PORT=42000
pko list
```

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `Cannot connect` | Pinokio not running | Start Pinokio, then try again |
| `No instances found` | Wrong host or offline | Check the host is on your network and Pinokio is running |
| Connection refused | Wrong port | Default is 42000, try `pko discover` to find the right one |

## Agent Integration

pko ships three agent skills for AI assistants (Hermes, Claude Code, Codex, etc.):

| Skill | File | Purpose |
|-------|------|---------|
| **pko-discover** | `skills/pko-discover.md` | Find & connect to Pinokio instances |
| **pko-install** | `skills/pko-install.md` | Install apps with pinokio.js reference |
| **pko-start** | `skills/pko-start.md` | Start/stop apps via WebSocket |

Install via `npx skills`:

```bash
npx skills add path/to/pko --skill pko-discover
npx skills add path/to/pko --skill pko-install
npx skills add path/to/pko --skill pko-start
```

Once published to GitHub:

```bash
npx skills add halr9000/pko
```

---

# For Developers

## Architecture

pko is a pure-Python CLI that wraps pinokiod's HTTP + WebSocket API:

```
┌─────────────┐     HTTP/WS      ┌──────────────┐
│   pko CLI   │ ────────────────→ │  pinokiod    │
│  (Python)   │ ←──────────────── │  (Node.js)   │
└─────────────┘    stream/result  └──────┬───────┘
                                         │
                                  ┌──────┴───────┐
                                  │  ~/pinokio/  │
                                  │  api/ bin/   │
                                  │  cache/ ENV  │
                                  └──────────────┘
```

### Project structure

```
pko/
├── src/pko/
│   ├── __init__.py          # Version
│   ├── __main__.py          # python -m pko
│   ├── main.py              # Typer CLI entry point
│   ├── app.py               # App lifecycle commands
│   ├── system.py            # System/config commands
│   ├── client.py            # HTTP + WebSocket client
│   ├── discover.py          # Instance discovery
│   ├── config.py            # Profile management
│   ├── models.py            # Data models
│   └── ui.py                # Shared UI helpers
├── skills/                  # Agent skills
│   ├── pko-discover.md
│   ├── pko-install.md
│   └── pko-start.md
├── tests/                   # Unit + integration tests
├── AGENTS.md                # Agent entry point
├── PLAN.md                  # Architecture & roadmap
└── pyproject.toml           # Build config
```

## Development

```bash
git clone https://github.com/halr9000/pko
cd pko
uv sync
uv run pko discover
```

### Running tests

```bash
uv run pytest                  # Unit tests only
uv run pytest -m integration   # Integration tests (needs live pinokiod)
```

Integration tests default to `localhost:42000`. Target a remote instance:

```bash
PKO_TEST_HOST=mando PKO_TEST_PORT=42000 uv run pytest -m integration
```

### Vendor file management

pko vendors upstream files from pinokiocomputer repos. Refresh with:

```bash
uv run python scripts/sync_vendor.py
```

A pre-commit hook can automate staleness checks — opt in once:

```bash
git config core.hooksPath .githooks
```

## Roadmap

### Phase 1 — Core ✅ Done
- Instance discovery (localhost + remote)
- Connection profiles (optional named profiles)
- App lifecycle: list, status, inspect, install, start, stop, delete
- System: info, config, logs, restart
- Agent skills + AGENTS.md

### Phase 2 — Config & Environment
- Config set (ENVIRONMENT file write)
- App env vars
- Logs viewer redesign (tree/follow/filter)
- Proxy management
- Cloudflare tunnel publish/unpublish
- Port management

### Phase 3 — Community & Discover
- Community search (beta.pinokio.co)
- Install from community
- App notifications
- Publish apps

### Phase 4 — Advanced
- Interactive prompt handling (app input)
- Shell session management
- OpenAPI spec contribution to pinokiod
- Pinokio.js JSON Schema contribution
- mDNS/Bonjour discovery contribution

## License

MIT