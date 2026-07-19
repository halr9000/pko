# Architecture Decision Records — pko

This log captures significant design decisions for `pko`, with the research/evidence
that drove them. Newest entries at the top.

Sources cited inline use short refs — see README.md "Sources" section for the full
list and how to re-query them via deepwiki.

---

## ADR-002: Logs command redesign (2026-07-19)

### Status
Accepted

### Context

The original `pko logs` command was a thin wrapper around pinokiod's legacy
`GET /getlog?logpath=...` endpoint — it required the caller to already know an
exact absolute file path, had no discovery, no follow/tail, no filtering, and
provided no way to reason about *which* logs matter for a given troubleshooting
question. This makes it nearly useless for both human and agent users.

Investigated pinokiod's actual logging architecture via `deepwiki` (`pinokiod`,
`pinokio`, `proto` repos) and direct source inspection of the running npm
package (`~/.local/lib/node_modules/pinokiod/server/index.js`,
`server/socket.js`, `server/lib/log_redaction.js`) plus a live instance's
on-disk log tree for an installed app (`pinokio-hello-world.git`).

### Research summary

**Where pinokiod actually writes logs** (confirmed via source + live inspection):

1. **Server-level logs** — `<PINOKIO_HOME>/logs/`
   - `stdout.txt` — global stdout/stderr redirect for the whole pinokiod
     process, written by `startLogging()` (`server/index.js:5553`). Only
     active when `home` is resolved from `kernel.store` or `PINOKIO_HOME`;
     truncated to the last 100,000 lines every 10 minutes. **Not present**
     on our dev instance (npm-installed, no `home` resolved through that
     particular code path) — this itself is a discoverable gap `pko` should
     surface, not silently swallow.
   - `system.json` — periodic system/process snapshot (platform, running
     scripts, shells, proxies, apps) — effectively a point-in-time dump of
     what `/pinokio/info` returns.
   - `shell/` — raw + cleaned buffers for the pinokiod-managed root shell
     (e.g. the `caddy run --watch` reverse proxy process), separate from any
     app.
   - `caddy.log`, `caddy-<timestamp>.log` — the bundled Caddy reverse proxy's
     own logs (HTTP access-log style), rotated with timestamp suffixes.

2. **Per-app logs** — `<PINOKIO_HOME>/api/<app>/logs/`
   - `api/<script>.js/<timestamp>` — one file per execution of a script
     (`install.js`, `start.js`, etc.), containing the raw shell session
     transcript with `[shell shell]` header, ANSI-stripped.
   - `api/<script>.js/latest` — symlink/copy of the most recent execution's
     transcript. **This is the single best "what happened last time I ran
     this" file.**
   - `api/<script>.js/events` — structured `TIMESTAMP [tag] message` lines
     covering script step lifecycle (`memory` = step state snapshots incl.
     step index/global/local vars/port; `api local.set` = variable
     assignment traces, etc.). This is the closest thing to a leveled
     event log pinokiod produces for a script run, though it has no
     info/warn/error taxonomy — severity has to be inferred from content
     (e.g. presence of "Error", "Traceback", non-zero exit indicators).
   - `sessions/index.json` + `sessions/<id>.json` — one JSON record per
     *session* (an install+start sequence or a single run), listing which
     scripts ran, when they started/ended, and pointers to the specific
     transcript files under `api/<script>.js/<timestamp>`. `ended_at: null`
     while a script is still running — this is the most reliable "is this
     currently active" signal available from the filesystem alone, and it
     matches what `pko status` already derives from `/pinokio/info`'s
     `scripts` array over HTTP.

3. **Discovery & streaming endpoints** (all confirmed live against
   `localhost:42000`):
   - `GET /api/logs/tree?workspace=<app>&path=<subpath>` — directory
     listing (name, path, type, size, modified) rooted at either the
     top-level `<PINOKIO_HOME>/logs` (no `workspace`) or an app's
     `<PINOKIO_HOME>/api/<app>/logs` (with `workspace=<app>`). This is the
     **list available logs** primitive pko needs — no such capability
     existed in the old `pko logs` implementation.
   - `GET /pinokio/logs/file?workspace=<app>&path=<relpath>&tail_lines=N` —
     read a specific log file, with an optional server-side tail. Restricted
     to "top-level redactable" text files (see `isTopLevelRedactableLogPath`
     in `log_redaction.js`) — verified that arbitrary nested files like
     `api/start.js/events` are **rejected** (`400 Only top-level text log
     files can be read for redaction`), so pko cannot rely on this endpoint
     alone for per-script files; those still need the legacy `/getlog` or a
     direct filesystem read via `/pinokio/fs`.
   - `GET /api/logs/stream?workspace=<app>&path=<relpath>` — **true
     Server-Sent Events (SSE) follow/tail.** Sends an initial `snapshot`
     event with the last ~N bytes, then live `chunk` events as new data is
     appended, with periodic `: keep-alive` comments and a 2000ms retry
     hint. This is the correct primitive for `--follow`.
   - `GET /getlog?logpath=<absolute path>` — the legacy endpoint the old
     `pko logs` used. Still functional, requires an absolute filesystem
     path (no traversal protection beyond what the OS provides), no tail/
     follow support. Useful as a fallback for files `/pinokio/logs/file`
     rejects.
   - `POST /pinokio/log` (+ `GET /pinokio/logs.zip`) — generates a
     redacted zip archive of **all** logs (server + every installed app).
     This is the Pinokio Desktop "Debug → Download logs.zip" flow — good
     for "attach everything for a bug report" but too coarse for day-to-day
     troubleshooting.

