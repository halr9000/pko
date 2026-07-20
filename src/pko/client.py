"""HTTP + WebSocket client for pinokiod."""

from __future__ import annotations

import json
import re
from typing import Any, AsyncIterator, Callable, Optional

import httpx

from .models import AppInfo, PinokioInstance, SystemInfo, WsPacket
from .config import CONFIG_DIR


def _extract_js_module_fields(source: str) -> Optional[dict]:
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
        except httpx.ConnectError:
            return False

    async def info(self) -> SystemInfo:
        """GET /pinokio/info — system information (diagnostics only, no app data)."""
        r = await self._http.get("/pinokio/info")
        r.raise_for_status()
        data = r.json()
        return SystemInfo(
            platform=data.get("platform", ""),
            arch=data.get("arch", ""),
            version=data.get("version", ""),
            memory=data.get("mem", {}),
            gpu=data.get("gpu", {}),
            home=data.get("home", ""),
        )

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

    async def read_pinokio_js(self, app_name: str) -> Optional[dict]:
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

    async def get_logs(self, log_path: str) -> str:
        """GET /getlog — retrieve logs."""
        r = await self._http.get("/getlog", params={"logpath": log_path})
        if r.status_code != 200:
            return ""
        return r.text

    async def restart(self) -> bool:
        """POST /restart — restart the server."""
        r = await self._http.post("/restart")
        return r.status_code == 200

    async def disk_usage(self, app_name: str) -> Optional[str]:
        """GET /du/:name — disk usage for an app."""
        r = await self._http.get(f"/du/{app_name}")
        if r.status_code != 200:
            return None
        return r.text

    async def get_app_status(self, app_name: str) -> Optional[dict]:
        """GET /apps/status/:id — rich per-app status.

        Discovered via the vendored pterm/util.js reference (ADR-005):
        pterm's own `status` command uses this endpoint, not a WebSocket
        probe. Confirmed live: returns running/ready state, title,
        description, icon, ready_url, and running_scripts in one HTTP
        call — strictly better than pko's prior WebSocket check_status()
        approach (which mis-resolves the running script's URI for apps
        whose default script isn't literally 'start.js', and needed a
        separate call for app metadata). Superseded WsClient.check_status
        as the canonical status path — see ADR-004 addendum.
        """
        r = await self._http.get(f"/apps/status/{app_name}")
        if r.status_code != 200:
            return None
        try:
            return r.json()
        except (json.JSONDecodeError, httpx.HTTPError):
            return None

    async def get_app_metadata(self, app_name: str) -> Optional[AppInfo]:
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
                path=status.get("path", app_name),
                title=status.get("title", app_name),
                description=status.get("description", ""),
                icon=status.get("icon", ""),
                running=bool(status.get("running", False)),
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
        self._ws = None

    async def connect(self) -> None:
        import websockets
        self._ws = await websockets.connect(self.instance.ws_url)

    async def run_script(
        self,
        uri: str,
        mode: str = "run",
        input_data: Optional[dict] = None,
        on_packet: Optional[Callable[[WsPacket], None]] = None,
    ) -> AsyncIterator[WsPacket]:
        """Run a script via WebSocket and stream packets."""
        from websockets import connect as ws_connect

        payload = {
            "uri": uri,
            "mode": mode,
            "input": input_data or {},
            "client": {"cols": 80, "rows": 24},
        }

        async with ws_connect(self.instance.ws_url) as ws:
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
        from websockets import connect as ws_connect

        payload = {
            "method": "kernel.api.stop",
            "params": {"uri": uri},
        }

        async with ws_connect(self.instance.ws_url) as ws:
            await ws.send(json.dumps(payload))

    async def check_status(self, uri: str) -> bool:
        """Check if a script is running."""
        from websockets import connect as ws_connect

        payload = {"uri": uri, "status": True}

        async with ws_connect(self.instance.ws_url) as ws:
            await ws.send(json.dumps(payload))
            async for raw in ws:
                try:
                    data = json.loads(raw)
                    return data.get("data") is True
                except json.JSONDecodeError:
                    continue
        return False

    async def close(self) -> None:
        if self._ws:
            await self._ws.close()