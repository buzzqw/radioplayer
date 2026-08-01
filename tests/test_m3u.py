"""Tests for M3U parser."""

import tempfile
from pathlib import Path

import pytest

from radioplayer.m3u import M3UParser
from radioplayer.models import RadioStation


class TestM3UParser:
    def test_is_valid_url(self):
        assert M3UParser.is_valid_url("http://example.com/stream")
        assert M3UParser.is_valid_url("https://stream.example.com:8000/path")
        assert not M3UParser.is_valid_url("not-a-url")
        assert not M3UParser.is_valid_url("")
        assert not M3UParser.is_valid_url("not-a-url-at-all-and-no-scheme")

    def test_parse_simple_m3u(self):
        content = """#EXTM3U
#EXTINF:-1,Radio Deejay
http://example.com/deejay.mp3
#EXTINF:-1,Radio 105
http://example.com/105.mp3
"""
        parser = M3UParser()
        stations = parser.parse_string(content)

        assert len(stations) == 2
        assert stations[0].name == "Radio Deejay"
        assert stations[0].url == "http://example.com/deejay.mp3"
        assert stations[1].name == "Radio 105"
        assert stations[1].url == "http://example.com/105.mp3"

    def test_parse_with_group(self):
        content = """#EXTM3U
#EXTINF:-1 group-title="Italia",Radio Deejay
http://example.com/deejay.mp3
"""
        parser = M3UParser()
        stations = parser.parse_string(content)

        assert len(stations) == 1
        assert stations[0].name == "Radio Deejay"
        assert stations[0].group == "Italia"
        assert stations[0].metadata.get("group-title") == "Italia"

    def test_parse_with_extgrp(self):
        content = """#EXTM3U
#EXTGRP:Jazz
#EXTINF:-1,Jazz Radio
http://example.com/jazz.mp3
"""
        parser = M3UParser()
        stations = parser.parse_string(content)

        assert len(stations) == 1
        assert stations[0].group == "Jazz"

    def test_parse_with_logo(self):
        content = """#EXTM3U
#EXTINF:-1 tvg-logo="http://example.com/logo.png",Radio Deejay
http://example.com/deejay.mp3
"""
        parser = M3UParser()
        stations = parser.parse_string(content)

        assert len(stations) == 1
        assert stations[0].logo == "http://example.com/logo.png"

    def test_skip_invalid_urls(self):
        content = """#EXTM3U
#EXTINF:-1,Invalid Station
not-a-valid-url
#EXTINF:-1,Valid Station
http://example.com/valid.mp3
"""
        parser = M3UParser()
        stations = parser.parse_string(content)

        assert len(stations) == 1
        assert stations[0].name == "Valid Station"

    def test_parse_empty_file(self):
        parser = M3UParser()
        stations = parser.parse_string("")
        assert len(stations) == 0

    def test_parse_file_from_disk(self):
        content = """#EXTM3U
#EXTINF:-1,Test Radio
http://example.com/test.mp3
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.m3u', delete=False, encoding='utf-8') as f:
            f.write(content)
            tmp_path = f.name

        try:
            parser = M3UParser()
            stations = parser.parse_file(Path(tmp_path))
            assert len(stations) == 1
            assert stations[0].name == "Test Radio"
        finally:
            Path(tmp_path).unlink()
