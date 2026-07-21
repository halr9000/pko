"""Tests for pko HTTP client (mocked and integration)."""
import json
from unittest.mock import patch

import httpx
import pytest

from pko.client import Client, WsClient
from pko.models import PinokioInstance

LOCAL = PinokioInstance(host="localhost", port=42000, is_local=True)


#
# ── Mocked unit tests ───────────────────────────────────────────────
#


@pytest.fixture
async def client():
    """Create a client pointing at localhost:42000 but with mock transport."""
    c = Client(LOCAL)
    yield c
    await c.close()


class TestClientHealth:
    async def test_healthy(self):
        async def mock_get(*a, **kw):
            return httpx.Response(200, json={"success": True})

        with patch.object(httpx.AsyncClient, "get", mock_get):
            c = Client(LOCAL)
            ok = await c.health()
            assert ok is True
            await c.close()

    async def test_unhealthy(self):
        async def mock_get(*a, **kw):
            raise httpx.ConnectError("refused")

        with patch.object(httpx.AsyncClient, "get", mock_get):
            c = Client(LOCAL)
            ok = await c.health()
            assert ok is False
            await c.close()


class TestClientInfo:
    async def test_returns_system_info(self):
        mock_data = {
            "platform": "linux",
            "arch": "x64",
            "version": {"pinokiod": "8.0.36"},
            "mem": {"total": 16000000, "free": 8000000},
            "gpu": {"model": "Intel"},
            "scripts": [{"app": "comfyui", "local": {"url": "http://localhost:7860"}}],
            "home": "/home/user/pinokio",
        }
        req = httpx.Request("GET", "http://localhost:42000/pinokio/info")

        async def mock_get(*a, **kw):
            return httpx.Response(200, json=mock_data, request=req)

        with patch.object(httpx.AsyncClient, "get", mock_get):
            c = Client(LOCAL)
            info = await c.info()
            assert info.platform == "linux"
            assert info.version == {"pinokiod": "8.0.36"}
            assert info.memory["total"] == 16000000
            assert info.home == "/home/user/pinokio"
            assert not hasattr(info, "running_scripts")
            assert not hasattr(info, "apps")
            await c.close()


class TestClientListRunningScripts:
    async def test_returns_scripts(self):
        mock_data = {
            "scripts": [{"app": "comfyui", "local": {"url": "http://localhost:7860"}}],
        }

        async def mock_get(*a, **kw):
            return httpx.Response(200, json=mock_data)

        with patch.object(httpx.AsyncClient, "get", mock_get):
            c = Client(LOCAL)
            scripts = await c.list_running_scripts()
            assert len(scripts) == 1
            assert scripts[0]["app"] == "comfyui"
            await c.close()

    async def test_empty_on_error(self):
        async def mock_get(*a, **kw):
            return httpx.Response(500)

        with patch.object(httpx.AsyncClient, "get", mock_get):
            c = Client(LOCAL)
            scripts = await c.list_running_scripts()
            assert scripts == []
            await c.close()


class TestClientListApps:
    async def test_empty(self):
        async def mock_get(*a, **kw):
            return httpx.Response(404, json={"error": "not found"})

        with patch.object(httpx.AsyncClient, "get", mock_get):
            c = Client(LOCAL)
            apps = await c.list_apps()
            assert apps == []
            await c.close()

    async def test_with_apps(self):
        mock_data = [{"name": "comfyui", "title": "ComfyUI"}, {"name": "foo"}]
        req = httpx.Request("GET", "http://localhost:42000/pinokio/fs")

        async def mock_get(*a, **kw):
            return httpx.Response(200, json=mock_data, request=req)

        with patch.object(httpx.AsyncClient, "get", mock_get):
            c = Client(LOCAL)
            apps = await c.list_apps()
            assert len(apps) == 2
            assert apps[0]["name"] == "comfyui"
            await c.close()


