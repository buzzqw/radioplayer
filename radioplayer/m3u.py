"""Parser M3U esteso con supporto gruppi e attributi."""

import logging
import re
from pathlib import Path
from typing import Iterable, List
from urllib.parse import urlparse

from .models import RadioStation

logger = logging.getLogger("RadioPlayer")

# Attributi che compaiono piu' spesso: mantenerli in testa rende il file leggibile.
_COMMON_ATTRS = ("tvg-id", "tvg-name", "tvg-logo", "group-title")
_ATTR_NAME = re.compile(r"^[A-Za-z0-9_-]+$")


def discover_m3u_files(*directories: Path) -> List[Path]:
    """Cerca i file .m3u nelle directory indicate, senza duplicati."""
    found = {}
    for directory in directories:
        try:
            for f in sorted(directory.glob("*.m3u")):
                found[f.resolve()] = f
        except OSError:
            continue
    return list(found.values())


class M3UParser:
    """Parser M3U con supporto attributi estesi e gruppi"""

    @staticmethod
    def is_valid_url(url: str) -> bool:
        """Verifica se l'URL e' valido"""
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except Exception:
            return False

    def parse_file(self, file_path: Path) -> List[RadioStation]:
        """Analizza un file M3U e restituisce le stazioni"""
        logger.info(f"Parsing file M3U: {file_path}")

        try:
            try:
                # utf-8-sig rimuove l'eventuale BOM iniziale.
                with open(file_path, 'r', encoding='utf-8-sig') as f:
                    content = f.read()
            except UnicodeDecodeError:
                logger.warning("UTF-8 fallito, uso latin-1")
                with open(file_path, 'r', encoding='latin-1') as f:
                    content = f.read()

            return self.parse_string(content)

        except Exception as e:
            logger.error(f"Errore lettura file M3U: {e}", exc_info=True)
            raise

    def parse_string(self, content: str) -> List[RadioStation]:
        """Analizza il contenuto M3U"""
        stations = []
        lines = [line.strip() for line in content.split('\n')]

        current_attrs = {}

        for line in lines:
            if line.startswith('#EXTINF:'):
                parsed = self._parse_extinf(line)
                if parsed:
                    duration, attrs, title = parsed
                    attrs['title'] = title
                    attrs['duration'] = duration
                    # Merge preserva gli attributi precedenti (#EXTGRP ecc.)
                    current_attrs = {**current_attrs, **attrs}
                    logger.debug(f"Parsed EXTINF: {attrs}")
                else:
                    logger.warning(f"EXTINF non parsabile: {line}")

            elif line.startswith('#EXTGRP:'):
                group = line.replace('#EXTGRP:', '').strip()
                current_attrs['group-title'] = group

            elif line and not line.startswith('#'):
                if self.is_valid_url(line):
                    name = current_attrs.get('title', f'Station {len(stations)+1}')
                    station = RadioStation(
                        name=name,
                        url=line,
                        metadata=current_attrs.copy()
                    )
                    stations.append(station)
                    logger.debug(f"Aggiunta stazione: {name}")
                    current_attrs = {}
                else:
                    logger.warning(f"URL non valido ignorato: {line}")

        logger.info(f"Parsate {len(stations)} stazioni")
        return stations

    @staticmethod
    def _parse_extinf(line: str):
        """Estrae (durata, attributi, titolo) da una riga #EXTINF.

        Il titolo puo' contenere virgole e gli attributi possono avere virgole
        tra virgolette: la virgola separatrice va cercata fuori dalle quote.
        """
        body = line[len("#EXTINF:"):]
        match = re.match(r"\s*(-?\d+)\s*(.*)", body)
        if not match:
            return None

        duration, rest = match.groups()
        in_quotes = False
        comma = -1
        for index, char in enumerate(rest):
            if char == '"':
                in_quotes = not in_quotes
            elif char == "," and not in_quotes:
                comma = index
                break
        if comma < 0:
            return None

        attrs_str = rest[:comma]
        title = rest[comma + 1:].strip()
        if not title:
            return None

        attrs = dict(re.findall(r'([\w-]+)="([^"]*)"', attrs_str))
        return duration, attrs, title

    @staticmethod
    def format_extinf(station: RadioStation) -> str:
        """Restituisce la riga #EXTINF preservando gli attributi della stazione."""
        attrs = []
        metadata = station.metadata or {}

        ordered = [k for k in _COMMON_ATTRS if metadata.get(k)]
        extra = sorted(
            k for k in metadata
            if k not in _COMMON_ATTRS and k not in ("title", "duration")
            and metadata.get(k) and _ATTR_NAME.match(k)
        )
        for key in ordered + extra:
            value = str(metadata[key]).replace('"', "'").replace("\n", " ").strip()
            if value:
                attrs.append(f'{key}="{value}"')

        duration = str(metadata.get("duration", "-1")).strip() or "-1"
        if not re.match(r"^-?\d+$", duration):
            duration = "-1"

        suffix = (" " + " ".join(attrs)) if attrs else ""
        name = station.name.replace("\r", " ").replace("\n", " ").strip()
        return f"#EXTINF:{duration}{suffix},{name}"

    @classmethod
    def serialize(cls, stations: Iterable[RadioStation]) -> str:
        """Serializza le stazioni in un file M3U completo."""
        lines = ["#EXTM3U"]
        for station in stations:
            lines.append(cls.format_extinf(station))
            lines.append(station.url)
        return "\n".join(lines) + "\n"
