# Changelog

All notable changes to pko are documented here. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/); versioning follows
[SemVer](https://semver.org/) with the understanding that pre-1.0 minor bumps
may include breaking CLI changes.

## [0.2.0] - 2026-07-19

### Added
- `status --all` flag to show status for every installed app in a table
- Server-address preface (`── <profile-or-host:port> ──`) on all command output, to disambiguate local vs. remote responses
- `connect` now sets the new profile as the default automatically
- Bugfix-driven test coverage: 41 tests (36 unit + 5 integration against a live pinokiod)
- `docs/adr/ADR-LOG.md` — architecture decision records with primary-source citations (deepwiki + direct pinokiod/proto source inspection)
- `vendor/` — pko now vendors two upstream files verbatim (`pinokiod`'s own `SKILL_PINOKIO.md` agent skill, `proto`'s `AGENTS.md` app-authoring contract) via a manifest-driven sync script (`scripts/sync_vendor.py`), rather than duplicating their logic
- CI (`.github/workflows/ci.yml`) — pytest + vendor-freshness check on push/PR + weekly cron
- Local pre-commit hook (`.githooks/pre-commit`, opt-in) enforcing vendor freshness
- README.md "Sources" table and "Development" section

### Fixed
- `info`: `home` field was blank — pinokiod's API returns `home`, not `homedir`
- `info`: running-app count showed 0 instead of the actual count — pinokiod returns `scripts`, not `running`
- `status <app>` with a nonexistent app name now returns a proper error (exit 1) instead of a misleading "not running" warning
- `status`/`list` app-identity matching now uses the `path` field consistently (matches pinokiod's own `scripts[].app` references)
- `list_apps()` no longer crashes on pinokiod's known 500 response for an empty/fresh `api/` directory
- `--version` flag now works (`@app.callback(invoke_without_command=True)`)
- `[Not implemented]` suffix on stub commands (`install`, `start`, `stop`) — previously silently stripped by Rich console markup parsing unescaped `[...]`
- `uv` dev-dependency deprecation warning (`[tool.uv] dev-dependencies` → `[dependency-groups] dev`)

### Known limitations (tracked for 1.0)
- `install`, `start`, `stop` remain stubs — require WebSocket script execution, not yet implemented
- `create-app` (new launcher scaffolding) is designed (ADR-003) but not implemented
- `logs` command redesign is planned (ADR-002, phased) but not implemented — current `logs` is still the original thin `/getlog` wrapper

## [0.1.0] - 2026-07-19

Initial release. Python CLI wrapping pinokiod's HTTP/WebSocket API.

### Added
- 13 commands: `discover`, `connect`, `profile`, `list`, `info`, `status`, `install`* `start`* `stop`* `delete`, `config`, `logs`, `restart` (*stubs)
- HTTP client (`client.py`) covering health, info, list apps, read app metadata, delete, config, logs, restart, disk usage
- WebSocket client (`client.py` `WsClient`) for script run/stop/status (used by the stubs' design, not yet wired to commands)
- Instance discovery (`discover.py`) — local port scan + remote host scan
- Connection profile management (`config.py`) — `~/.config/pko/config.json`
- `AGENTS.md` + 3 `SKILL.md` agent skills (`pko-discover`, `pko-install`, `pko-start`), npx-skills-compatible format
- `PLAN.md` — architecture decisions, phased API rollout, upstream contribution strategy
- Packaged for `uv`/`uvx` zero-install use
