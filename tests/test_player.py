"""Regression tests for player filters, deletion and UI rendering."""

import io
import time
from unittest.mock import patch

import pytest
from rich.console import Console

from radioplayer.config import DEFAULT_CONFIG
from radioplayer.models import RadioStation, UpdateFlags
from radioplayer.player import RadioPlayer


@pytest.fixture
def player(monkeypatch):
    config = dict(DEFAULT_CONFIG)
    config["favorites"] = []
    monkeypatch.setattr("radioplayer.player.load_config", lambda: config)
    monkeypatch.setattr("radioplayer.player.save_config", lambda cfg: None)
    monkeypatch.setattr(
        "radioplayer.player.MetadataHistory.load", lambda self, path: None
    )
    monkeypatch.setattr(RadioPlayer, "_check_mpv", lambda self: True)

    p = RadioPlayer(use_rich=False)
    p.stations = [
        RadioStation("Radio Deejay", "http://a/1", {"group-title": "Italia"}),
        RadioStation("Radio 105", "http://a/2", {"group-title": "Italia"}),
        RadioStation("BBC Radio 1", "http://a/3", {"group-title": "UK"}),
        RadioStation("Jazz FM", "http://a/4", {"group-title": "Jazz"}),
        RadioStation("Radio Italia", "http://a/5", {"group-title": "Italia"}),
    ]
    p._refresh_groups()
    p._invalidate_filtered()
    return p


class TestFilters:
    def test_group_filter_navigation_stays_in_group(self, player):
        player.group_filter = "Italia"
        player._invalidate_filtered()
        player._ensure_selection_visible()

        visible = [idx for idx, _ in player._get_visible_entries()]
        assert visible == [0, 1, 4]

        player.state.selected_station_index = 4
        player.change_selection(1)
        assert player.state.selected_station_index == 0
        player.change_selection(-1)
        assert player.state.selected_station_index == 4

    def test_local_search_selects_first_visible_match(self, player):
        player.group_filter = "Italia"
        player.local_search_mode = True
        player.local_search_query = "radio"
        player._update_local_search()

        assert player.state.selected_station_index == 0
        visible = [idx for idx, _ in player._get_visible_entries()]
        assert visible == [0, 1, 4]

    def test_select_hidden_number_clears_filters(self, player):
        player.group_filter = "Italia"
        player._invalidate_filtered()

        player.select_by_number(3)  # BBC Radio 1, fuori dal gruppo Italia

        assert player.group_filter is None
        assert player.state.selected_station_index == 2

    def test_favorites_only_filter(self, player):
        player.favorites = {"http://a/4"}
        player.show_favorites_only = True
        player._invalidate_filtered()

        visible = [idx for idx, _ in player._get_visible_entries()]
        assert visible == [3]

    def test_play_refuses_when_filter_hides_everything(self, player):
        player.show_favorites_only = True
        player._invalidate_filtered()

        with patch.object(player.mpv_controller, "start", side_effect=AssertionError):
            player.play_selected()

        assert "Nessuna stazione visibile" in player.temp_message


class TestDeletion:
    def test_delete_requires_confirmation(self, player, monkeypatch, tmp_path):
        player.m3u_file_path = tmp_path / "stations.m3u"
        monkeypatch.setattr(player, "_save_m3u_file", lambda: None)
        monkeypatch.setattr(player, "_save_user_config", lambda: None)
        player.state.selected_station_index = 1

        player.remove_selected_station()
        assert len(player.stations) == 5
        assert player._pending_delete is not None

        player.remove_selected_station()
        assert len(player.stations) == 4
        assert player._pending_delete is None
        assert all(s.name != "Radio 105" for s in player.stations)

    def test_delete_cancelled_by_other_key(self, player, tmp_path):
        player.m3u_file_path = tmp_path / "stations.m3u"
        player.state.selected_station_index = 1
        player.remove_selected_station()
        player.cancel_pending_delete()
        assert player._pending_delete is None
        assert len(player.stations) == 5


class TestGroupPicker:
    def test_open_and_apply_group(self, player):
        player.open_group_picker()
        assert player.show_group_overlay is True

        choices = player._group_choices()
        player.group_overlay_idx = choices.index("UK")
        player.confirm_group_selection()

        assert player.group_filter == "UK"
        assert player.show_group_overlay is False
        assert player.state.selected_station_index == 2


