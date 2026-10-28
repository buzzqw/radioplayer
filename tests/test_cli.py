"""Tests for the command line entry point."""

import pytest

from radioplayer.__main__ import main


def test_version_exits_zero(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert "Radio Player M3U v" in capsys.readouterr().out


def test_help_exits_zero(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    assert "--no-tray" in capsys.readouterr().out


def test_list_stations(tmp_path, capsys):
    playlist = tmp_path / "stations.m3u"
    playlist.write_text(
        "#EXTM3U\n"
        "#EXTINF:-1 group-title=\"Italia\",Radio Uno\nhttp://a/1\n"
        "#EXTINF:-1 group-title=\"UK\",Radio Two\nhttp://a/2\n",
        encoding="utf-8",
    )

    code = main(["--list", str(playlist)])
    output = capsys.readouterr().out

    assert code == 0
    assert "Radio Uno" in output
    assert "Radio Two" in output
    assert "2 stazioni" in output


def test_resolver_default_does_not_use_last_playlist(
    tmp_path, monkeypatch, capsys
):
    import radioplayer.__main__ as cli

    first = tmp_path / "radio.m3u"
    second = tmp_path / "stations.m3u"
    first.write_text("#EXTM3U\n", encoding="utf-8")
    second.write_text("#EXTM3U\n", encoding="utf-8")

    monkeypatch.setattr(cli, "find_m3u_files", lambda: [first, second])
    monkeypatch.setattr(cli, "load_config", lambda: {"last_m3u": str(second)})
    monkeypatch.setattr("builtins.input", lambda prompt: "1")

    assert cli._resolve_m3u_file(None) == first


def test_resolver_last_flag_uses_last_playlist(tmp_path, monkeypatch):
    import radioplayer.__main__ as cli

    first = tmp_path / "radio.m3u"
    second = tmp_path / "stations.m3u"
    first.write_text("#EXTM3U\n", encoding="utf-8")
    second.write_text("#EXTM3U\n", encoding="utf-8")

    monkeypatch.setattr(cli, "find_m3u_files", lambda: [first, second])
    monkeypatch.setattr(cli, "load_config", lambda: {"last_m3u": str(second)})

    assert cli._resolve_m3u_file(None, use_last=True) == second
