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
| Logs | `GET /getlog?logpath=...` (legacy) + `GET /api/logs/tree`, `GET /api/logs/stream`, `GET /pinokio/logs/file` (see ADR-002) | HTTP GET / SSE |
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

## Logs Command Redesign (ADR-002)

Full research and rationale: `docs/adr/ADR-LOG.md` (ADR-002). Summary below —
read the ADR before touching `logs` code, it has the endpoint contracts and
verified example responses.

### Endpoints in play

| Endpoint | Purpose | Notes |
|---|---|---|
| `GET /api/logs/tree?workspace=<app>&path=<subpath>` | List logs (discovery) | Omit `workspace` for server-level tree |
| `GET /api/logs/stream?workspace=<app>&path=<relpath>` | Follow/tail (SSE) | `snapshot` event then `chunk` events; 2s keep-alive |
| `GET /pinokio/logs/file?workspace=<app>&path=<relpath>&tail_lines=N` | Read a top-level text log | Rejects nested per-script files (400) |
| `GET /getlog?logpath=<absolute path>` | Legacy fallback read | No tail/follow; needed for files `/pinokio/logs/file` rejects (e.g. `api/<script>.js/events`) |
| `POST /pinokio/log` + `GET /pinokio/logs.zip` | Full redacted archive | "download everything" escape hatch, keep as `--zip` flag |

### On-disk log layout (confirmed live)

```
<PINOKIO_HOME>/logs/                          # server-level
├── stdout.txt                                # global stdout/stderr (may be absent — see ADR)
├── system.json                                # periodic system/process snapshot
├── shell/                                     # pinokiod-managed root shell (e.g. caddy)
└── caddy.log, caddy-<ts>.log                  # bundled reverse proxy logs

<PINOKIO_HOME>/api/<app>/logs/                # per-app
├── sessions/index.json                        # session index, ended_at:null = still running
├── sessions/<id>.json                          # one session record (which scripts ran, when)
└── api/<script>.js/
    ├── <timestamp>                             # one transcript per execution
    ├── latest                                  # most recent transcript
    └── events                                  # structured step-lifecycle log, ISO timestamps
```

### Phased implementation

**Phase A — discovery & basic read (blocks everything else)**
1. `client.py`: add `list_log_tree(workspace: str | None, path: str = "") -> dict` wrapping `/api/logs/tree`
2. `client.py`: add `read_log_file(workspace, path, tail_lines=None) -> dict` wrapping `/pinokio/logs/file`, falling back to `/getlog` with the resolved absolute path when the server rejects a nested path (400)
3. `main.py`: `pko logs --list [APP]` — render the tree as a table (name, type, size, modified)
4. `main.py`: `pko logs [APP]` — default to reading `api/<most-recent-script>.js/latest` for an app (resolve "most recent script" from `sessions/index.json`'s `latest_session`), or `logs/stdout.txt` for `--server`/no-APP
5. Tests: mock `httpx` responses for tree + file read, plus one integration test hitting the live instance's real tree

**Phase B — follow (SSE)**
6. `client.py`: add `stream_log(workspace, path) -> AsyncIterator[dict]` using `httpx.AsyncClient.stream("GET", ...)`, parsing `event:`/`data:` SSE framing, yielding `{"event": "snapshot"|"chunk"|"server-error", "data": {...}}`
7. `main.py`: `--follow`/`-f` flag — print `snapshot` then stream `chunk` events to console until Ctrl+C
8. Tests: mock an SSE byte stream, assert snapshot + chunk parsing

**Phase C — filtering (best-effort, document as approximate)**
9. `--lines N`/`-n` — pass `tail_lines` where the endpoint supports it, else slice client-side
10. `--search TEXT` — client-side substring/regex filter applied to fetched/streamed lines
11. `--level LEVEL` — heuristic filter matching common ERROR/WARN/INFO markers (no native pinokiod taxonomy — must say so in `--help`)
12. `--since DURATION` — file-mtime filter for tree listing; line-timestamp filter for `events`-format files only

**Phase D — polish**
13. `--zip` — trigger `POST /pinokio/log` + report the download URL (mirrors Desktop's "Debug" button)
14. Update `AGENTS.md`/skills with the new logs usage patterns for the three user stories in ADR-002
15. Update README command table + `pko logs --help`

### Breaking change note
The old `pko logs --path PATH --tail N` interface (single flat `/getlog` call)
is fully superseded. Acceptable pre-1.0 — no back-compat shim planned.