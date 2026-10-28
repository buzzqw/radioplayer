"""Tests for RadioBrowser API client."""

from unittest.mock import patch

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