4. **What the Desktop app itself does** (via deepwiki on `pinokiocomputer/pinokio`):
   confirmed the Electron shell has **no** follow/tail, search, or level-filter
   UI of its own for logs — it shows `stdout.txt` path on a startup-error
   splash screen, and separately captures a size-capped `browser.log` (last
   100 console messages) when `PINOKIO_BROWSER_LOG=1`. All of the richer
   discovery/tail/redaction functionality found above (`/api/logs/tree`,
   `/api/logs/stream`, `/pinokio/logs/file`) lives in `pinokiod`'s own web UI
   (`server/public/logs.js`, `logs-top-redaction.js`), which is served
   separately from the Electron desktop chrome. **This means pko's new logs
   command is filling a real gap** — even Pinokio's own desktop app doesn't
   give users a good CLI-equivalent experience; the good tooling exists
   server-side but has no non-browser client today.

5. **`pinokiocomputer/home`** — **CORRECTION (2026-07-19, later same day):** this repo
   is valid and highly relevant; the earlier "repository not found" note below was
   wrong — deepwiki simply hadn't indexed it yet (an indexing job was submitted and a
   retry is scheduled). Confirmed live via direct `web_extract` of
   `docs/README.md` on the `main` branch. This is Pinokio's canonical docs source —
   the very `PINOKIO.md` that `proto`'s `AGENTS.md` repeatedly points app authors to
   for API syntax. Contents relevant to pko:
   - **§4 Orchestration** — apps declare dependencies via
     `PINOKIO_SCRIPT_REQUIRES=<app1>,<app2>` in their `ENVIRONMENT` file. Launching
     an app recursively resolves and starts its dependency graph first, waiting for
     each to reach a "ready" state (the same readiness signal used by the `ready()`
     script API) before continuing. This means **`pko start <app>` cannot assume a
     single script execution** — it may need to observe/wait on a chain of
     dependent app launches. Relevant to the *stub* `start`/`stop` implementation
     work, not directly to the logs redesign, but should inform Phase (post-logs)
     planning for those commands.
   - **§5 Agent Interpreter** — Pinokio ships a *built-in* agent-facing layer:
     auto-generated `SKILL.md` files under `~/.agents/skills` for every installed
     app, standard discovery, auto-start-if-not-running, and reusable generated
     clients. This is conceptually adjacent to (and possibly overlapping with) pko's
     own "Built for agents (agent skills included)" vision item — worth a follow-up
     ADR before further agent-skills work on pko, to decide whether pko's skills
     complement or duplicate Pinokio's native ones.
   - Superseded original note: ~~"repository not found. No AGENTS.md or other
     content available"~~ — this was based on `deepwiki.read_wiki_structure` and
     `read_wiki_contents` both returning "Repository not found" (deepwiki-side
     indexing gap, not a real 404 — the repo exists and is public). No `AGENTS.md`
     was found in this repo specifically (it's a docs-site repo, not a
     launcher-project template like `proto`); the relevant file is `docs/README.md`.

6. **`pinokiocomputer/proto`'s `AGENTS.md`** — confirms the *convention* app
   authors are told to follow when writing their own `pinokio.js` scripts:
   check `logs/` first when debugging, with `api/` (launcher script logs),
   `dev/` (AI coding tool logs), `shell/` (direct user interaction logs) as
   the expected subdirectories, files named by Unix timestamp with a
   `latest` pointer — this matches exactly what was observed on disk for
   `pinokio-hello-world.git`, confirming the layout is a stable, documented
   convention pko can depend on, not an implementation accident.

### User stories mapped to features

| User story | Required feature(s) | Backing evidence |
|---|---|---|
| "How can I observe pinokio server activity (start/stop, app start/stop)?" | `pko logs --server` reading `logs/stdout.txt` + `logs/system.json`; optionally `pko logs --server --follow` via SSE once pinokiod exposes streaming for `stdout.txt` (today SSE stream only proven for per-app files — see Task list) | `startLogging()`, `system.json` snapshot content |
| "How can I troubleshoot an individual app (fails to launch / process dies / currently running / throws error)?" | `pko logs <app>` defaulting to `api/start.js/latest` (or the most recent script per `sessions/index.json`); `--follow` via `/api/logs/stream`; `--search TEXT` client-side grep over fetched content; `--level` heuristic filter (best-effort, since pinokiod has no real levels) | `sessions/*.json` (`ended_at: null` = still running), `api/<script>.js/latest`, `events` file format |
| "How can I ensure that an app that just installed can launch successfully?" | `pko logs <app> --script start.js --lines N` right after `pko start`; surfacing `sessions/index.json`'s most recent run's `ended_at` to report success/failure/still-running at a glance | `sessions/index.json` schema observed live |

