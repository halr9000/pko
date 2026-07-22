# pko — Pinokio CLI

**Vision**: Automate Pinokio from anywhere. Enable agentic operations regardless of where the agent runs — local machine, remote server, or CI pipeline.

## Quick Start

```bash
# Zero-install
uvx pko discover
uvx pko list
uvx pko info

# Or install via npx skills ecosystem
npx skills add path/to/pko --skill pko-discover
npx skills add path/to/pko --skill pko-install
npx skills add path/to/pko --skill pko-start

# Once published to GitHub
npx skills add halr9000/pko

# Connect to an instance
uvx pko connect 192.168.1.50:42000

# List installed apps
uvx pko list

# Check system info
uvx pko info

# Check app status
uvx pko status hello-world

# Rich metadata for one app
uvx pko inspect hello-world

# Install, start, stop
uvx pko install https://github.com/halr9000/pinokio-hello-world
uvx pko start hello-world
uvx pko stop hello-world
```

## Commands

| Command | Description |
|---------|-------------|
| `discover` | Find Pinokio instances on localhost or remote host |
| `connect` | Save a connection profile (name optional, defaults to "default") |
| `profile` | Manage connection profiles |
| `list` | List installed apps |
| `status` | Check if an app is running |
| `inspect` | Rich per-app metadata: title, description, disk usage, running state |
| `start` | Start an app via WebSocket |
| `stop` | Stop a running app via WebSocket |
| `install` | Install an app from git |
| `delete` | Delete an app or cache |
| `config` | Get/set environment configuration |
| `logs` | View server logs |
| `restart` | Restart the server |
| `info` | System information (diagnostics only) |

## Architecture

```
pko/
├── src/pko/
│   ├── __init__.py       # Version
│   ├── __main__.py       # python -m pko
│   ├── main.py           # Typer CLI entry point (imports from submodules)
│   ├── app.py            # App lifecycle commands (list, status, start, stop, install, delete, inspect)
│   ├── system.py         # System/config commands (info, config, logs, restart)
│   ├── client.py         # HTTP + WebSocket client + run_client helper
│   ├── discover.py       # Instance discovery (scan ports)
│   ├── config.py         # Profile/config management
│   ├── models.py         # Data models (AppStatus, AppInfo, SystemInfo, WsPacket)
│   └── ui.py             # Shared UI helpers (console, print_ok, print_error)
├── skills/               # Agent skills
│   ├── pko-discover.md
│   ├── pko-install.md
│   └── pko-start.md
├── tests/                # Unit + integration tests
├── AGENTS.md             # This file
├── README.md             # User documentation
├── PLAN.md               # Architecture & roadmap
└── pyproject.toml         # Build config
```

## Common Patterns

### For agents

1. **Discover first** — Always run `pko discover` to find instances before connecting
2. **Save known hosts** — Use `pko connect <host>:<port>` for repeatable connections (name is optional)
3. **Check health before operations** — `pko info` to verify the instance is responsive
4. **App lifecycle** — `pko list` → `pko status <app>` → `pko start <app>` or `pko stop <app>`
5. **Install from git** — `pko install https://github.com/<owner>/<repo>` for local instances
6. **Logs** — `pko logs --path stdout.txt --tail 50` (path varies by instance)

### For humans

- `uvx pko discover` — find instances
- `uvx pko connect localhost:42000` — save default host
- `uvx pko list` — see installed apps
- `uvx pko start hello-world` — start an app
- `uvx pko stop hello-world` — stop an app
- `uvx pko info` — check system
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
npx skills add halr9000/pko
```