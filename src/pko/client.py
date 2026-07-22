"""HTTP + WebSocket client for pinokiod."""
from __future__ import annotations

import asyncio
import json
import os
import re
from collections.abc import AsyncIterator, Callable
from pathlib import PurePosixPath, PureWindowsPath

import httpx
import websockets

from .models import AppInfo, AppStatus, PinokioInstance, SystemInfo, WsPacket


def _format_bytes(n: int | float) -> str:
    """Convert a byte count to a human-readable string (e.g. 218911011 → "209 MB")."""
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if abs(n) < 1024.0:
            if unit == "B":
                return f"{int(n)} B"
            return f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} EB"


def _extract_js_module_fields(source: str) -> dict | None:
    """Best-effort extraction of literal string fields from a pinokio.js
    CommonJS module (`module.exports = {...}`).

    Most launcher projects ship pinokio.js as real JavaScript rather than
    JSON (confirmed against a live instance — module.exports with a `menu`
    function, not a plain object literal). We don't attempt a real JS
    parse; this regexes out simple `key: "literal string"` pairs for the
    handful of fields pko cares about (title, description, icon, version).
    Computed/templated values (functions, template literals) are not
    resolved and are simply absent from the result.
    """
    if not source or "module.exports" not in source:
        return None
    fields: dict[str, str] = {}
    for key in ("title", "description", "icon", "version"):
        m = re.search(rf'{key}\s*:\s*["\']([^"\']*)["\']', source)
        if m:
            fields[key] = m.group(1)
    return fields or None


async def run_client(
    instance: PinokioInstance,
    handler: Callable,
) -> bool:
    """Create a Client, health-check, run handler, then close.

    Returns True if the handler ran; False if the health check failed.
    """
    client = Client(instance)
    try:
        ok = await client.health()
        if not ok:
            return False
        await handler(client, instance)
        return True
    finally:
        await client.close()


