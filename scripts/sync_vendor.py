#!/usr/bin/env python3
"""Sync vendored single-file dependencies from upstream Pinokio repos.

Why this exists: pko explicitly depends on two files pinokiod/proto ship for
agent use (see vendor/manifest.json for rationale). We do NOT want a git
submodule or subtree — we want exactly these files, refreshed on demand, with
the exact upstream commit SHA recorded so drift is visible in `git diff` and
reproducible in CI.

Usage:
    uv run python scripts/sync_vendor.py            # sync all files, write lock
    uv run python scripts/sync_vendor.py --check     # exit 1 if any file is stale
                                                       # vs. its locked SHA (no network)

This has zero non-stdlib dependencies (uses urllib) so it can run in CI
without installing pko's own deps first.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT / "vendor" / "manifest.json"
LOCK_PATH = ROOT / "vendor" / "manifest.lock.json"

GITHUB_API = "https://api.github.com"
RAW_GITHUB = "https://raw.githubusercontent.com"


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "pko-vendor-sync"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def latest_commit_sha(repo: str, ref: str, path: str) -> str:
    """Resolve the most recent commit SHA that touched `path` on `ref`."""
    url = f"{GITHUB_API}/repos/{repo}/commits?path={path}&sha={ref}&per_page=1"
    data = json.loads(_get(url))
    if not data:
        raise RuntimeError(f"No commits found for {repo}@{ref}:{path}")
    return data[0]["sha"]


def fetch_raw(repo: str, sha: str, path: str) -> bytes:
    url = f"{RAW_GITHUB}/{repo}/{sha}/{path}"
    return _get(url)


def load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text())


def load_lock() -> dict:
    if LOCK_PATH.exists():
        return json.loads(LOCK_PATH.read_text())
    return {"files": {}}


def sync(check_only: bool = False) -> int:
    manifest = load_manifest()
    lock = load_lock()
    stale = []
    updated = {}

    for entry in manifest["files"]:
        fid = entry["id"]
        repo = entry["source_repo"]
        ref = entry["ref"]
        source_path = entry["source_path"]
        dest = ROOT / entry["dest"]

        try:
            sha = latest_commit_sha(repo, ref, source_path)
        except (urllib.error.URLError, RuntimeError) as e:
            print(f"[{fid}] ERROR resolving latest commit: {e}", file=sys.stderr)
            return 2

        locked_sha = lock.get("files", {}).get(fid, {}).get("sha")

        if check_only:
            if locked_sha != sha:
                stale.append((fid, locked_sha, sha))
            continue

        if locked_sha == sha and dest.exists():
            print(f"[{fid}] up to date ({sha[:12]})")
            updated[fid] = lock["files"][fid]
            continue

        print(f"[{fid}] fetching {repo}@{sha[:12]}:{source_path}")
        content = fetch_raw(repo, sha, source_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)
        updated[fid] = {
            "sha": sha,
            "source_repo": repo,
            "source_path": source_path,
            "dest": entry["dest"],
        }
        print(f"[{fid}] wrote {entry['dest']} ({len(content)} bytes) @ {sha[:12]}")

    if check_only:
        if stale:
            print("STALE vendor files detected:")
            for fid, locked_sha, current_sha in stale:
                locked_display = locked_sha[:12] if locked_sha else "unlocked"
                print(f"  {fid}: locked={locked_display} latest={current_sha[:12]}")
            return 1
        print("All vendor files up to date.")
        return 0

    LOCK_PATH.write_text(json.dumps({"files": updated}, indent=2) + "\n")
    print(f"Wrote {LOCK_PATH.relative_to(ROOT)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Only check if vendor files are stale vs. upstream; no writes, no network fetch of content (still calls GitHub API to resolve latest SHA).",
    )
    args = parser.parse_args()
    return sync(check_only=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
