"""API client per RadioBrowser.info."""

import logging
from typing import List, Optional

import requests
import urllib3

from .m3u import M3UParser
from .models import RadioStation

logger = logging.getLogger("RadioPlayer")

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class RadioBrowserAPI:
    """Client per la API pubblica RadioBrowser.info"""

    _BASE_URLS = [
        "https://all.api.radio-browser.info/json",
        "http://all.api.radio-browser.info/json",
    ]
    HEADERS = {"User-Agent": "RadioPlayerM3U/3.0 azanzani@gmail.com"}
    _working_base: Optional[str] = None

    def _get(self, path: str, params: dict) -> Optional[object]:
        """Tenta la richiesta su tutti gli endpoint, cachando quello funzionante."""
        bases = []
        if self._working_base:
            bases.append(self._working_base)
        bases += [b for b in self._BASE_URLS if b != self._working_base]

        for base in bases:
            for verify in (True, False):
                try:
                    resp = requests.get(
                        f"{base}{path}",
                        params=params,
                        headers=self.HEADERS,
                        timeout=8,
                        verify=verify,
                    )
                    resp.raise_for_status()
                    RadioBrowserAPI._working_base = base
                    return resp.json()
                except requests.exceptions.SSLError:
                    if verify:
                        continue
                    break
                except requests.Timeout:
                    logger.warning(f"RadioBrowser: timeout su {base}")
                    break
                except Exception as e:
                    logger.warning(f"RadioBrowser: {base} (verify={verify}) \u2014 {e}")
                    break
        return None

    def search(self, query: str, limit: int = 20) -> List[RadioStation]:
        """Cerca stazioni per nome. Restituisce lista ordinata per popolarita'."""
        if not query.strip():
            return []

        params = {
            "name": query,
            "limit": limit,
            "hidebroken": "true",
            "order": "votes",
            "reverse": "true",
        }
        data = self._get("/stations/search", params)
        if data is None:
            return []

        results: List[RadioStation] = []
        for item in data:
            url = item.get("url_resolved") or item.get("url", "")
            if not url or not M3UParser.is_valid_url(url):
                continue
            station = RadioStation(
                name=item.get("name", "Unknown").strip(),
                url=url,
                metadata={
                    "title": item.get("name", "").strip(),
                    "group-title": item.get("country", ""),
                    "tvg-logo": item.get("favicon", ""),
                    "rb-uuid": item.get("stationuuid", ""),
                    "rb-votes": str(item.get("votes", 0)),
                    "rb-bitrate": str(item.get("bitrate", 0)),
                    "rb-codec": item.get("codec", ""),
                    "rb-country": item.get("country", ""),
                    "rb-tags": item.get("tags", ""),
                },
            )
            results.append(station)

        logger.info(f"RadioBrowser: {len(results)} stazioni per '{query}'")
        return results
