"""Parser M3U esteso con supporto gruppi e attributi."""

import re
import logging
from pathlib import Path
from typing import List
from urllib.parse import urlparse

from .models import RadioStation

logger = logging.getLogger("RadioPlayer")


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
                with open(file_path, 'r', encoding='utf-8') as f:
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
                match = re.match(r'#EXTINF:(-?\d+)\s*(.*?),(.+)', line)
                if match:
                    duration, attrs_str, title = match.groups()
                    attrs = dict(re.findall(r'(\w+(?:-\w+)*)="([^"]+)"', attrs_str))
                    attrs['title'] = title.strip()
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
