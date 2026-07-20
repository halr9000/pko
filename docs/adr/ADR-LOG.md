# Architecture Decision Records — pko

This log captures significant design decisions for `pko`, with the research/evidence
that drove them. Newest entries at the top.

Sources cited inline use short refs — see README.md "Sources" section for the full
list and how to re-query them via deepwiki.

---

## ADR-005: `pterm` discovery — strategic options (2026-07-19)

Full content lives in `PLAN.md`'s "`pterm` Discovery — Strategic Options
(ADR-005)" section, since it's an options-menu for the user rather than a
settled decision. Summary: the Pinokio author pointed us at `pterm`
(https://github.com/pinokiocomputer/pterm), his own Node.js CLI for
Pinokio — and it turns out to be the actual implementation underneath
`SKILL_PINOKIO.md` (the vendored skill teaches an agent to shell out to it).
It covers nearly all of pko's planned Phase 2–4 roadmap (registry search,
install, start/stop, status, logs) with a working, authoritative protocol
reference. Four options laid out (independent Python impl informed by
`pterm`'s source; thin wrapper shelling out to `pterm`; hybrid
detect-and-delegate; scope pko down to only what `pterm` can't do), with a
non-binding recommendation for Option 1 (keep pko pure-Python/zero-Node,
use `pterm`'s source as a protocol reference rather than a runtime
dependency) — since Options 2/3 would add a Node.js dependency that
contradicts pko's stated "agent runs outside the box," minimal-deps,
uvx-first premise. Decision pending user input; three open questions
posed in PLAN.md.

---



## ADR-004: `info`/`status` rationalization — see PLAN.md

Full ADR content lives in `PLAN.md`'s "`info` / `status` Rationalization
(ADR-004)" section rather than duplicated here, since it's implementation-
phase-heavy (13 tasks across 5 phases) and PLAN.md is the living roadmap
doc. Summary: `info` currently conflates system diagnostics with app-runtime
data (`running_scripts`, `apps`); `status` inefficiently depends on the same
heavy `/pinokio/info` call instead of the lightweight WebSocket
`check_status()` (which exists but is dead code). Proposal: `info` becomes
system-only, `status` becomes app-runtime-only (WebSocket-based for single
app), and a new `pko inspect <app>` command fills the "rich app metadata"
gap neither command currently covers. Breaking change, acceptable pre-1.0.

---


## ADR-003: Agent-skills boundary vs. Pinokio's built-in agent layer, and vendoring strategy (2026-07-19)

### Status
Accepted

### Context

Following the ADR-002 correction that `pinokiocomputer/home` is a valid,
richly documented repo, deeper research (deepwiki + direct code inspection of
the running `pinokiod` npm package) surfaced that **Pinokio itself ships a
built-in agent-facing layer** — not just documentation about one. This
directly overlaps with pko's own "Built for agents (agent skills included)"
vision item, and the user flagged the risk explicitly: avoiding a
**split-brain problem** where pko's skills and Pinokio's built-in skills give
an agent conflicting or duplicate instructions for the same operation.

### What Pinokio ships natively (confirmed via source)

`pinokiod/kernel/managed_skills.js` auto-generates and maintains two
built-in `SKILL.md` files, written into every one of:
```
~/.agents/skills/<id>/SKILL.md
~/.claude/skills/<id>/SKILL.md
~/.hermes/skills/<id>/SKILL.md
```
(`publishRoots()`, `managed_skills.js:43-47`) — i.e. **Pinokio already
installs itself into Hermes's own skill directory**, unprompted, whenever
pinokiod runs, if it can write there.

1. **`pinokio` skill** — sourced verbatim from
   `pinokiod/prototype/system/SKILL_PINOKIO.md` (see vendoring below). This is
   a **"pterm-first" runtime-control skill**: search installed apps
   (`pterm search`), check status (`pterm status`), launch
   (`pterm run <ref>`), poll for readiness, call the app's API directly or
   generate a reusable per-app client, view logs (`pterm logs`), and a
   "Parallel Mode" for explicitly multi-app/multi-machine tasks. Notably:
   `pterm status`'s output already includes a `ref` field shaped
   `pinokio://<host>:<port>/<scope>/<id>` and explicitly documents **cross-machine
   results** (`source.local=false`) — i.e. Pinokio's own built-in skill already
   has *some* multi-instance awareness via `pterm`'s registry, not just
   single-box.

2. **`gepeto` skill** — dynamically composed by wrapping the *target Pinokio
   home's own* `AGENTS.md` (rendered from `proto`'s template at project-init
   time) with a `name: gepeto` / `description: Guide for building 1-click
   launchers...` frontmatter block (`managed_skills.js:308-321`). This is the
   **app-authoring / launcher-building** skill — how to structure
   `install.js`/`start.js`/`pinokio.js`/`pinokio.json`, PINOKIO_HOME
   resolution, the full Script API reference, and best practices. This is
   the exact content of `proto/AGENTS.md`, vendored below.