class Client:
    """HTTP client for pinokiod REST API."""

    def __init__(self, instance: PinokioInstance, timeout: float = 30.0):
        self.instance = instance
        self._http = httpx.AsyncClient(
            base_url=instance.base_url,
            timeout=httpx.Timeout(timeout),
            headers={"User-Agent": "pko/0.1.0"},
        )

    async def close(self) -> None:
        await self._http.aclose()

    async def health(self) -> bool:
        """GET /check — health check."""
        try:
            r = await self._http.get("/check")
            return r.status_code == 200
        except httpx.HTTPError:
            return False

    async def info(self) -> SystemInfo:
        """GET /pinokio/info — system information (diagnostics only, no app data)."""
        r = await self._http.get("/pinokio/info")
        r.raise_for_status()
        data = r.json()
        return SystemInfo(
            platform=data.get("platform", ""),
            arch=data.get("arch", ""),
            version=data.get("version", {}),
            memory=data.get("mem", {}),
            gpu=data.get("gpu", {}),
            home=data.get("home", ""),
        )

    async def resolve_script_path(self, app_name: str, script: str = "start.js") -> str:
        """Resolve the absolute filesystem path to a script file.

        pinokiod's WebSocket API requires the absolute path to the script
        file on the server (e.g. ``E:\\hal\\pinokio\\api\\comfy.git\\start.js``),
        not a virtual ``/api/...`` URI. The vendored ``pterm`` code resolves
        URIs using ``process.cwd()`` (same machine); pko resolves remotely
        by fetching the pinokio home directory from ``GET /pinokio/info``.

        Returns the path with forward slashes (Node.js handles both on
        all platforms).
        """
        sys_info = await self.info()
        if not sys_info.home:
            msg = "Cannot resolve script path: pinokio home directory unknown"
            raise RuntimeError(msg)
        # Use PurePosixPath for clean forward-slash joining regardless of
        # the client OS or server OS — Node.js on Windows handles both.
        parts = PurePosixPath(sys_info.home.replace("\\", "/"), "api", app_name, script)
        return str(parts)

    async def list_running_scripts(self) -> list[dict]:
        """GET /pinokio/info — extract only the running-scripts list.

        Separated from info() so 'is X running' checks don't imply pulling
        the whole system-diagnostics payload (GPU/memory) is the intended
        contract — see ADR-004.
        """
        r = await self._http.get("/pinokio/info")
        if r.status_code != 200:
            return []
        data = r.json()
        return data.get("scripts", [])

    async def list_apps_from_info(self) -> list[dict]:
        """Get installed apps list from /pinokio/info (more reliable than fs endpoint)."""
        r = await self._http.get("/pinokio/info")
        if r.status_code != 200:
            return []
        data = r.json()
        return data.get("api", [])

    async def get_port(self) -> int:
        """GET /pinokio/port — get an available port."""
        r = await self._http.get("/pinokio/port")
        r.raise_for_status()
        return r.json().get("result", 42000)

    async def list_apps(self) -> list[dict]:
        """List installed apps by reading the api directory."""
        r = await self._http.get("/pinokio/fs", params={"drive": "api", "path": "/"})
        if r.status_code in (404, 500):
            return []
        r.raise_for_status()
        data = r.json()
        apps = []
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    apps.append(item)
                elif isinstance(item, str):
                    apps.append({"name": item})
        return apps

    async def read_pinokio_js(self, app_name: str) -> dict | None:
        """Read pinokio.js/index.json metadata for an app.

        pinokio.js is typically a real JavaScript module
        (`module.exports = {...}`), not JSON — most launcher projects use
        this form per proto/AGENTS.md's conventions, confirmed against a
        live instance. Try JSON first (covers index.json and any
        JSON-only pinokio.js), then fall back to a best-effort regex
        extraction of simple string fields (title/description/icon) from
        the raw JS source. This will not resolve computed/templated
        values, but covers the common case of literal string fields.
        """
        r = await self._http.get(
            "/pinokio/fs",
            params={"drive": "api", "path": f"{app_name}/pinokio.js"},
        )
        if r.status_code == 404:
            # Try index.json
            r = await self._http.get(
                "/pinokio/fs",
                params={"drive": "api", "path": f"{app_name}/index.json"},
            )
        if r.status_code == 404:
            return None
        if r.status_code != 200:
            return None
        try:
            return r.json()
        except (json.JSONDecodeError, httpx.HTTPError):
            return _extract_js_module_fields(r.text)

    async def delete_app(self, app_name: str, delete_type: str = "bin") -> bool:
        """POST /pinokio/delete — delete an app."""
        r = await self._http.post("/pinokio/delete", json={"type": delete_type, "name": app_name})
        return r.status_code == 200

    async def get_config(self) -> dict:
        """Read the ENVIRONMENT file."""
        r = await self._http.get("/pinokio/fs", params={"drive": "api", "path": "../ENVIRONMENT"})
        if r.status_code != 200:
            return {}
        env_text = r.text
        result = {}
        for line in env_text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                result[k.strip()] = v.strip().strip('"').strip("'")
        return result

    async def get_logs(self, log_path: str) -> str | None:
        """GET /getlog — retrieve logs.

        Returns the log text if found, None if the log file doesn't exist
        (pinokiod returns 500 with an HTML error page for missing files).
        """
        r = await self._http.get("/getlog", params={"logpath": log_path})
        if r.status_code != 200:
            return None
        # pinokiod sometimes returns HTML error pages with 200 status
        if r.text.strip().startswith("<html") or r.text.strip().startswith("<!DOCTYPE"):
            return None
        return r.text

    async def get_app_logs(self, app_id: str, script: str = "start.js", tail: int = 50) -> dict | None:
        """GET /apps/logs/:id — structured logs for an app.

        Returns a dict with 'text' (full log content), 'lines' (list of lines),
        'line_count', 'size', and 'modified'. Returns None if the app has no logs.
        This is the canonical log endpoint used by pterm.
        """
        r = await self._http.get(
            f"/apps/logs/{app_id}",
            params={"script": script, "tail": str(tail)},
        )
        if r.status_code != 200:
            return None
        try:
            data = r.json()
            if not isinstance(data, dict) or "text" not in data:
                return None
            return data
        except Exception:
            return None

    async def restart(self) -> bool:
        """POST /restart — restart the server."""
        r = await self._http.post("/restart")
        return r.status_code == 200

    async def disk_usage(self, app_name: str) -> str | None:
        """GET /du/:name — disk usage for an app.

        Returns a human-readable string like "209 MB" or "6.6 GB".
        The raw response is JSON with a ``du`` key containing bytes.
        """
        r = await self._http.get(f"/du/{app_name}")
        if r.status_code != 200:
            return None
        try:
            data = r.json()
            raw = data.get("du", r.text)
        except Exception:
            raw = r.text
        if isinstance(raw, (int, float)):
            return _format_bytes(raw)
        if isinstance(raw, str) and raw.strip().isdigit():
            return _format_bytes(int(raw.strip()))
        # Already a string like "1.2GB" — return as-is
        return str(raw) if raw else None

    async def get_app_status(self, app_name: str) -> AppStatus | None:
        """GET /apps/status/:id — rich per-app status.

        Returns a typed AppStatus dataclass. Returns None if the app
        doesn't exist or the endpoint is unavailable.
        """
        r = await self._http.get(f"/apps/status/{app_name}")
        if r.status_code != 200:
            return None
        try:
            data = r.json()
            return AppStatus(
                app_id=data.get("app_id", app_name),
                running=bool(data.get("running", False)),
                ready_url=data.get("ready_url", ""),
                title=data.get("title", ""),
                description=data.get("description", ""),
                icon=data.get("icon", ""),
                path=data.get("path", app_name),
                running_scripts=data.get("running_scripts", []),
            )
        except (json.JSONDecodeError, httpx.HTTPError):
            return None

    async def get_app_metadata(self, app_name: str) -> AppInfo | None:
        """Rich metadata for an app: prefer /apps/status/:id (title,
        description, icon, running state all in one call — see
        get_app_status), fall back to reading pinokio.js/index.json
        directly if the status endpoint is unavailable. Disk usage always
        comes from a separate /du/:name call.

        Backs `pko inspect <app>` (ADR-004).
        """
        du = await self.disk_usage(app_name)
        status = await self.get_app_status(app_name)
        if status is not None:
            return AppInfo(
                name=app_name,
                path=status.path or app_name,
                title=status.title or app_name,
                description=status.description or "",
                icon=status.icon or "",
                running=status.running,
                disk_usage=du or "",
            )
        script = await self.read_pinokio_js(app_name)
        if script is None:
            return None
        return AppInfo(
            name=app_name,
            path=app_name,
            title=script.get("title", app_name),
            description=script.get("description", ""),
            icon=script.get("icon", ""),
            running=False,
            disk_usage=du or "",
        )


