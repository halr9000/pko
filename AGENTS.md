# pko — Pinokio CLI

**Vision**: Automate Pinokio from anywhere. Enable agentic operations regardless of where the agent runs — local machine, remote server, or CI pipeline.

## Quick Start

```bash
# Zero-install (recommended)
uvx pko discover
uvx pko list
uvx pko info

# Or install via npx skills ecosystem
npx skills add path/to/pko --skill pko-discover
npx skills add path/to/pko --skill pko-install
npx skills add path/to/pko --skill pko-start

# Once published to GitHub
npx skills add owner/pko

# Connect to an instance
uvx pko connect 192.168.1.50:42000

# List installed apps
uvx pko list

# Check system info
uvx pko info

# Check app status
uvx pko status comfyui

# Rich metadata for one app
uvx pko inspect comfyui
```

## API Design

pko wraps the pinokiod HTTP + WebSocket API into a clean CLI. All commands accept `--host` and `--port` for targeting remote instances, or use the saved default host.

### Command Groups

| Command | Description | Phase |
|---------|-------------|-------|
| `discover` | Find Pinokio instances on localhost or remote host | 1 |
| `connect` | Save a known host:port and set it as default | 1 |
| `hosts` | List known Pinokio servers (host:port) | 1 |
| `list` | List installed apps | 1 |
| `info` | System information (diagnostics only) | 1 |
| `status` | Check if an app is running (`GET /apps/status/:id` for single app; `--all` lists everyone) | 1 |
| `inspect` | Rich per-app metadata: title, description, disk usage, running state | 1 |
| `config` | Get/set environment configuration | 2 |
| `logs` | View server logs | 2 |
| `restart` | Restart the server | 2 |
| `delete` | Delete an app or cache | 1 |
| `install` | Install an app from git | 1 |
| `start` | Start an app | 1 |
| `stop` | Stop an app | 1 |

## Architecture

```
pko/
├── src/pko/
│   ├── __init__.py       # Version
│   ├── __main__.py       # python -m pko
│   ├── main.py           # Typer CLI (all commands)
│   ├── client.py         # HTTP + WebSocket client
│   ├── discover.py       # Instance discovery (scan ports)
│   ├── config.py         # Profile/config management
│   └── models.py         # Data models
├── skills/               # Agent skills
│   ├── pko-install.md
│   ├── pko-start.md
│   └── pko-discover.md
├── AGENTS.md             # This file
├── README.md             # User documentation
├── PLAN.md               # Architecture & roadmap
└── pyproject.toml         # Build config
```

## Protocol Reference

### pinokiod HTTP API

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/check` | GET | Health check → `{success: true}` |
| `/pinokio/info` | GET | System info (platform, arch, memory, GPU, version) |
| `/apps/status/:id` | GET | Rich per-app status (running/ready state, title, description, icon, ready_url) — discovered via vendored pterm/util.js reference, see ADR-004/ADR-005 |
| `/pinokio/port` | GET | Get an available port → `{result: number}` |
| `/pinokio/fs?drive=api&path=/` | GET | List installed apps |
| `/pinokio/fs?drive=api&path=<name>/pinokio.js` | GET | Read app metadata |
| `/pinokio/fs?drive=api&path=../ENVIRONMENT` | GET | Read global config |
| `/pinokio/delete` | POST | Delete app/cache: `{type, name}` |
| `/restart` | POST | Restart server |
| `/getlog` | GET | View logs: `?logpath=...` |
| `/du/:name` | GET | Disk usage for app |

### pinokiod WebSocket Protocol

Messages are JSON with `{type, id, data, index}`:

| Type | Direction | Purpose |
|------|-----------|---------|
| `stream` | Server→Client | Terminal output / data stream |
| `result` | Server→Client | Step completion result |
| `event` | Server→Client | System events (stop, etc.) |
| `error` | Server→Client | Error messages |
| `start` | Server→Client | Script execution started |
| `connect` | Server→Client | Connection established |
| `disconnect` | Server→Client | Connection closed |
| `wait` | Server→Client | Waiting for user input |
| `input` | Server→Client | Requesting user input |
| `modal` | Server→Client | Display modal |
| `notify` | Server→Client | Desktop notification |

**Client sends** to run a script:
```json
{
  "uri": "/api/myapp/index.json",
  "mode": "run",
  "input": {},
  "client": {"cols": 80, "rows": 24}
}
```

**Client sends** to stop a script:
```json
{
  "method": "kernel.api.stop",
  "params": {"uri": "/api/myapp/index.json"}
}
```

## Common Patterns

### For agents managing Pinokio

1. **Discover first**: Always run `pko discover` to find instances before connecting
2. **Save known hosts**: Use `pko connect <host>:<port>` for repeatable connections
3. **Check health before operations**: `pko info` to verify the instance is responsive
4. **App lifecycle**: `pko list` → `pko status <app>` → `pko start <app>` or `pko stop <app>`
5. **Config changes**: Use `pko config` to read values; for writes, edit the ENVIRONMENT file

### For human users

- `uvx pko discover` — find instances
- `uvx pko connect localhost:42000` — save default host
- `uvx pko info` — check system
- `uvx pko list` — see installed apps
- `uvx pko config` — see environment variables

## Skills

See `skills/` directory for standard `SKILL.md` agent skills compatible with `npx skills`:

| Skill | Description | Install |
|-------|-------------|---------|
| `pko-discover` | Find & connect to Pinokio instances | `npx skills add path/to/pko --skill pko-discover` |
| `pko-install` | Install apps + pinokio.js reference | `npx skills add path/to/pko --skill pko-install` |
| `pko-start` | Start/stop apps + WebSocket protocol | `npx skills add path/to/pko --skill pko-start` |

Install all at once (once published to GitHub):
```bash
npx skills add owner/pko
```