class TestClientReadPinokioJs:
    async def test_found(self):
        mock_meta = {"title": "Test App", "description": "A test"}

        async def mock_get(*a, **kw):
            return httpx.Response(200, json=mock_meta)

        with patch.object(httpx.AsyncClient, "get", mock_get):
            c = Client(LOCAL)
            meta = await c.read_pinokio_js("testapp")
            assert meta["title"] == "Test App"
            await c.close()

    async def test_not_found(self):
        async def mock_get(*a, **kw):
            return httpx.Response(404)

        with patch.object(httpx.AsyncClient, "get", mock_get):
            c = Client(LOCAL)
            meta = await c.read_pinokio_js("nonexistent")
            assert meta is None
            await c.close()


class TestClientDelete:
    async def test_success(self):
        async def mock_post(*a, **kw):
            return httpx.Response(200, json={"success": True})

        with patch.object(httpx.AsyncClient, "post", mock_post):
            c = Client(LOCAL)
            assert await c.delete_app("testapp") is True
            await c.close()

    async def test_failure(self):
        async def mock_post(*a, **kw):
            return httpx.Response(500, json={"error": "fail"})

        with patch.object(httpx.AsyncClient, "post", mock_post):
            c = Client(LOCAL)
            assert await c.delete_app("testapp") is False
            await c.close()


class TestClientConfig:
    async def test_parses_environment_file(self):
        env_content = "KEY1=value1\nKEY2=value2\n# comment\nKEY3=value3\n"

        async def mock_get(*a, **kw):
            return httpx.Response(200, text=env_content)

        with patch.object(httpx.AsyncClient, "get", mock_get):
            c = Client(LOCAL)
            env = await c.get_config()
            assert env["KEY1"] == "value1"
            assert env["KEY2"] == "value2"
            assert env["KEY3"] == "value3"
            assert "# comment" not in env
            await c.close()

    async def test_empty_when_not_found(self):
        async def mock_get(*a, **kw):
            return httpx.Response(404)

        with patch.object(httpx.AsyncClient, "get", mock_get):
            c = Client(LOCAL)
            assert await c.get_config() == {}
            await c.close()


class TestClientGetAppStatus:
    async def test_running(self):
        mock_data = {
            "app_id": "testapp",
            "running": True,
            "ready_url": "http://127.0.0.1:7860",
            "title": "Test App",
        }

        async def mock_get(*a, **kw):
            return httpx.Response(200, json=mock_data)

        with patch.object(httpx.AsyncClient, "get", mock_get):
            c = Client(LOCAL)
            status = await c.get_app_status("testapp")
            assert status is not None
            assert status["running"] is True
            assert status["ready_url"] == "http://127.0.0.1:7860"
            await c.close()

    async def test_not_found(self):
        async def mock_get(*a, **kw):
            return httpx.Response(404)

        with patch.object(httpx.AsyncClient, "get", mock_get):
            c = Client(LOCAL)
            status = await c.get_app_status("nonexistent")
            assert status is None
            await c.close()


class TestClientGetLogs:
    async def test_success(self):
        async def mock_get(*a, **kw):
            return httpx.Response(200, text="line1\nline2\nline3\n")

        with patch.object(httpx.AsyncClient, "get", mock_get):
            c = Client(LOCAL)
            logs = await c.get_logs("stdout.txt")
            assert logs == "line1\nline2\nline3\n"
            await c.close()

    async def test_not_found(self):
        async def mock_get(*a, **kw):
            return httpx.Response(404)

        with patch.object(httpx.AsyncClient, "get", mock_get):
            c = Client(LOCAL)
            logs = await c.get_logs("nonexistent.txt")
            assert logs == ""
            await c.close()


