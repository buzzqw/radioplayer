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

    def test_parse_with_comma_in_attributes_and_title(self):
        content = """#EXTM3U
#EXTINF:-1 group-title="Rock, Pop" tvg-name="A, B",Radio, The Best
http://example.com/rock.mp3
"""
        parser = M3UParser()
        stations = parser.parse_string(content)

        assert len(stations) == 1
        assert stations[0].name == "Radio, The Best"
        assert stations[0].group == "Rock, Pop"
        assert stations[0].metadata["tvg-name"] == "A, B"

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

    def test_serialize_preserves_attributes(self):
        stations = [
            RadioStation(
                name="Radio Deejay",
                url="http://example.com/deejay.mp3",
                metadata={
                    "title": "Radio Deejay",
                    "duration": "-1",
                    "group-title": "Italia",
                    "tvg-id": "deejay.it",
                    "tvg-logo": "http://example.com/logo.png",
                    "rb-uuid": "abc-123",
                },
            ),
            RadioStation(name="BBC Radio 1", url="http://example.com/bbc.mp3"),
        ]

        content = M3UParser.serialize(stations)
        parsed = M3UParser().parse_string(content)

        assert len(parsed) == 2
        assert parsed[0].name == "Radio Deejay"
        assert parsed[0].group == "Italia"
        assert parsed[0].metadata["tvg-id"] == "deejay.it"
        assert parsed[0].metadata["tvg-logo"] == "http://example.com/logo.png"
        assert parsed[0].metadata["rb-uuid"] == "abc-123"
        assert parsed[1].name == "BBC Radio 1"
        assert parsed[1].group == "Generale"

    def test_serialize_handles_duration_and_quotes(self):
        station = RadioStation(
            name='Radio "One"',
            url="http://example.com/one.mp3",
            metadata={"duration": "123", "group-title": 'A "B"'},
        )
        line = M3UParser.format_extinf(station)
        assert line.startswith("#EXTINF:123 ")
        assert 'group-title="A \'B\'"' in line
        assert line.endswith(',Radio "One"')


class TestDiscoverM3UFiles:
    def test_discover_deduplicates(self, tmp_path):
        from radioplayer.m3u import discover_m3u_files

        a = tmp_path / "a.m3u"
        b = tmp_path / "b.m3u"
        a.write_text("#EXTM3U\n", encoding="utf-8")
        b.write_text("#EXTM3U\n", encoding="utf-8")

        found = discover_m3u_files(tmp_path, tmp_path)
        assert len(found) == 2
        assert {p.name for p in found} == {"a.m3u", "b.m3u"}
