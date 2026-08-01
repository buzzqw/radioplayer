"""Tests for configuration persistence."""

import pytest

from radioplayer.config import load_config, save_config, DEFAULT_CONFIG, CONFIG_FILE


@pytest.fixture
def clean_config(monkeypatch, tmp_path):
    """Override CONFIG_FILE to a temp path."""
    monkeypatch.setattr("radioplayer.config.CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr("radioplayer.config.CONFIG_DIR", tmp_path)


class TestConfig:
    def test_load_default_when_no_file(self, clean_config):
        config = load_config()
        assert config == DEFAULT_CONFIG

    def test_load_saved_config(self, clean_config):
        custom = {"volume": 80, "show_song_popups": False, "logging_enabled": True}
        save_config(custom)
        loaded = load_config()
        assert loaded["volume"] == 80
        assert loaded["show_song_popups"] is False
        assert loaded["logging_enabled"] is True

    def test_load_partial_config(self, clean_config):
        save_config({"volume": 30})
        loaded = load_config()
        assert loaded["volume"] == 30
        assert loaded["show_song_popups"] == DEFAULT_CONFIG["show_song_popups"]
        assert loaded["logging_enabled"] == DEFAULT_CONFIG["logging_enabled"]

    def test_save_creates_directory(self, clean_config, tmp_path, monkeypatch):
        nested = tmp_path / "nested" / "config"
        monkeypatch.setattr("radioplayer.config.CONFIG_FILE", nested / "config.json")
        monkeypatch.setattr("radioplayer.config.CONFIG_DIR", nested)
        save_config({"volume": 60})
        assert (nested / "config.json").exists()