3. Pinokio's own docs (`pinokiocomputer/home`, §5.2) confirm this works with
   *external* agents too: "Codex CLI in terminal, Claude Code in terminal,
   Codex Desktop, Gemini CLI, Cursor, Anything else" — plus explicit mention
   of Hermes Agent and OpenClaw as example orchestrators (§5.3). Most
   auto-discover `~/.agents/skills`; agents that don't (Claude Desktop) can
   import the `SKILL.md` manually via a Settings-page download.

### The actual boundary (per user's framing)

The user's framing is the deciding design principle for this ADR: **where
does the agent sit relative to the box?**

- Pinokio's built-in `pinokio`/`gepeto` skills assume **the agent runs on
  (or is invoked from within) a single Pinokio instance's own machine** —
  `pterm` is a local binary, resolved via `~/.pinokio/config.json` or
  `127.0.0.1:42000`. The skill's own resolution logic explicitly treats
  loopback-unreachable as an exceptional, fallback-worthy case, not the
  default assumption.
- pko's premise is the opposite default: **the agent runs outside any
  particular Pinokio box**, and may manage zero, one, or many boxes it
  doesn't have local shell/filesystem access to at all (a phone-side agent
  managing a homelab GPU rig over Tailscale, for example). pko's `client.py`
  is HTTP/WS-only by construction — it never assumes local `pterm`,
  `~/.pinokio/config.json`, or filesystem access to `PINOKIO_HOME`.

This is not a cosmetic difference — it changes which failure modes and
discovery steps matter. Pinokio's skill's Failure Handling section is about
sandbox/permission errors resolving a *local* binary. pko's discovery
(`pko discover`, profiles) is about finding and authenticating to a
*network-reachable* instance in the first place, which the built-in skill
doesn't attempt (it assumes exactly one instance, itself).

### Decision

1. **Do not duplicate `pterm`'s single-instance runtime-control logic in a
   pko skill.** For any task where an agent already has local access to a
   Pinokio instance and its own `pinokio`/`gepeto` skills (i.e. `pterm` /
   `~/.pinokio/config.json` resolve successfully), **the correct outcome is
   for the agent to just use those built-in skills** — pko's skill docs
   should say so explicitly rather than re-teach `pterm search`/`run`/`status`.

2. **pko's skills own only what upstream does not cover:**
   - **Remote/multi-instance discovery and profile management** — `pko
     discover`, `pko connect`, `pko profile` have no upstream equivalent;
     `pterm`'s registry cross-machine awareness is opportunistic (results
     from *reachable* peers), not a discovery/profile primitive an external
     agent can drive.
   - **Zero-local-access operation** — every pko operation works over
     HTTP/WS from a machine with no `pterm` binary, no `~/.pinokio/`, and no
     filesystem access to any `PINOKIO_HOME`. This is pko's entire reason to
     exist and is explicitly *not* what the built-in skill is built for.
   - **Cross-instance orchestration a single `pterm` invocation can't
     express** — e.g. "check status on 3 named profiles and report which
     ones have app X running" is a pko-shaped operation, not a `pterm`-shaped
     one (the built-in skill's own "Parallel Mode" section still assumes
     the invoking agent has local `pterm` and enumerates `ref`s from a
     single local search).
   - **Everything already planned and unique to pko**: logs redesign
     (ADR-002; note `pterm logs` exists but is a thin CLI wrapper without the
     tree/stream/filter feature set ADR-002 specifies), install (once
     implemented), start/stop across profiles.

