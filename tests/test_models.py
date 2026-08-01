"""Tests for data models."""

import time

import pytest

from radioplayer.models import (
    RadioStation,
    StreamInfo,
    PlayerState,
    UpdateFlags,
)


class TestRadioStation:
    def test_creation(self):
        s = RadioStation(name="Test", url="http://example.com/stream")
        assert s.name == "Test"
        assert s.url == "http://example.com/stream"
        assert s.group == "Generale"
        assert s.logo is None

    def test_with_metadata(self):
        s = RadioStation(
            name="Test",
            url="http://example.com/stream",
            metadata={"group-title": "Italia", "tvg-logo": "http://logo.png"},
        )
        assert s.group == "Italia"
        assert s.logo == "http://logo.png"

    def test_str(self):
        s = RadioStation(name="Test", url="http://example.com/stream")
        assert str(s) == "Test"


class TestStreamInfo:
    def test_default_values(self):
        si = StreamInfo()
        assert si.artist == ""
        assert si.song == ""
        assert si.title == ""

    def test_get_song_time_not_playing(self):
        si = StreamInfo(song_start_time=time.time())
        assert si.get_song_time(False, False) == "00:00"

    def test_get_song_time_playing(self):
        si = StreamInfo(song_start_time=time.time() - 65)
        elapsed = si.get_song_time(True, False)
        assert elapsed == "01:05"

    def test_immutable(self):
        si = StreamInfo(artist="Old")
        with pytest.raises(Exception):
            si.artist = "New"

    def test_replace(self):
        si = StreamInfo(artist="Old", song="OldSong")
        new_si = si.replace(artist="New", bitrate="128 kbps")
        assert new_si.artist == "New"
        assert new_si.song == "OldSong"
        assert new_si.bitrate == "128 kbps"
        assert si.artist == "Old"


class TestPlayerState:
    def test_default_values(self):
        ps = PlayerState()
        assert ps.is_playing is False
        assert ps.is_paused is False
        assert ps.volume == 50
        assert ps.selected_station_index == 0
        assert ps.playing_station_index == -1


class TestUpdateFlags:
    def test_flags_combination(self):
        flags = UpdateFlags.TIMER | UpdateFlags.STATUS
        assert flags & UpdateFlags.TIMER
        assert flags & UpdateFlags.STATUS
        assert not (flags & UpdateFlags.SONG)

    def test_full_includes_all(self):
        assert UpdateFlags.FULL & UpdateFlags.TIMER
        assert UpdateFlags.FULL & UpdateFlags.STATUS
        assert UpdateFlags.FULL & UpdateFlags.SONG
        assert UpdateFlags.FULL & UpdateFlags.STATIONS

    def test_none_is_zero(self):
        assert UpdateFlags.NONE.value == 0
