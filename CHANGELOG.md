# Changelog

All notable changes to pko are documented here. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/); versioning follows
[SemVer](https://semver.org/) with the understanding that pre-1.0 minor bumps
may include breaking CLI changes.

## [0.3.0] - 2026-07-21

### Architecture
- Decomposed the 1000-line `main.py` monolith into focused modules: `app.py` (app lifecycle), `system.py` (system/config), `ui.py` (shared UI helpers). `main.py` is now a thin entry point that imports commands from submodules.
- Added `AppStatus` typed dataclass — `get_app_status()` now returns `AppStatus | None` instead of a raw `dict`.
- Added `run_client()` helper to `client.py` — shared async client lifecycle (create, health-check, handler, close) used by all commands.
- Removed dead code: `WsClient.check_status()` method and its tests (superseded by HTTP-based `get_app_status()`).

### Added
- `start <app>` — now functional! Runs an app's script via WebSocket and streams output to the console.
- `stop <app>` — now functional! Sends a stop command to a running app via WebSocket.
- `install <source>` — now functional! Clones a git repo into `~/pinokio/api/<name>/` for local instances; prints web UI instructions for remote instances.
- `pko start --script <name>` option to specify a custom script (default: `index.json`).
- `pko stop --script <name>` option for consistency with start.
- `pko start` and `pko stop` handle Ctrl+C gracefully (app continues running in background).
- `pko logs <app_name>` — canonical log viewer using `/apps/logs/:id` endpoint (same as `pterm logs`).
- `pko logs --list` / `-l` — enumerate available log files for all installed apps with line counts and timestamps.
- `pko logs --script <name>` / `-s` — specify which script's logs to view (default: `start.js`).
- `get_app_logs()` on `Client` — typed log retrieval returning structured dict with `text`, `lines`, `line_count`, `size`, `modified`.
- `--help` output now grouped into logical panels: System, Discovery, App Lifecycle — with `rich_help_panel` and `rich_markup_mode`.
- Full app lifecycle integration test (`test_app_lifecycle`) using pinokio-hello-world: start → verify running → stop → verify stopped.
- CLI-level integration tests (`TestLiveAppLifecycle`) for list, status --all, info against a live instance.
- README.md rewritten for two audiences (end users + developers) with hello-world examples, troubleshooting table, and agent integration docs.
- AGENTS.md cleaned up: removed phase column, sync'd command groups, validated `npx skills add halr9000/pko` syntax.

### Fixed
- `.githooks/pre-commit` now detects cross-OS venvs (e.g., Linux-originated venv on Windows) and skips gracefully instead of failing.
- Removed unused imports across all modules.
- `get_app_status()` returns typed `AppStatus` model instead of raw dict.
- `WsClient` now has `start_script_and_wait()` convenience method for programmatic use.
- `get_logs()` return type changed from `str` to `str | None` — properly distinguishes empty logs from missing files.
- `get_logs()` detects HTML error pages (pinokiod returns them with 200 status for missing files).
- `pko stop --script` help text corrected from "Script URI" to "Script to stop".
- Integration tests fail (not skip) when the target instance is unreachable — `pytest.fail` with clear env var hint.
- `test_app_lifecycle` handles already-running apps by stopping them first before the start cycle.

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
