"""Tests for RadioBrowser API client."""

from unittest.mock import patch

import requests

from radioplayer.radio_browser import RadioBrowserAPI


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload
        self.headers = {}

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def make_payload(n=20, offset=0):
    return [
        {
            "name": f"Radio {offset + i}",
            "url_resolved": f"http://example.com/{offset + i}.mp3",
            "country": "Italy",
            "stationuuid": f"uuid-{offset + i}",
            "votes": 100 - i,
            "bitrate": 128,
            "codec": "MP3",
            "favicon": "",
            "tags": "pop",
        }
        for i in range(n)
    ]


def test_search_passes_offset_and_caches():
    api = RadioBrowserAPI()
    with patch("radioplayer.radio_browser.requests.get") as get:
        get.return_value = FakeResponse(make_payload(20, 40))

        first = api.search("radio", limit=20, offset=40)
        second = api.search("radio", limit=20, offset=40)

        assert len(first) == 20
        assert len(second) == 20
        assert get.call_count == 1
        params = get.call_args.kwargs["params"]
        assert params["offset"] == 40
        assert params["limit"] == 20


def test_search_different_query_hits_network():
    api = RadioBrowserAPI()
    with patch("radioplayer.radio_browser.requests.get") as get:
        get.return_value = FakeResponse(make_payload(5))
        assert len(api.search("one")) == 5
        assert len(api.search("two")) == 5
        assert get.call_count == 2


def test_search_invalid_payload_sets_error():
    api = RadioBrowserAPI()
    with patch("radioplayer.radio_browser.requests.get") as get:
        get.return_value = FakeResponse({"error": "bad"})
        assert api.search("radio") == []
        assert api.last_error is not None


def test_search_falls_back_on_certificate_error():
    """Se il certificato TLS non è verificabile, riprova senza verifica."""
    api = RadioBrowserAPI()
    api._insecure_base = None
    with patch("radioplayer.radio_browser.requests.get") as get:
        get.side_effect = [
            requests.exceptions.SSLError("certificate verify failed"),
            FakeResponse(make_payload(3)),
        ]

        result = api.search("radio24")

        assert len(result) == 3
        assert get.call_count == 2
        assert get.call_args_list[0].kwargs["verify"] is True
        assert get.call_args_list[1].kwargs["verify"] is False
        assert api._insecure_base is not None
