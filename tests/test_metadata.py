"""Tests for metadata history."""

import json
import tempfile
from pathlib import Path

import pytest

from radioplayer.metadata import MetadataHistory


class TestMetadataHistory:
    def test_add_and_retrieve(self):
        h = MetadataHistory(maxlen=100)
        h.add("Artist 1", "Song 1", "Station A")
        h.add("Artist 2", "Song 2", "Station B")

        last = h.get_last(10)
        assert len(last) == 2
        assert last[0]["artist"] == "Artist 1"
        assert last[1]["artist"] == "Artist 2"

    def test_maxlen(self):
        h = MetadataHistory(maxlen=3)
        for i in range(5):
            h.add(f"Artist {i}", f"Song {i}", "Station")

        last = h.get_last(10)
        assert len(last) == 3
        assert last[0]["artist"] == "Artist 2"

    def test_export_to_json(self):
        h = MetadataHistory()
        h.add("Artist", "Song", "Station")

        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            tmp_path = f.name

        try:
            h.export(Path(tmp_path))
            data = json.loads(Path(tmp_path).read_text())
            assert len(data) == 1
            assert data[0]["artist"] == "Artist"
            assert data[0]["song"] == "Song"
            assert data[0]["station"] == "Station"
            assert "timestamp" in data[0]
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_get_last_empty(self):
        h = MetadataHistory()
        assert h.get_last() == []

    def test_entry_has_timestamp(self):
        h = MetadataHistory()
        h.add("Artist", "Song", "Station")
        last = h.get_last(1)
        assert "timestamp" in last[0]