3. **pko's `create-app` command wraps the `gepeto`-equivalent workflow, not
   a new invention.** `proto/AGENTS.md` (vendored, see below) is the design
   source: it defines the full app-authoring contract — mandatory
   `PINOKIO_HOME` resolution order, app-launcher (`api/`) vs. plugin-launcher
   (`plugin/`) destination rules, the four-part project shape (`pinokio.json`
   config, `ENVIRONMENT`, script files, `pinokio.js` launcher UI), the full
   Script API surface, and numbered best practices (retrofitting existing
   working setups, AI-bundle declarations for torch/xformers, gitignore
   rules, cross-platform command preferences, etc.). **`pko create-app`
   should not reimplement any of this reasoning** — it should shell out to
   (or programmatically drive) whatever AI-agent-assisted flow the user
   already has available, primed with this exact document as context,
   mirroring what Pinokio's own "Create" button does per `home`'s §5
   (prompt → agent/IDE selection → AI-assisted build → Run → Publish).
   Concretely this likely means: `pko create-app <name>` resolves
   `PINOKIO_HOME` the same way `proto/AGENTS.md` specifies, scaffolds the
   destination folder, and either (a) hands off to a `delegate_task`-style
   agent invocation loaded with the vendored `AGENTS.md` as its brief, or
   (b) if pko is being driven by an agent that already has this skill
   installed, simply documents the contract for that agent to follow
   directly — **not** duplicate logic that would drift from upstream.
   This confirms **`create-app` and `install` are related but distinct**:
   `create-app` produces a *new* launcher project from scratch (writes
   `install.js`/`start.js`/`pinokio.js`/`pinokio.json` following the
   `proto/AGENTS.md` contract); `install` (still a stub) takes an *existing*
   git URL pointing at an already-built launcher project and clones it into
   `PINOKIO_HOME/api/`. `create-app` may call `install`-equivalent logic at
   the end (registering the freshly-created project with the running
   instance) but they are not the same operation and should not be merged
   into one command.

4. **Vendoring mechanism.** Rather than a git submodule/subtree (too heavy
   for two files, and subtree pulls the whole upstream repo history), pko
   vendors these two files via a small manifest-driven sync script:
   - `vendor/manifest.json` — human-edited: which files, from which
     repo/path/ref, why (rationale field required per entry).
   - `vendor/manifest.lock.json` — machine-generated: the exact upstream
     commit SHA each vendored file was last synced from. Committed to git so
     drift is visible in review (`git diff` on the lock file = "upstream
     changed since we last looked").
   - `scripts/sync_vendor.py` — zero-dependency (stdlib `urllib` only, works
     without `uv sync` first) script with two modes: default (fetch+write),
     `--check` (CI-friendly: resolve latest upstream SHA via GitHub API,
     compare to lock, exit 1 if stale, no content fetch/write).
   - Vendored files are **never hand-edited** — the manifest documents this
     and `sync_vendor.py`'s docstring repeats it. Any local adjustment must
     happen in pko's own code/docs that *reference* the vendored file, not
     in the vendored copy itself.

### Consequences

- New `vendor/` directory tracked in git (not gitignored) — the whole point
  is these files are committed so `git diff` shows upstream drift.
- **Enforcement wired (2026-07-19, same day):** `.githooks/pre-commit`
  (opt-in via `git config core.hooksPath .githooks`) runs
  `sync_vendor.py --check` before every commit; `.github/workflows/ci.yml`
  runs the same check on every push/PR plus a weekly cron so drift surfaces
  even without local commits. Neither auto-fixes — refreshing is always a
  manual `uv run python scripts/sync_vendor.py` + reviewed diff. This closes
  the "not yet wired" gap noted below in the original version of this ADR.
- pko's own future `skills/pko-*` SKILL.md files must each state, in their
  own text, "if `pterm`/the `pinokio` skill is available and reachable
  locally, prefer it for \<X\>" where applicable, rather than silently
  overlapping.
- `create-app` implementation (not yet started) is now scoped: it is an
  agent-hand-off / scaffolding command primed by `vendor/proto/AGENTS.md`,
  not a from-scratch reimplementation of Pinokio's launcher-authoring rules.
- This ADR does *not* resolve exactly how the create-app hand-off is wired
  (subagent delegation vs. printing the brief vs. something else) — that is
  implementation-phase work, tracked in PLAN.md's Create App section.

### Sources
- `pinokiocomputer/pinokiod` — `kernel/managed_skills.js` (`BUILTIN_SKILLS`,
  `publishRoots`, `composeBuiltinSkillContent`, `syncBuiltinSourceFiles`) —
  direct source read of the running npm package (v8.0.36).
- `pinokiocomputer/pinokiod` — `prototype/system/SKILL_PINOKIO.md` — direct
  source read + vendored verbatim, commit `89957c62bde6` on `main`
  (see `vendor/manifest.lock.json`).
- `pinokiocomputer/proto` — `AGENTS.md` — vendored verbatim, commit
  `f46c872ba944` on `main` (see `vendor/manifest.lock.json`).
- `pinokiocomputer/home` — `docs/README.md` §5 "Agent Interpreter" (via
  `web_extract`, deepwiki indexing was still pending at time of writing) —
  confirms the `~/.agents/skills` convention, external-agent compatibility
  list, and the Pinokio-side "Create" UI workflow this ADR's `create-app`
  design should mirror.

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