class TestClientRestart:
    async def test_success(self):
        async def mock_post(*a, **kw):
            return httpx.Response(200)

        with patch.object(httpx.AsyncClient, "post", mock_post):
            c = Client(LOCAL)
            assert await c.restart() is True
            await c.close()

    async def test_failure(self):
        async def mock_post(*a, **kw):
            return httpx.Response(500)

        with patch.object(httpx.AsyncClient, "post", mock_post):
            c = Client(LOCAL)
            assert await c.restart() is False
            await c.close()


class TestClientDiskUsage:
    async def test_success(self):
        async def mock_get(*a, **kw):
            return httpx.Response(200, text="1.2GB")

        with patch.object(httpx.AsyncClient, "get", mock_get):
            c = Client(LOCAL)
            du = await c.disk_usage("testapp")
            assert du == "1.2GB"
            await c.close()

    async def test_not_found(self):
        async def mock_get(*a, **kw):
            return httpx.Response(404)

        with patch.object(httpx.AsyncClient, "get", mock_get):
            c = Client(LOCAL)
            du = await c.disk_usage("nonexistent")
            assert du is None
            await c.close()


class TestExtractJsModuleFields:
    def test_extracts_fields(self):
        from pko.client import _extract_js_module_fields
        source = '''
module.exports = {
    title: "Test App",
    description: "A test app for pko",
    icon: "icon.png",
    version: "1.0.0",
    menu: async function() {}
};
'''
        result = _extract_js_module_fields(source)
        assert result is not None
        assert result["title"] == "Test App"
        assert result["description"] == "A test app for pko"
        assert result["icon"] == "icon.png"
        assert result["version"] == "1.0.0"

    def test_not_a_module(self):
        from pko.client import _extract_js_module_fields
        result = _extract_js_module_fields('{"title": "JSON"}')
        assert result is None

    def test_no_matching_fields(self):
        from pko.client import _extract_js_module_fields
        source = '''
module.exports = {
    menu: async function() { return []; }
};
'''
        result = _extract_js_module_fields(source)
        assert result is None


class TestClientListAppsStringItems:
    async def test_string_items(self):
        mock_data = [{"name": "comfyui"}, "bare-string-item"]
        req = httpx.Request("GET", "http://localhost:42000/pinokio/fs")

        async def mock_get(*a, **kw):
            return httpx.Response(200, json=mock_data, request=req)

        with patch.object(httpx.AsyncClient, "get", mock_get):
            c = Client(LOCAL)
            apps = await c.list_apps()
            assert len(apps) == 2
            assert apps[0]["name"] == "comfyui"
            assert apps[1]["name"] == "bare-string-item"
            await c.close()


class TestClientGetAppMetadata:

    async def test_status_and_du_both_fail(self):
        async def mock_get(*a, **kw):
            url = str(a[1]) if len(a) > 1 else ""
            if "/apps/status/" in url:
                return httpx.Response(404)
            if "/du/" in url:
                return httpx.Response(404)
            return httpx.Response(404)

        with patch.object(httpx.AsyncClient, "get", mock_get):
            c = Client(LOCAL)
            meta = await c.get_app_metadata("nonexistent")
            assert meta is None
            await c.close()

    async def test_found_via_status_endpoint(self):
        mock_status = {
            "app_id": "testapp",
            "title": "Test App",
            "description": "A test",
            "icon": "icon.png",
            "path": "/pinokio/api/testapp",
            "running": True,
        }

        async def mock_get(*a, **kw):
            url = str(a[1]) if len(a) > 1 else ""
            if "/du/" in url:
                return httpx.Response(200, text="1.2GB")
            return httpx.Response(200, json=mock_status)

        with patch.object(httpx.AsyncClient, "get", mock_get):
            c = Client(LOCAL)
            meta = await c.get_app_metadata("testapp")
            assert meta is not None
            assert meta.name == "testapp"
            assert meta.title == "Test App"
            assert meta.description == "A test"
            assert meta.running is True
            await c.close()

    async def test_falls_back_to_pinokio_js(self):
        mock_meta = {"title": "Test App", "description": "A test", "icon": "icon.png"}

        async def mock_get(*a, **kw):
            url = str(a[1]) if len(a) > 1 else ""
            if "/apps/status/" in url:
                return httpx.Response(404)
            if "/du/" in url:
                return httpx.Response(200, text="1.2GB")
            return httpx.Response(200, json=mock_meta)

        with patch.object(httpx.AsyncClient, "get", mock_get):
            c = Client(LOCAL)
            meta = await c.get_app_metadata("testapp")
            assert meta is not None
            assert meta.name == "testapp"
            assert meta.title == "Test App"
            assert meta.running is False
            await c.close()

    async def test_not_found(self):
        async def mock_get(*a, **kw):
            return httpx.Response(404)

        with patch.object(httpx.AsyncClient, "get", mock_get):
            c = Client(LOCAL)
            meta = await c.get_app_metadata("nonexistent")
            assert meta is None
            await c.close()


