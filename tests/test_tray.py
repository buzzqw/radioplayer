"""Tests for the system tray menu."""

import pytest

from radioplayer import tray as tray_module
from radioplayer.models import PlayerState, RadioStation, StreamInfo

pytestmark = pytest.mark.skipif(
    not tray_module.TRAY_AVAILABLE, reason="pystray non disponibile"
)


class FakePlayer:
    def __init__(self):
        self.state = PlayerState()
        self.state.is_playing = True
        self.state.playing_station_index = 0
        self.state.volume = 40
        self.state.stream_info = StreamInfo(artist="Daft Punk", song="One More Time")
        self.stations = [RadioStation("Radio Test", "http://example/stream")]

    def change_volume(self, delta):
        self.state.volume = max(0, min(100, self.state.volume + delta))


def _menu_texts(tray):
    return [str(item) for item in tray._build_menu().items]


def test_menu_shows_station_and_current_song():
    tray = tray_module.SystemTrayIcon(FakePlayer())

    texts = _menu_texts(tray)

    assert any("Radio Test" in text for text in texts)
    assert any("One More Time" in text for text in texts)


def test_volume_preset_updates_player_and_menu():
    player = FakePlayer()
    tray = tray_module.SystemTrayIcon(player)

    tray._set_volume(75)

    assert player.state.volume == 75
    assert any("Volume: 75%" in text for text in _menu_texts(tray))


def test_volume_is_clamped():
    player = FakePlayer()
    tray = tray_module.SystemTrayIcon(player)

    tray._set_volume(150)
    assert player.state.volume == 100

    tray._set_volume(-20)
    assert player.state.volume == 0


def test_tooltip_contains_title_and_volume():
    player = FakePlayer()
    tray = tray_module.SystemTrayIcon(player)

    tooltip = tray._make_tooltip()

    assert "Radio Test" in tooltip
    assert "One More Time" in tooltip
    assert "40%" in tooltip


def test_unavailable_message_empty_when_available():
    assert tray_module.tray_unavailable_message() == ""
