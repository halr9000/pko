"""Tests for pko config module (named profiles, optional name)."""
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from pko.config import (
    load_config,
    save_config,
    add_profile,
    get_profile,
    set_default_profile,
    remove_profile,
    list_profiles,
    get_default_instance,
    DEFAULT_PROFILE_NAME,
)


@pytest.fixture(autouse=True)
def temp_config():
    """Use a temp config dir for each test."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_dir = Path(tmpdir) / "pko"
        config_dir.mkdir(parents=True)
        with (
            patch("pko.config.CONFIG_DIR", config_dir),
            patch("pko.config.CONFIG_FILE", config_dir / "config.json"),
        ):
            yield


class TestConfigLoadSave:
    def test_load_empty(self):
        cfg = load_config()
        assert cfg == {"profiles": {}, "default_profile": None}

    def test_save_and_load(self):
        cfg = {"profiles": {"test": {"host": "10.0.0.1", "port": 42000}}, "default_profile": "test"}
        save_config(cfg)
        loaded = load_config()
        assert loaded["profiles"]["test"]["host"] == "10.0.0.1"
        assert loaded["default_profile"] == "test"


class TestAddProfile:
    def test_defaults_to_default_name(self):
        add_profile("192.168.1.50", 42000)
        profile = get_profile()  # name defaults to "default" too
        assert profile["host"] == "192.168.1.50"
        assert profile["port"] == 42000

    def test_add_sets_default(self):
        add_profile("192.168.1.50", 42000)
        profiles = list_profiles()
        assert len(profiles) == 1
        assert profiles[0]["name"] == DEFAULT_PROFILE_NAME
        assert profiles[0]["default"] is True

    def test_named_profile(self):
        add_profile("10.0.0.1", 42000, name="secondary")
        profile = get_profile("secondary")
        assert profile["host"] == "10.0.0.1"

    def test_second_add_without_default_keeps_first_default(self):
        add_profile("10.0.0.1", 42000, name="a", set_default=True)
        add_profile("10.0.0.2", 42000, name="b", set_default=False)
        profiles = {p["name"]: p["default"] for p in list_profiles()}
        assert profiles["a"] is True
        assert profiles["b"] is False


class TestSetDefaultProfile:
    def test_set_known_profile(self):
        add_profile("10.0.0.1", 42000, name="a")
        add_profile("10.0.0.2", 42000, name="b", set_default=False)
        assert set_default_profile("b") is True
        profiles = {p["name"]: p["default"] for p in list_profiles()}
        assert profiles["b"] is True
        assert profiles["a"] is False

    def test_set_unknown_profile_fails(self):
        assert set_default_profile("nope") is False


class TestRemoveProfile:
    def test_remove_deletes_entry(self):
        add_profile("10.0.0.1", 42000, name="a")
        assert remove_profile("a") is True
        assert get_profile("a") is None

    def test_remove_unknown_fails(self):
        assert remove_profile("ghost") is False

    def test_removing_default_promotes_next(self):
        add_profile("10.0.0.1", 42000, name="a")
        add_profile("10.0.0.2", 42000, name="b", set_default=False)
        remove_profile("a")
        profiles = list_profiles()
        assert len(profiles) == 1
        assert profiles[0]["default"] is True


class TestDefaultInstance:
    @patch.dict(os.environ, {}, clear=True)
    def test_fallback_to_localhost(self):
        inst = get_default_instance()
        assert inst.host == "localhost"
        assert inst.port == 42000
        assert inst.source == "default"
        assert inst.is_local is True

    @patch.dict(os.environ, {"PKO_HOST": "10.0.0.5", "PKO_PORT": "43000"}, clear=True)
    def test_env_var_overrides(self):
        inst = get_default_instance()
        assert inst.host == "10.0.0.5"
        assert inst.port == 43000
        assert inst.source == "env"

    @patch.dict(os.environ, {"PINOKIO_HOST": "10.0.0.6", "PINOKIO_PORT": "42001"}, clear=True)
    def test_pinokio_env_var_fallback(self):
        inst = get_default_instance()
        assert inst.host == "10.0.0.6"
        assert inst.port == 42001

    @patch.dict(os.environ, {}, clear=True)
    def test_uses_default_profile(self):
        add_profile("10.0.0.7", 42000)
        inst = get_default_instance()
        assert inst.host == "10.0.0.7"
        assert inst.source == "config"

    @patch.dict(os.environ, {"PKO_HOST": "10.0.0.8", "PKO_PORT": "42000"}, clear=True)
    def test_env_overrides_default_profile(self):
        add_profile("10.0.0.7", 42000)
        inst = get_default_instance()
        assert inst.host == "10.0.0.8"