class TestPersistence:
    def test_load_m3u_restores_last_station(self, player, tmp_path):
        path = tmp_path / "stations.m3u"
        path.write_text(
            "#EXTM3U\n"
            "#EXTINF:-1 group-title=\"Italia\",One\nhttp://a/1\n"
            "#EXTINF:-1 group-title=\"Italia\",Two\nhttp://a/2\n",
            encoding="utf-8",
        )
        player._last_station_url = "http://a/2"
        player.load_m3u(path)
        assert player.state.selected_station_index == 1

    def test_save_m3u_preserves_attributes(self, player, tmp_path):
        from radioplayer.m3u import M3UParser

        player.m3u_file_path = tmp_path / "out.m3u"
        player.stations = [
            RadioStation(
                "Radio Deejay", "http://a/1",
                {"group-title": "Italia", "tvg-id": "deejay.it",
                 "tvg-logo": "http://logo.png", "duration": "-1"},
            )
        ]
        player._save_m3u_file()

        parsed = M3UParser().parse_file(player.m3u_file_path)
        assert parsed[0].group == "Italia"
        assert parsed[0].metadata["tvg-id"] == "deejay.it"
        assert parsed[0].metadata["tvg-logo"] == "http://logo.png"


class TestInputRouting:
    def feed(self, player, keys, monkeypatch):
        iterator = iter(keys)

        def fake_get_char():
            try:
                return next(iterator)
            except StopIteration:
                player.running = False
                return None

        monkeypatch.setattr(player, "get_char", fake_get_char)
        player.running = True
        player.handle_input()

    def test_number_input_selects_station(self, player, monkeypatch):
        self.feed(player, ["3", "\r"], monkeypatch)
        assert player.state.selected_station_index == 2

    def test_next_station_key(self, player, monkeypatch):
        self.feed(player, ["n"], monkeypatch)
        assert player.state.selected_station_index == 1
        self.feed(player, ["N"], monkeypatch)
        assert player.state.selected_station_index == 0

    def test_group_picker_keyboard(self, player, monkeypatch):
        self.feed(player, ["g", "DOWN", "\r"], monkeypatch)
        assert player.group_filter == "Italia"

    def test_favorites_key(self, player, monkeypatch):
        self.feed(player, ["f"], monkeypatch)
        assert player.show_favorites_only is True

    def test_delete_twice_keyboard(self, player, monkeypatch, tmp_path):
        player.m3u_file_path = tmp_path / "stations.m3u"
        monkeypatch.setattr(player, "_save_m3u_file", lambda: None)
        player.state.selected_station_index = 1
        self.feed(player, ["d", "d"], monkeypatch)
        assert len(player.stations) == 4

    def test_undo_delete_keyboard(self, player, monkeypatch, tmp_path):
        player.m3u_file_path = tmp_path / "stations.m3u"
        monkeypatch.setattr(player, "_save_m3u_file", lambda: True)
        player.state.selected_station_index = 1
        self.feed(player, ["d", "d"], monkeypatch)
        assert len(player.stations) == 4
        self.feed(player, ["u"], monkeypatch)
        assert len(player.stations) == 5
        assert any(s.name == "Radio 105" for s in player.stations)


class TestSearchPagination:
    def test_load_more_appends_results(self, player, monkeypatch):
        pages = {
            0: [RadioStation(f"Radio {i}", f"http://b/{i}") for i in range(20)],
            20: [RadioStation(f"Radio {i}", f"http://b/{i}") for i in range(20, 25)],
        }
        monkeypatch.setattr(
            player.radio_browser, "search",
            lambda query, limit=20, offset=0: pages.get(offset, []),
        )
        player.search_mode = True
        player.search_query = "radio"

        player._do_search()
        assert len(player.search_results) == 20
        assert player.search_has_more is True

        player._do_search_more()
        assert len(player.search_results) == 25
        assert player.search_has_more is False


class TestUIRendering:
    def make_console(self, player, width=80, height=24):
        player.console = Console(
            file=io.StringIO(), width=width, height=height,
            force_terminal=False, color_system=None,
        )
        player._last_console_size = None
        player.pending_updates = UpdateFlags.FULL

    def test_main_layout_smoke(self, player):
        for width, height in ((60, 18), (80, 24), (120, 40)):
            self.make_console(player, width, height)
            player.state.is_playing = True
            player.state.playing_station_index = 2
            player.state.stream_info = player.state.stream_info.replace(
                artist="Artist", song="Song", audio_bitrate="128 kbps",
                codec="MP3", buffer_status="80%",
            )
            assert player._render_rich() is not None

    def test_markup_in_names_does_not_break(self, player):
        self.make_console(player)
        player.stations[0] = RadioStation(
            "[LIVE] Radio [x]", "http://a/1", {"group-title": "[G]"}
        )
        player._invalidate_filtered()
        player.local_search_mode = True
        player.local_search_query = "["
        player._update_local_search()
        player.temp_message = "[boom]"
        player.temp_message_time = time.time()
        assert player._render_rich() is not None

    def test_overlays_smoke(self, player):
        self.make_console(player)

        player.show_help_overlay = True
        assert player._render_rich() is not None
        player.show_help_overlay = False

        player.show_group_overlay = True
        assert player._render_rich() is not None
        player.show_group_overlay = False

        player.history.add("Artist", "Song", "Station")
        player.show_history_overlay = True
        assert player._render_rich() is not None
        player.show_history_overlay = False

        player.search_mode = True
        player.search_results = player.stations[:2]
        player.search_query = "radio"
        assert player._render_rich() is not None
