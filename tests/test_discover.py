"""Tests for pko discovery module."""
from unittest.mock import patch

import httpx

from pko.discover import discover_local, probe_instance, resolve_instance
from pko.models import PinokioInstance


class TestProbeInstance:
    async def test_successful_probe(self):
        async def mock_get(*a, **kw):
            return httpx.Response(200, json={"success": True})

        with patch("httpx.AsyncClient.get", mock_get):
            result = await probe_instance("10.0.0.1", 42000)
            assert result is not None
            assert result.host == "10.0.0.1"
            assert result.port == 42000
            assert result.source == "discover"

    async def test_failed_probe(self):
        async def mock_get(*a, **kw):
            raise httpx.ConnectError("refused")

        with patch("httpx.AsyncClient.get", mock_get):
            result = await probe_instance("10.0.0.1", 42000)
            assert result is None


class TestDiscoverLocal:
    async def test_no_instances(self):
        async def mock_probe(host, port, timeout=2.0):
            return None

        with patch("pko.discover.probe_instance", mock_probe):
            results = await discover_local()
            assert results == []

    async def test_one_found(self):
        found = PinokioInstance(host="localhost", port=42000, source="discover")

        async def mock_probe(host, port, timeout=2.0):
            return found if port == 42000 else None

        with patch("pko.discover.probe_instance", mock_probe):
            results = await discover_local()
            assert len(results) == 1
            assert results[0].port == 42000


class TestResolveInstance:
    def test_with_host_port(self):
        inst = resolve_instance(host="10.0.0.1", port=42001)
        assert inst.host == "10.0.0.1"
        assert inst.port == 42001
        assert inst.source == "cli"

    def test_host_with_default_port(self):
        inst = resolve_instance(host="192.168.1.1")
        assert inst.port == 42000

    def test_no_args_uses_default(self):
        with patch("pko.discover.get_default_instance") as mock_default:
            mock_default.return_value = PinokioInstance(
                host="localhost", port=42000, source="default"
            )
            inst = resolve_instance()
            assert inst.host == "localhost"