class WsClient:
    """WebSocket client for pinokiod streaming operations."""

    def __init__(self, instance: PinokioInstance):
        self.instance = instance

    async def run_script(
        self,
        uri: str,
        mode: str = "run",
        input_data: dict | None = None,
        on_packet: Callable[[WsPacket], None] | None = None,
    ) -> AsyncIterator[WsPacket]:
        """Run a script via WebSocket and stream packets."""
        payload = {
            "uri": uri,
            "mode": mode,
            "input": input_data or {},
            "client": {"cols": 80, "rows": 24},
        }

        async with websockets.connect(self.instance.ws_url) as ws:
            await ws.send(json.dumps(payload))
            async for raw in ws:
                try:
                    data = json.loads(raw)
                    packet = WsPacket(
                        type=data.get("type", ""),
                        id=data.get("id", ""),
                        data=data.get("data", {}),
                        index=data.get("index", 0),
                    )
                    if on_packet:
                        on_packet(packet)
                    yield packet
                except json.JSONDecodeError:
                    continue

    async def stop_script(self, uri: str) -> None:
        """Send stop command via WebSocket."""
        payload = {
            "method": "kernel.api.stop",
            "params": {"uri": uri},
        }

        async with websockets.connect(self.instance.ws_url) as ws:
            await ws.send(json.dumps(payload))

    async def start_script_and_wait(self, uri: str) -> str:
        """Run a script and return the accumulated output text."""
        output_parts: list[str] = []

        async for packet in self.run_script(uri):
            if packet.type == "stream":
                text = packet.data.get("data", "")
                if text:
                    output_parts.append(text)
            elif packet.type == "error":
                error_msg = packet.data.get("message", str(packet.data))
                output_parts.append(f"[ERROR] {error_msg}")
            elif packet.type == "result":
                break

        return "".join(output_parts)