"""Monitor metadata ICY e cronologia brani."""

import json
import logging
import re
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional

import requests

logger = logging.getLogger("RadioPlayer")


class MetadataHistory:
    """Gestisce la cronologia dei brani riprodotti"""

    def __init__(self, maxlen: int = 100):
        self.history: deque = deque(maxlen=maxlen)
        logger.info(f"Inizializzata cronologia metadata (max {maxlen} elementi)")

    def add(self, artist: str, song: str, station: str):
        """Aggiunge un brano alla cronologia"""
        entry = {
            'artist': artist,
            'song': song,
            'station': station,
            'timestamp': datetime.now().isoformat()
        }
        self.history.append(entry)
        logger.debug(f"Aggiunto a cronologia: {artist} - {song} @ {station}")

    def export(self, path: Path):
        """Esporta la cronologia in JSON"""
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(list(self.history), f, indent=2, ensure_ascii=False)
            logger.info(f"Cronologia esportata in {path}")
        except OSError as e:
            logger.error(f"Errore esportazione cronologia: {e}")

    def load(self, path: Path):
        """Carica la cronologia da JSON, ignorando voci non valide."""
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                return
            self.history.clear()
            limit = self.history.maxlen or len(data)
            for entry in data[-limit:]:
                if not isinstance(entry, dict):
                    continue
                self.history.append({
                    'artist': str(entry.get('artist', '') or ''),
                    'song': str(entry.get('song', '') or ''),
                    'station': str(entry.get('station', '') or ''),
                    'timestamp': str(entry.get('timestamp', '') or ''),
                })
            logger.info(f"Cronologia caricata da {path} ({len(self.history)} voci)")
        except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
            logger.warning(f"Errore caricamento cronologia: {e}")

    def get_last(self, n: int = 10) -> List[Dict]:
        """Restituisce gli ultimi n brani"""
        return list(self.history)[-n:]


class MetadataMonitor:
    """Monitora i metadata dello stream radio"""

    def __init__(self, update_callback: Callable):
        self.update_callback = update_callback
        self.running = False
        self.current_url: Optional[str] = None
        self._response: Optional[requests.Response] = None
        self._generation = 0
        self.received_title = False
        logger.info("Inizializzato MetadataMonitor")

    def start(self, url: str):
        self._generation += 1
        self.current_url = url
        self.running = True
        self.received_title = False
        logger.info(f"Avviato monitoraggio metadata per: {url}")

    def stop(self):
        self._generation += 1
        self.running = False
        self.current_url = None
        resp = self._response
        if resp is not None:
            self._response = None
            try:
                resp.close()
            except Exception:
                pass
        logger.info("Fermato monitoraggio metadata")

    def monitor_loop(self):
        """Loop di monitoraggio metadata ICY"""
        generation = self._generation
        while (
            self.running
            and self.current_url
            and generation == self._generation
        ):
            resp = None
            try:
                headers = {'Icy-MetaData': '1', 'User-Agent': 'RadioPlayer/3.0'}
                resp = requests.get(
                    self.current_url, headers=headers, stream=True, timeout=5
                )
                self._response = resp

                icy_bitrate = resp.headers.get('icy-br', '')
                if icy_bitrate:
                    self.update_callback('bitrate', f"{icy_bitrate} kbps")

                metaint = resp.headers.get('icy-metaint')
                if not metaint:
                    logger.debug("Nessun icy-metaint, attendo...")
                    time.sleep(5)
                    continue

                metaint = int(metaint)
                logger.debug(f"ICY metaint: {metaint}")

                while self.running and generation == self._generation:
                    try:
                        audio_data = resp.raw.read(metaint)
                        if not audio_data:
                            break

                        meta_length_byte = resp.raw.read(1)
                        if not meta_length_byte:
                            break

                        meta_length = ord(meta_length_byte) * 16

                        if meta_length > 0:
                            metadata = resp.raw.read(meta_length)
                            metadata_str = metadata.decode('utf-8', errors='ignore')
                            title_match = re.search(r"StreamTitle='([^']*)'", metadata_str)
                            if title_match:
                                stream_title = title_match.group(1).strip()
                                if stream_title:
                                    self.received_title = True
                                    self.update_callback('stream_title', stream_title)
                                    logger.info(f"Metadata ICY: {stream_title}")
                    except Exception:
                        break

            except requests.RequestException as e:
                if self.running and generation == self._generation:
                    logger.warning(f"Errore richiesta metadata: {e}")
                    time.sleep(5)
            except Exception as e:
                if self.running and generation == self._generation:
                    logger.error(f"Errore monitor metadata: {e}", exc_info=True)
                    time.sleep(5)
            finally:
                if resp is not None:
                    try:
                        resp.close()
                    except Exception:
                        pass
                if self._response is resp:
                    self._response = None

        logger.info("Loop metadata terminato")
