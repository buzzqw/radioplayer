"""API client per RadioBrowser.info."""

import logging
from typing import List, Optional

import requests
import urllib3
from urllib3.exceptions import InsecureRequestWarning

from .m3u import M3UParser
from .models import RadioStation

logger = logging.getLogger("RadioPlayer")


class RadioBrowserAPI:
    """Client per la API pubblica RadioBrowser.info"""

    _BASE_URLS = [
        "https://all.api.radio-browser.info/json",
    ]
    HEADERS = {"User-Agent": "RadioPlayerM3U/3.0 azanzani@gmail.com"}
    _working_base: Optional[str] = None

    def __init__(self):
        self.last_error: Optional[str] = None
        self._cache: dict = {}
        self._cache_order: list = []
        self._insecure_base: Optional[str] = None

    def _get(self, path: str, params: dict) -> Optional[object]:
        """Tenta la richiesta sugli endpoint, cachando quello funzionante.

        Se la verifica del certificato TLS fallisce, riprova in modalità
        insicura (verify=False) anziché bloccare la ricerca.
        """
        bases = []
        if self._working_base:
            bases.append(self._working_base)
        bases += [b for b in self._BASE_URLS if b != self._working_base]

        for base in bases:
            url = f"{base}{path}"
            verify = base != self._insecure_base
            while True:
                try:
                    resp = requests.get(
                        url,
                        params=params,
                        headers=self.HEADERS,
                        timeout=5,
                        verify=verify,
                    )
                    resp.raise_for_status()
                    RadioBrowserAPI._working_base = base
                    self._insecure_base = None if verify else base
                    self.last_error = None
                    return resp.json()
                except requests.exceptions.SSLError as e:
                    if verify:
                        urllib3.disable_warnings(InsecureRequestWarning)
                        logger.warning(
                            "RadioBrowser: certificato TLS non valido su %s, "
                            "riprovo senza verifica", base,
                        )
                        verify = False
                        continue
                    self.last_error = f"Errore di rete: {e}"
                    logger.warning(f"RadioBrowser: {base} \u2014 {e}")
                except requests.Timeout:
                    self.last_error = "Timeout nella connessione a RadioBrowser"
                    logger.warning(f"RadioBrowser: timeout su {base}")
                except requests.RequestException as e:
                    self.last_error = f"Errore di rete: {e}"
                    logger.warning(f"RadioBrowser: {base} \u2014 {e}")
                except ValueError as e:
                    self.last_error = "Risposta non valida da RadioBrowser"
                    logger.warning(f"RadioBrowser: risposta non valida \u2014 {e}")
                break
        return None

    def search(self, query: str, limit: int = 20, offset: int = 0) -> List[RadioStation]:
        """Cerca stazioni per nome. Restituisce lista ordinata per popolarita'."""
        self.last_error = None
        if not query.strip():
            return []

        cache_key = (query.strip().lower(), limit, offset)
        if cache_key in self._cache:
            return list(self._cache[cache_key])

        params = {
            "name": query,
            "limit": limit,
            "offset": offset,
            "hidebroken": "true",
            "order": "votes",
            "reverse": "true",
        }
        data = self._get("/stations/search", params)
        if not isinstance(data, list):
            if data is not None:
                self.last_error = "Risposta non valida da RadioBrowser"
            return []

        results: List[RadioStation] = []
        for item in data:
            if not isinstance(item, dict):
                continue
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
        self._cache[cache_key] = list(results)
        self._cache_order.append(cache_key)
        while len(self._cache_order) > 32:
            old_key = self._cache_order.pop(0)
            self._cache.pop(old_key, None)
        return results
