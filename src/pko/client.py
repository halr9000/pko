"""HTTP + WebSocket client for pinokiod."""

from __future__ import annotations

import json
from typing import Any, AsyncIterator, Callable, Optional

import httpx

from .models import PinokioInstance, SystemInfo, WsPacket
from .config import CONFIG_DIR


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
        """GET /pinokio/info — system information."""
        r = await self._http.get("/pinokio/info")
        r.raise_for_status()
        data = r.json()
        return SystemInfo(
            platform=data.get("platform", ""),
            arch=data.get("arch", ""),
            version=data.get("version", ""),
            memory=data.get("mem", {}),
            gpu=data.get("gpu", {}),
            running_scripts=data.get("scripts", []),
            home=data.get("home", ""),
            apps=data.get("api", []),
        )

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
        """Read pinokio.js metadata for an app."""
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
            return None

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