class TestWsClientCheckStatus:
    async def test_running(self):
        class FakeWs:
            async def send(self, data):
                pass

            def __aiter__(self):
                return self

            async def __anext__(self):
                if getattr(self, "_sent", False):
                    raise StopAsyncIteration
                self._sent = True
                return json.dumps({"data": True})

        class FakeConnect:
            def __init__(self, url):
                pass

            async def __aenter__(self):
                return FakeWs()

            async def __aexit__(self, *a):
                return False

        with patch("websockets.connect", FakeConnect):
            ws = WsClient(LOCAL)
            result = await ws.check_status("/api/testapp/index.json")
            assert result is True

    async def test_not_running(self):
        class FakeWs:
            async def send(self, data):
                pass

            def __aiter__(self):
                return self

            async def __anext__(self):
                if getattr(self, "_sent", False):
                    raise StopAsyncIteration
                self._sent = True
                return json.dumps({"data": False})

        class FakeConnect:
            def __init__(self, url):
                pass

            async def __aenter__(self):
                return FakeWs()

            async def __aexit__(self, *a):
                return False

        with patch("websockets.connect", FakeConnect):
            ws = WsClient(LOCAL)
            result = await ws.check_status("/api/testapp/index.json")
            assert result is False


#
# ── Integration tests (live pinokiod) ───────────────────────────────
#
# Target instance set via PKO_TEST_HOST / PKO_TEST_PORT env vars.
# Defaults to localhost:42000. Skip if unreachable — set env vars to point
# at any reachable pinokiod instance for remote testing.
#


def _test_instance() -> PinokioInstance:
    import os as _os
    host = _os.environ.get("PKO_TEST_HOST", "localhost")
    port = int(_os.environ.get("PKO_TEST_PORT", "42000"))
    return PinokioInstance(host=host, port=port, is_local=host in ("localhost", "127.0.0.1", "::1"))


@pytest.mark.integration
class TestLiveClient:
    """These tests require pinokiod running on a reachable host:port."""

    @pytest.fixture
    async def live_client(self):
        inst = _test_instance()
        c = Client(inst)
        ok = await c.health()
        if not ok:
            pytest.skip(f"pinokiod not running at {inst.host}:{inst.port}")
        yield c
        await c.close()

    async def test_health(self, live_client):
        ok = await live_client.health()
        assert ok is True

    async def test_info(self, live_client):
        info = await live_client.info()
        assert info.platform in ("linux", "win32", "darwin")
        assert isinstance(info.version, dict)
        assert isinstance(info.home, str)

    async def test_port(self, live_client):
        port = await live_client.get_port()
        assert isinstance(port, int)
        assert port > 0

    async def test_list_apps(self, live_client):
        apps = await live_client.list_apps()
        assert isinstance(apps, list)

    async def test_get_config(self, live_client):
        env = await live_client.get_config()
        assert isinstance(env, dict)

    async def test_get_app_status_for_nonexistent(self, live_client):
        status = await live_client.get_app_status("definitely-not-a-real-app-xyz")
        assert status is None
