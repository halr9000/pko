"""Pinokio instance discovery.

Scans well-known ports on localhost, supports manual connection,
and env-var-based configuration.
"""

from __future__ import annotations

import asyncio
import socket
from typing import Optional

import httpx

from .models import PinokioInstance, KNOWN_PORTS, DEFAULT_PORT
from .config import get_default_instance


async def probe_instance(host: str, port: int, timeout: float = 2.0) -> Optional[PinokioInstance]:
    """Check if pinokiod is running at host:port."""
    try:
        async with httpx.AsyncClient(
            base_url=f"http://{host}:{port}",
            timeout=httpx.Timeout(timeout),
        ) as client:
            r = await client.get("/check")
            if r.status_code == 200:
                return PinokioInstance(
                    host=host,
                    port=port,
                    source="discover",
                    is_local=host in ("localhost", "127.0.0.1", "::1", socket.gethostname()),
                )
    except (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError):
        pass
    return None


async def discover_local(timeout: float = 2.0) -> list[PinokioInstance]:
    """Scan localhost on well-known ports."""
    results = []
    for port in KNOWN_PORTS:
        result = await probe_instance("localhost", port, timeout)
        if result:
            results.append(result)
    return results


async def discover_remote(host: str, timeout: float = 2.0) -> list[PinokioInstance]:
    """Scan a remote host on well-known ports."""
    results = []
    for port in KNOWN_PORTS:
        result = await probe_instance(host, port, timeout)
        if result:
            results.append(result)
    return results


def resolve_instance(
    host: Optional[str] = None,
    port: Optional[int] = None,
) -> PinokioInstance:
    """Resolve a Pinokio instance from CLI args, env, or config."""
    if host:
        return PinokioInstance(
            host=host,
            port=port or DEFAULT_PORT,
            source="cli",
            is_local=host in ("localhost", "127.0.0.1", "::1"),
        )
    return get_default_instance()