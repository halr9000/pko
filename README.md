# pko — Pinokio CLI

**Automate Pinokio from anywhere.** `pko` is a cross-platform CLI for managing Pinokio instances — install apps, start/stop them, check system info, and more — all from the terminal or an AI agent.

```bash
uvx pko discover           # Find Pinokio instances on your network
uvx pko list               # List installed apps
uvx pko info               # System information
uvx pko status comfyui     # Check if an app is running
```

> `uvx` runs a Python tool with zero install, via [uv](https://docs.astral.sh/uv/) — see [Prerequisites](#prerequisites) below if you don't have it yet (or use the pip equivalents throughout this doc).

## Why pko?

| Feature | What it does |
|---------|-------------|
| 🖥️ **Local & Remote** | Connect to any Pinokio instance, not just localhost |
| 🔍 **Auto-discovery** | Scan well-known ports to find instances |
| 🔌 **Zero install** | Run with `uvx pko` — no setup needed |
| 🤖 **Agent-ready** | AGENTS.md + skills/ for Hermes, Codex, Claude Code |
| 📦 **Minimal deps** | Just Python + uv |
| 🔄 **Lifecycle mgmt** | Install, start, stop, delete, list, status |

## Quick Start

### Prerequisites

- **Python 3.10+** with [uv](https://docs.astral.sh/uv/) (recommended) or pip. New to uv? It's a fast Python package/tool manager from Astral — install it with `curl -LsSf https://astral.sh/uv/install.sh | sh` (macOS/Linux) or `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"` (Windows), or see the [official install guide](https://docs.astral.sh/uv/getting-started/installation/) for other methods (Homebrew, pipx, etc). No uv? Every command below has a pip fallback.
- A running Pinokio instance (default: `localhost:42000`)

### Zero-install (uv)

```bash
# Discover instances
uvx pko discover

# Connect to a remote instance
uvx pko connect 192.168.1.50:42000

# List installed apps
uvx pko list

# Check system info
uvx pko info

# Check app status
uvx pko status comfyui
```

### Install with uv

```bash
uv tool install pko
pko discover
```

### Install with pip

```bash
pip install pko
pko discover
```

### Install as Agent Skills (npx skills)

The skills in `skills/` follow the [standard SKILL.md format](https://agentskills.io) and can be installed with the `npx skills` CLI:

```bash
# Install individual skills from local path
npx skills add path/to/pko --skill pko-discover
npx skills add path/to/pko --skill pko-install
npx skills add path/to/pko --skill pko-start

# Once published to GitHub
npx skills add owner/pko
```

This installs the skills to your agent's skill directory (e.g., `~/.hermes/skills/` for Hermes Agent, `~/.claude/skills/` for Claude Code). The `npx skills` CLI supports 70+ agents including Hermes, OpenClaw, Claude Code, Codex, Cursor, and more.

## Sources

Reference material for pinokiod's API/protocol and app-authoring conventions. When
asked to "check sources," use `deepwiki` (`ask_question`/`read_wiki_contents`)
against these repos, or `web_extract`/`browser` for the docs site — don't re-derive
from scratch.

| Source | What it is |
|---|---|
| [`pinokiocomputer/pinokio`](https://github.com/pinokiocomputer/pinokio) | Electron desktop app — GUI, install flow, discover/community integration |
| [`pinokiocomputer/pinokiod`](https://github.com/pinokiocomputer/pinokiod) | The actual server daemon pko talks to — HTTP/WS API, logging, kernel |
| [`pinokiocomputer/proto`](https://github.com/pinokiocomputer/proto) | Project scaffolding + `AGENTS.md` template used to bootstrap new Pinokio launcher projects (app-authoring conventions, not pko itself) |
| [`pinokiocomputer/home`](https://github.com/pinokiocomputer/home) | Pinokio's canonical docs site source (`docs/README.md` = the `PINOKIO.md` referenced by `proto`'s AGENTS.md). Covers the platform overview, auto-launch, app **orchestration**/dependency graphs (`PINOKIO_SCRIPT_REQUIRES`), and the built-in **Agent Interpreter** layer (`~/.agents/skills`, agent-facing app discovery) — directly relevant to pko's agent-skills goals. Not indexed by deepwiki as of ADR-002; re-check indexing status before falling back to raw `web_extract` of `docs/README.md` |
| [Pinokio Desktop Manual](https://desktop.pinokio.co/docs/#/) | End-user docs for the desktop app — overview/TOC only, no orchestrator API detail |
| `docs/adr/ADR-LOG.md` (this repo) | Our own research notes/decisions distilled from the above, with citations |

### Vendored files

pko vendors two upstream files verbatim (see ADR-003) rather than duplicating
their logic: `vendor/pinokiod/SKILL_PINOKIO.md` (Pinokio's own agent skill for
single-instance runtime control) and `vendor/proto/AGENTS.md` (the
app-authoring contract, design source for `pko create-app`). Refresh with
`uv run python scripts/sync_vendor.py`; check staleness with `--check`. Never
hand-edit files under `vendor/` — see `vendor/manifest.json`.

## Commands

### Instance Discovery

```bash
# Scan localhost
pko discover

# Scan a remote host
pko discover --host 192.168.1.50

# Connect and save as default host
pko connect localhost:42000
pko connect 10.0.0.5:42000 --name secondary

# Manage profiles (rarely needed — connect already sets the default)
pko profile                    # List all
pko profile secondary          # Show details
pko profile secondary --delete # Remove
pko profile secondary --default # Set as default
```

### App Lifecycle

```bash
# List installed apps
pko list

# Check if an app is running (uses a lightweight WebSocket probe)
pko status comfyui

# Show all apps' running/stopped state at once
pko status --all

# Rich metadata for one app (title, description, disk usage, running state)
pko inspect comfyui

# Delete an app
pko delete comfyui

# Restart the server
pko restart
```

### System & Config

```bash
# System information (diagnostics only — platform, arch, version, GPU, memory)
pko info
pko info --json               # JSON output

# View configuration
pko config                    # All env vars
pko config PINOKIO_SHARE_PASSCODE  # Single key

# View logs
pko logs
pko logs --tail 100
```

### Remote Instances

All commands accept `--host` and `--port`:

```bash
pko --host 192.168.1.50 --port 42000 list
pko --host 10.0.0.5 info
```

Or use environment variables:

```bash
export PKO_HOST=192.168.1.50
export PKO_PORT=42000
pko list
```

## Architecture

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

pko wraps pinokiod's HTTP + WebSocket API into a clean CLI interface. It talks to the same local server that the Pinokio desktop app uses.

## API Reference

### HTTP Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/check` | GET | Health check |
| `/pinokio/info` | GET | System information |
| `/apps/status/:id` | GET | Rich per-app status (running, ready_url, title, description) |
| `/pinokio/port` | GET | Available port |
| `/pinokio/fs` | GET | List/read files |
| `/pinokio/delete` | POST | Delete app/cache |
| `/restart` | POST | Restart server |
| `/getlog` | GET | View logs |
| `/du/:name` | GET | Disk usage |

### WebSocket Protocol

Connect to `ws://host:port` and send JSON:

```json
// Run a script
{"uri": "/api/myapp/index.json", "mode": "run", "input": {}}

// Stop a script
{"method": "kernel.api.stop", "params": {"uri": "/api/myapp/index.json"}}

// Check status
{"uri": "/api/myapp/index.json", "status": true}
```

## Agent Integration

pko ships with agent skills for AI assistants:

- **skills/pko-discover.md** — Finding and connecting to instances
- **skills/pko-install.md** — Installing apps with pinokio.js reference
- **skills/pko-start.md** — Starting/stopping apps with WebSocket protocol

The AGENTS.md file at the project root is the entry point for Hermes, Codex, and Claude Code agents.

## Development

```bash
git clone https://github.com/halr9000/pko
cd pko
uv sync
uv run pko discover
```

### Running tests

```bash
uv run pytest
```

### Enforcing vendor freshness

Vendored upstream files (see "Vendored files" above) can silently drift —
nothing breaks locally when pinokiod/proto change upstream, so staleness has
to be actively checked. Two layers catch this:

1. **Pre-commit hook (local, opt-in)** — `.githooks/pre-commit` runs
   `scripts/sync_vendor.py --check` before every commit and blocks it if
   vendor files are stale. Not enabled by default (git doesn't auto-discover
   hooks outside `.git/hooks/`); opt in once per clone:
   ```bash
   git config core.hooksPath .githooks
   ```
   Requires network (calls the GitHub API to resolve latest upstream SHAs;
   no content is downloaded for `--check`). Offline commits: `git commit --no-verify`.

2. **CI (`.github/workflows/ci.yml`)** — runs `sync_vendor.py --check` on
   every push/PR, plus a weekly cron (Mondays) so drift surfaces even when
   nobody touches the repo for a while. This is the backstop for anyone who
   didn't opt into the local hook.

Neither layer auto-fixes anything — both only *detect* staleness. Refreshing
is always a manual, reviewed step: `uv run python scripts/sync_vendor.py`,
then read the diff before committing (upstream skill/AGENTS.md content
changes can be substantive, not just typo fixes).

### Project Structure

```
pko/
├── src/pko/
│   ├── __init__.py       # Version
│   ├── __main__.py       # python -m pko
│   ├── main.py           # CLI commands
│   ├── client.py         # HTTP + WebSocket client
│   ├── discover.py       # Instance discovery
│   ├── config.py         # Profile management
│   └── models.py         # Data models
├── skills/               # Agent skills
├── AGENTS.md             # Agent entry point
├── PLAN.md               # Architecture & roadmap
└── pyproject.toml         # Build config
```

## Roadmap

### Phase 1 — Core ✅ Done
- ✅ Instance discovery (localhost + remote)
- ✅ Connection profiles (optional name, defaults to "default")
- ✅ List installed apps
- ✅ System info
- ✅ App status check
- ✅ Health check
- ✅ Delete app
- ✅ Server restart
- ✅ AGENTS.md + skills/

### Phase 2 — Config & Environment
- ⬜ Config get/set (ENVIRONMENT file)
- ⬜ App env vars
- ⬜ Logs viewer
- ⬜ Proxy management
- ⬜ Cloudflare tunnel publish/unpublish
- ⬜ Disk usage
- ⬜ Port management

### Phase 3 — Community & Discover
- ⬜ Community search (beta.pinokio.co)
- ⬜ Install from community
- ⬜ App notifications
- ⬜ Publish apps

### Phase 4 — Advanced
- ⬜ WebSocket script execution (start/stop/stream)
- ⬜ Interactive prompt handling
- ⬜ Shell session management
- ⬜ OpenAPI spec contribution to pinokiod
- ⬜ Pinokio.js JSON Schema contribution
- ⬜ mDNS/Bonjour discovery contribution

## Upstream Contributions

To keep pko easy to maintain, we plan to contribute back to the Pinokio ecosystem:

1. **OpenAPI spec** — Contribute an OpenAPI specification for pinokiod's HTTP API
2. **Pinokio.js JSON Schema** — Formalize the launcher format with a JSON Schema
3. **Discovery mechanism** — Add mDNS/Bonjour or simple advertised endpoint

## License

MIT