### Decision

Redesign `pko logs` around **discovery-first, app-scoped access**, backed by
the modern `/api/logs/tree` + `/api/logs/stream` + `/pinokio/logs/file`
endpoints, with `/getlog` and the zip-export flow kept as fallbacks. New
subcommand shape:

- `pko logs --list [APP]` — discovery. No app = top-level server logs tree.
  With app = that app's log tree (mirrors `/api/logs/tree`).
- `pko logs [APP] [--file PATH]` — read a specific log (defaults to the most
  recent script's `latest` transcript for that app, or `stdout.txt` for the
  server).
- `--follow` / `-f` — live tail via SSE (`/api/logs/stream`).
- `--lines N` / `-n` — tail N lines (maps to `tail_lines` query param where
  supported, else client-side truncation).
- `--search TEXT` — client-side substring/regex filter over fetched lines.
- `--level LEVEL` — best-effort heuristic filter (matches common
  ERROR/WARN/INFO markers and non-zero-exit indicators in the text; pinokiod
  has no native level taxonomy, so this is explicitly documented as
  approximate, not authoritative).
- `--since DURATION` — filter by file mtime / line timestamp where the log
  format includes one (the `events` file has per-line ISO timestamps;
  `latest`/timestamped transcripts do not — `--since` degrades to
  file-mtime-based inclusion for those).
- `--server` — explicit flag to target server-level logs instead of an app
  (equivalent to omitting APP, made explicit for clarity in scripts).

### Consequences

- Requires adding `list_log_tree()`, `read_log_file()`, `stream_log()` to
  `client.py`, each mapping to the endpoints inventoried above.
- `--follow` needs an SSE client — `httpx` supports streaming responses
  natively (`client.stream("GET", ...)`), no new dependency required.
- `--level`/`--since` are explicitly best-effort given pinokiod does not
  provide structured levels or (for most files) per-line timestamps; this
  must be documented clearly in `--help` so users don't treat it as
  authoritative filtering.
- The old single-argument `--path`/`--tail` interface is superseded; this is
  a breaking CLI change for `pko logs`, acceptable pre-1.0.

### Sources
- `pinokiocomputer/pinokiod` — server/index.js (`startLogging`, `/api/logs/tree`,
  `/api/logs/stream`, `/pinokio/logs/file`, `/pinokio/log`, `/pinokio/logs.zip`,
  `/getlog`), server/socket.js (`resolveLogDir`, `appendEventLog`), server/lib/log_redaction.js
  (`createTopLevelLogFileHandler`, `isTopLevelRedactableLogPath`) — via deepwiki + direct read.
- `pinokiocomputer/pinokio` — Electron desktop log handling (`stdout.txt` path,
  `browser.log`, no follow/search/filter UI) — via deepwiki.
- `pinokiocomputer/proto` — `AGENTS.md` documented logs/ convention
  (`api/`, `dev/`, `shell/` subdirs, timestamp+`latest` naming) — via web_extract
  of raw AGENTS.md and deepwiki.
- `pinokiocomputer/home` — CORRECTED: repo is valid, contains Pinokio's canonical
  docs (`docs/README.md`, i.e. `PINOKIO.md`) including Orchestration and Agent
  Interpreter sections — retrieved via direct `web_extract` (deepwiki indexing was
  pending at time of writing; retry scheduled via cron job `deepwiki-retry-pinokio-home`).
- Live instance inspection — `curl` against `localhost:42000` (`/api/logs/tree`,
  `/pinokio/logs/file`, `/pinokio/fs`), direct filesystem read of
  `~/pinokio/api/pinokio-hello-world.git/logs/**` and `~/pinokio/logs/**` on the
  dev host (EndeavourOS, pinokiod 8.0.36, npm-installed).

---

## ADR-001: Python over TypeScript/Node for pko (2026-07-19)

### Status
Accepted

### Context
pko is a client to pinokiod's HTTP + WebSocket API. No code is shared with
pinokiod itself (Node.js). The deciding factor was which ecosystem serves
pko's target *users* best — AI agents (Hermes, Codex, Claude Code) and
human CLI users needing zero-install ergonomics.

### Decision
Python, packaged for `uv`/`uvx` zero-install use (`uvx pko ...`), using
`typer` + `rich` + `httpx` + `websockets`.

### Consequences
See PLAN.md "Architecture Decision: Python" for the full comparison table.

### Sources
- `pinokiocomputer/pinokio`, `pinokiocomputer/pinokiod`, `pinokiocomputer/proto`
  — via deepwiki, establishing the HTTP/WS API surface pko needed to wrap.
