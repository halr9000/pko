"""Tests for pko models."""
from pko.models import PinokioInstance, SystemInfo, WsPacket


class TestPinokioInstance:
    def test_base_url(self):
        inst = PinokioInstance(host="localhost", port=42000)
        assert inst.base_url == "http://localhost:42000"

    def test_ws_url(self):
        inst = PinokioInstance(host="192.168.1.50", port=42000)
        assert inst.ws_url == "ws://192.168.1.50:42000"

    def test_is_local(self):
        for host in ("localhost", "127.0.0.1", "::1"):
            inst = PinokioInstance(host=host, port=42000, is_local=True)
            assert inst.is_local is True

    def test_source_default(self):
        inst = PinokioInstance(host="localhost", port=42000)
        assert inst.source == "manual"


class TestSystemInfo:
    def test_defaults(self):
        info = SystemInfo()
        assert info.platform == ""
        assert info.arch == ""
        assert info.memory == {}

    def test_from_data(self):
        info = SystemInfo(
            platform="linux",
            arch="x64",
            version="8.0.36",
            memory={"total": 16000000, "free": 8000000},
            gpu={"model": "Intel"},
            home="/home/user/pinokio",
        )
        assert info.platform == "linux"
        assert info.memory["total"] == 16000000
        assert info.home == "/home/user/pinokio"


class TestWsPacket:
    def test_defaults(self):
        pkt = WsPacket(type="stream")
        assert pkt.type == "stream"
        assert pkt.id == ""
        assert pkt.data == {}
        assert pkt.index == 0

    def test_with_data(self):
        pkt = WsPacket(type="result", id="abc", data={"output": "hello"}, index=1)
        assert pkt.id == "abc"
        assert pkt.data["output"] == "hello"