#!/usr/bin/env python3
"""
Radio Player M3U - VERSIONE FINALE (UI POLISHED)

Copyright (C) 2025 Andres Zanzani <azanzani@gmail.com>

CORREZIONI APPLICATE:
1. UI: Scritta 'LOG' ora in GRASSETTO ROSSO quando attiva.
2. UI: Layout Status mantenuto a size=6 per i titoli.
3. LOGIC: Fix definitivo titoli metadata e refresh.
"""

import subprocess
import time
import re
import sys
import os
import select
import termios
import tty
import signal
import requests
import socket
import json
import platform
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from urllib.parse import urlparse
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple
from concurrent.futures import ThreadPoolExecutor, Future
from enum import Flag, auto
import queue
import threading
from collections import deque

# Rich UI imports (con fallback)
try:
    from rich.console import Console
    from rich.live import Live
    from rich.panel import Panel
    from rich.table import Table
    from rich.layout import Layout
    from rich.text import Text
    from rich.progress import Progress, BarColumn, TextColumn
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    # Stub classes per type hints quando Rich non disponibile
    Console = None
    Live = None
    Panel = None
    Table = None
    Layout = None
    Text = None
    print("⚠️  Rich non disponibile. Installa con: pip install rich")
    print("    Verrà usata l'interfaccia TUI base.\n")

# Importazioni condizionali per Windows
if platform.system() == "Windows":
    import msvcrt
    try:
        import win32gui
        import win32con
        WIN32_AVAILABLE = True
    except ImportError:
        WIN32_AVAILABLE = False
else:
    WIN32_AVAILABLE = False

# ============================================================================
# CONFIGURAZIONE LOGGING
# ============================================================================

def setup_logging(log_file: Path = None, 
                  level: int = logging.INFO) -> logging.Logger:
    """Configura il sistema di logging con rotazione file"""
    
    # Se non specificato, usa directory corrente
    if log_file is None:
        log_file = Path.cwd() / "radio_player.log"
    
    logger = logging.getLogger("RadioPlayer")
    logger.setLevel(level)
    
    # Previeni duplicazione handlers
    if logger.handlers:
        return logger
    
    # Inizialmente usa NullHandler per non creare file
    null_handler = logging.NullHandler()
    logger.addHandler(null_handler)
    
    # Salva il path del file per dopo
    logger._log_file_path = log_file
    
    # Console handler solo per errori critici
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.ERROR)
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
    )
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    return logger

logger = setup_logging()

# ============================================================================
# FLAGS PER AGGIORNAMENTI UI
# ============================================================================

class UpdateFlags(Flag):
    """Flag per tracciare quali parti dell'UI devono essere aggiornate"""
    NONE = 0
    TIMER = auto()
    STATUS = auto()
    SONG = auto()
    STATIONS = auto()
    INPUT = auto()
    TECHNICAL = auto()
    FULL = TIMER | STATUS | SONG | STATIONS | INPUT | TECHNICAL

# ============================================================================
# MODELLI DATI
# ============================================================================

@dataclass
class RadioStation:
    """Rappresenta una stazione radio con metadata estesi"""
    name: str
    url: str
    metadata: Dict[str, str] = field(default_factory=dict)
    
    def __str__(self) -> str:
        return self.name
    
    @property
    def group(self) -> str:
        """Gruppo della stazione (se presente in metadata)"""
        return self.metadata.get('group-title', 'Generale')
    
    @property
    def logo(self) -> Optional[str]:
        """URL logo della stazione"""
        return self.metadata.get('tvg-logo')

@dataclass
class StreamInfo:
    """Informazioni sullo stream corrente"""
    artist: str = ""
    song: str = ""
    title: str = ""
    bitrate: str = ""
    audio_bitrate: str = ""
    codec: str = ""
    buffer_status: str = ""
    cache_duration: str = ""
    start_time: Optional[float] = None
    song_start_time: Optional[float] = None
    pause_start_time: Optional[float] = None
    total_pause_time: float = 0.0
    
    def get_song_time(self, is_playing: bool, is_paused: bool) -> str:
        """Calcola il tempo del brano corrente"""
        if not self.song_start_time or not is_playing:
            return "00:00"
        
        if is_paused and self.pause_start_time:
            elapsed = self.pause_start_time - self.song_start_time - self.total_pause_time
        else:
            elapsed = time.time() - self.song_start_time - self.total_pause_time
        
        elapsed = max(0, elapsed)
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)
        return f"{minutes:02d}:{seconds:02d}"
    
    def get_uptime(self, is_playing: bool, is_paused: bool) -> str:
        """Calcola l'uptime della riproduzione"""
        if not self.start_time or not is_playing or is_paused:
            return "00:00"
        
        elapsed = time.time() - self.start_time
        hours = int(elapsed // 3600)
        minutes = int((elapsed % 3600) // 60)
        seconds = int(elapsed % 60)
        
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"

@dataclass
class PlayerState:
    """Stato completo del player"""
    is_playing: bool = False
    is_paused: bool = False
    is_muted: bool = False
    volume: int = 50
    selected_station_index: int = 0
    playing_station_index: int = -1
    stream_info: StreamInfo = field(default_factory=StreamInfo)
    show_song_popups: bool = True

# ============================================================================
# CRONOLOGIA METADATA
# ============================================================================

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
        except Exception as e:
            logger.error(f"Errore esportazione cronologia: {e}")
    
    def get_last(self, n: int = 10) -> List[Dict]:
        """Restituisce gli ultimi n brani"""
        return list(self.history)[-n:]

# ============================================================================
# PARSER M3U ESTESO
# ============================================================================

class M3UParser:
    """Parser M3U con supporto attributi estesi e gruppi"""
    
    @staticmethod
    def is_valid_url(url: str) -> bool:
        """Verifica se l'URL è valido"""
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except Exception as e:
            logger.warning(f"URL non valido: {url} - {e}")
            return False
    
    def parse_file(self, file_path: Path) -> List[RadioStation]:
        """Analizza un file M3U e restituisce le stazioni"""
        logger.info(f"Parsing file M3U: {file_path}")
        
        try:
            # Prova UTF-8, poi fallback a latin-1
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
                # Parse: #EXTINF:duration attr1="val1" attr2="val2",Title
                match = re.match(r'#EXTINF:(-?\d+)\s*(.*?),(.+)', line)
                if match:
                    duration, attrs_str, title = match.groups()
                    
                    # Estrai attributi chiave="valore"
                    attrs = dict(re.findall(r'(\w+(?:-\w+)*)="([^"]+)"', attrs_str))
                    attrs['title'] = title.strip()
                    attrs['duration'] = duration
                    current_attrs = attrs
                    
                    logger.debug(f"Parsed EXTINF: {attrs}")
                else:
                    logger.warning(f"EXTINF non parsabile: {line}")
                    
            elif line.startswith('#EXTGRP:'):
                # Gruppo alternativo
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

# ============================================================================
# CLIENT IPC MPV MIGLIORATO
# ============================================================================

class MPVIPCClient:
    """Client IPC per comunicare con MPV tramite socket"""
    
    def __init__(self, socket_path: str):
        self.socket_path = socket_path
        self._request_id = 0
        logger.info(f"Inizializzato MPV IPC client: {socket_path}")
    
    def send_command(self, command: str, *args, timeout: float = 2.0) -> Optional[Any]:
        """Invia un comando a MPV e attende la risposta"""
        self._request_id += 1
        request = {
            "command": [command, *args],
            "request_id": self._request_id
        }
        
        logger.debug(f"IPC send: {request}")
        
        try:
            if platform.system() == "Windows":
                return self._send_windows(request, timeout)
            else:
                return self._send_unix(request, timeout)
        except Exception as e:
            logger.error(f"Errore IPC command '{command}': {e}")
            return None
    
    def _send_unix(self, request: dict, timeout: float) -> Optional[Any]:
        """Invia comando su Unix socket"""
        if not os.path.exists(self.socket_path):
            logger.warning(f"Socket non esiste: {self.socket_path}")
            return None
        
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(timeout)
                sock.connect(self.socket_path)
                sock.sendall((json.dumps(request) + "\n").encode('utf-8'))
                
                # Leggi risposta completa
                buffer = b""
                while True:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    buffer += chunk
                    if b"\n" in buffer:
                        break
                
                if buffer:
                    response = json.loads(buffer.decode('utf-8').strip())
                    logger.debug(f"IPC response: {response}")
                    
                    if response.get("request_id") == self._request_id:
                        if response.get("error") == "success":
                            return response.get("data")
                        else:
                            logger.warning(f"IPC error: {response.get('error')}")
                    else:
                        logger.warning(f"Request ID mismatch: {response.get('request_id')} != {self._request_id}")
                
                return None
                
        except socket.timeout:
            logger.warning(f"IPC timeout per comando: {request['command'][0]}")
            return None
        except Exception as e:
            logger.error(f"Errore IPC Unix: {e}")
            return None
    
    def _send_windows(self, request: dict, timeout: float) -> Optional[Any]:
        """Invia comando su Windows named pipe"""
        try:
            import win32file
            import win32pipe
            import pywintypes
            
            handle = win32file.CreateFile(
                self.socket_path,
                win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                0, None,
                win32file.OPEN_EXISTING,
                0, None
            )
            
            message = (json.dumps(request) + "\n").encode('utf-8')
            win32file.WriteFile(handle, message)
            
            result, data = win32file.ReadFile(handle, 4096)
            win32file.CloseHandle(handle)
            
            if data:
                response = json.loads(data.decode('utf-8').strip())
                logger.debug(f"IPC response: {response}")
                
                if response.get("error") == "success":
                    return response.get("data")
            
            return None
            
        except ImportError:
            logger.error("win32file non disponibile per IPC Windows")
            return None
        except Exception as e:
            logger.error(f"Errore IPC Windows: {e}")
            return None
    
    def get_property(self, property_name: str) -> Optional[Any]:
        """Ottiene una proprietà da MPV"""
        return self.send_command("get_property", property_name)
    
    def set_property(self, property_name: str, value: Any) -> bool:
        """Imposta una proprietà in MPV"""
        result = self.send_command("set_property", property_name, value)
        return result is not None

# ============================================================================
# MONITOR METADATA CON THREAD POOL
# ============================================================================

class MetadataMonitor:
    """Monitora i metadata dello stream radio"""

    def __init__(self, update_callback):
        self.update_callback = update_callback
        self.running = False
        self.current_url = None
        self._response = None  # risposta HTTP attiva, chiudibile da stop()
        logger.info("Inizializzato MetadataMonitor")

    def start(self, url: str):
        self.current_url = url
        self.running = True
        logger.info(f"Avviato monitoraggio metadata per: {url}")

    def stop(self):
        self.running = False
        self.current_url = None
        # Chiude la connessione attiva: interrompe il read() bloccante nel thread
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
        while self.running and self.current_url:
            resp = None
            try:
                headers = {'Icy-MetaData': '1', 'User-Agent': 'RadioPlayer/2.0'}
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

                while self.running:
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
                                    self.update_callback('stream_title', stream_title)
                                    logger.info(f"Metadata ICY: {stream_title}")
                    except Exception:
                        # Connessione chiusa da stop() o errore di rete
                        break

            except requests.RequestException as e:
                if self.running:
                    logger.warning(f"Errore richiesta metadata: {e}")
                    time.sleep(5)
            except Exception as e:
                if self.running:
                    logger.error(f"Errore monitor metadata: {e}", exc_info=True)
                    time.sleep(5)
            finally:
                if resp is not None:
                    try:
                        resp.close()
                    except Exception:
                        pass
                self._response = None

        logger.info("Loop metadata terminato")

# ============================================================================
# CLIENT RADIOBROWSER.INFO
# ============================================================================

class RadioBrowserAPI:
    """Client per la API pubblica RadioBrowser.info"""

    _BASE_URLS = [
        "https://all.api.radio-browser.info/json",
        "http://all.api.radio-browser.info/json",
    ]
    HEADERS = {"User-Agent": "RadioPlayerM3U/2.0 azanzani@gmail.com"}
    _working_base: Optional[str] = None  # cache classe: evita retry SSL ad ogni ricerca

    def _get(self, path: str, params: dict) -> Optional[Any]:
        """Tenta la richiesta su tutti gli endpoint, cachando quello funzionante."""
        import urllib3

        # Metti in cima l'URL già funzionante, se noto
        bases = []
        if self._working_base:
            bases.append(self._working_base)
        bases += [b for b in self._BASE_URLS if b != self._working_base]

        for base in bases:
            for verify in (True, False):
                if not verify:
                    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                try:
                    resp = requests.get(
                        f"{base}{path}",
                        params=params,
                        headers=self.HEADERS,
                        timeout=8,
                        verify=verify,
                    )
                    resp.raise_for_status()
                    RadioBrowserAPI._working_base = base  # salva per le prossime chiamate
                    return resp.json()
                except requests.exceptions.SSLError:
                    if verify:
                        continue  # riprova senza verifica SSL
                    break  # passa all'endpoint successivo
                except requests.Timeout:
                    logger.warning(f"RadioBrowser: timeout su {base}")
                    break
                except Exception as e:
                    logger.warning(f"RadioBrowser: {base} (verify={verify}) — {e}")
                    break
        return None

    def search(self, query: str, limit: int = 20) -> List["RadioStation"]:
        """Cerca stazioni per nome. Restituisce lista ordinata per popolarità."""
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
                    "title":       item.get("name", "").strip(),
                    "group-title": item.get("country", ""),
                    "tvg-logo":    item.get("favicon", ""),
                    "rb-uuid":     item.get("stationuuid", ""),
                    "rb-votes":    str(item.get("votes", 0)),
                    "rb-bitrate":  str(item.get("bitrate", 0)),
                    "rb-codec":    item.get("codec", ""),
                    "rb-country":  item.get("country", ""),
                    "rb-tags":     item.get("tags", ""),
                },
            )
            results.append(station)

        logger.info(f"RadioBrowser: {len(results)} stazioni per '{query}'")
        return results


# ============================================================================
# CONTROLLER MPV
# ============================================================================

class MPVController:
    """Gestisce il processo MPV e la comunicazione IPC"""
    
    def __init__(self, socket_path: str):
        self.socket_path = socket_path
        self.process: Optional[subprocess.Popen] = None
        self.ipc_client = MPVIPCClient(socket_path)
        logger.info("Inizializzato MPVController")
    
    def start(self, url: str, volume: int = 50) -> bool:
        """Avvia MPV con lo stream"""
        try:
            # Rimuovi socket esistente
            if platform.system() != "Windows" and os.path.exists(self.socket_path):
                os.remove(self.socket_path)
                logger.debug("Rimosso socket esistente")
            
            cmd = [
                'mpv',
                '--no-video',
                f'--volume={volume}',
                '--quiet',
                '--no-terminal',
                '--cache=yes',
                '--demuxer-max-bytes=2M',
                '--audio-buffer=0.2',
                f'--input-ipc-server={self.socket_path}',
                url
            ]
            
            logger.info(f"Avvio MPV: {' '.join(cmd)}")
            
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                preexec_fn=os.setsid if platform.system() != "Windows" else None
            )
            
            # Attendi che il socket sia pronto
            for _ in range(20):  # Max 2 secondi
                time.sleep(0.1)
                if platform.system() != "Windows" and os.path.exists(self.socket_path):
                    break
            
            if self.process.poll() is None:
                logger.info("MPV avviato con successo")
                return True
            else:
                logger.error("MPV terminato immediatamente")
                return False
                
        except Exception as e:
            logger.error(f"Errore avvio MPV: {e}", exc_info=True)
            return False
    
    def stop(self):
        """Ferma MPV"""
        if not self.process:
            return
        
        try:
            logger.info("Fermata MPV")
            if platform.system() == "Windows":
                self.process.terminate()
                self.process.wait(timeout=2)
            else:
                os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
                self.process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            logger.warning("MPV non risponde, force kill")
            try:
                if platform.system() == "Windows":
                    self.process.kill()
                else:
                    os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)
            except:
                pass
        except Exception as e:
            logger.error(f"Errore stop MPV: {e}")
        finally:
            self.process = None
            
            # Pulisci socket
            if platform.system() != "Windows" and os.path.exists(self.socket_path):
                try:
                    os.remove(self.socket_path)
                except:
                    pass
    
    def is_running(self) -> bool:
        """Verifica se MPV è in esecuzione"""
        return self.process is not None and self.process.poll() is None
    
    def set_volume(self, volume: int) -> bool:
        """Imposta il volume"""
        return self.ipc_client.set_property("volume", volume)
    
    def set_mute(self, muted: bool) -> bool:
        """Imposta muto"""
        return self.ipc_client.set_property("mute", muted)
    
    def get_audio_stats(self) -> Dict[str, Any]:
        """Ottiene statistiche audio"""
        stats = {}
        
        bitrate = self.ipc_client.get_property("audio-bitrate")
        if bitrate:
            stats['bitrate'] = f"{int(bitrate/1000)} kbps"
        
        codec = self.ipc_client.get_property("audio-codec-name")
        if codec:
            stats['codec'] = codec.upper()
        
        cache = self.ipc_client.get_property("demuxer-cache-duration")
        if cache:
            stats['cache'] = f"{cache:.1f}s"
        
        buffering = self.ipc_client.get_property("paused-for-cache")
        if buffering:
            stats['buffer_status'] = "BUFFERING"
        else:
            cache_percent = self.ipc_client.get_property("cache-buffering-state")
            if cache_percent is not None:
                stats['buffer_status'] = f"{cache_percent}%"
            else:
                stats['buffer_status'] = "OK"
        
        return stats

# ============================================================================
# RADIO PLAYER PRINCIPALE
# ============================================================================

class RadioPlayer:
    """Radio Player principale con gestione avanzata"""
    
    def __init__(self, use_rich: bool = RICH_AVAILABLE):
        self.use_rich = use_rich and RICH_AVAILABLE
        
        # Configurazione socket
        if platform.system() == "Windows":
            socket_path = r"\\.\pipe\radio_player_mpv"
        else:
            socket_path = "/tmp/radio_player_mpv.sock"
        
        # Componenti
        self.stations: List[RadioStation] = []
        self.state = PlayerState()
        self.mpv_controller = MPVController(socket_path)
        self.metadata_monitor = MetadataMonitor(self._on_metadata_update)
        self.history = MetadataHistory()
        
        # Thread pool
        self.executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="RadioPlayer")
        self.update_queue: queue.Queue = queue.Queue()
        
        # UI
        self.running = True
        self.pending_updates = UpdateFlags.FULL
        
        # Rich UI
        if self.use_rich:
            self.console = Console()
            self.live = None
        
        # Terminal raw mode
        self.old_settings = None
        
        # Input numerico
        self.number_input_mode = False
        self.number_buffer = ""
        
        # Recording
        self.is_recording = False
        self.recording_process: Optional[subprocess.Popen] = None
        self.recording_file: Optional[Path] = None
        
        # Logging
        self.logging_enabled = False  # Default OFF

        # Messaggio temporaneo UI
        self.temp_message = ""
        self.temp_message_time = 0

        # RadioBrowser search
        self.radio_browser = RadioBrowserAPI()
        self.search_mode = False
        self.search_query = ""
        self.search_results: List[RadioStation] = []
        self.search_selected_idx = 0
        self.search_loading = False
        self._search_timer: Optional[threading.Timer] = None
        self._last_searched_query = ""   # query dell'ultima ricerca completata
        self._preview_station: Optional[RadioStation] = None  # in ascolto ma non in M3U
        self.m3u_file_path: Optional[Path] = None

        # Timer sessione: non si resetta al cambio stazione
        self.session_start_time = time.time()
        
        # Cache UI
        self.last_render_time = 0
        self.min_render_interval = 0.1  # Max 10 FPS
        
        logger.info(f"Inizializzato RadioPlayer (Rich UI: {self.use_rich})")
        
        # Verifica MPV
        if not self._check_mpv():
            print("❌ MPV non installato!")
            print("   Ubuntu/Debian: sudo apt install mpv")
            print("   Fedora: sudo dnf install mpv")
            print("   macOS: brew install mpv")
            sys.exit(1)
    
    def _check_mpv(self) -> bool:
        """Verifica disponibilità MPV"""
        try:
            subprocess.run(
                ['mpv', '--version'],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True
            )
            logger.info("MPV disponibile")
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.error("MPV non trovato")
            return False
    
    def load_m3u(self, file_path: Path) -> bool:
        """Carica file M3U"""
        try:
            parser = M3UParser()
            self.stations = parser.parse_file(file_path)

            if not self.stations:
                logger.warning("Nessuna stazione trovata nel file M3U")
                return False

            self.m3u_file_path = file_path
            logger.info(f"Caricate {len(self.stations)} stazioni da {file_path}")
            self.pending_updates |= UpdateFlags.FULL
            return True
            
        except Exception as e:
            logger.error(f"Errore caricamento M3U: {e}", exc_info=True)
            return False
    
    def _on_metadata_update(self, key: str, value: str):
        """Callback per aggiornamenti metadata"""
        # RIMOSSO DEBUG SU FILE
        logger.info(f"Metadata update: {key} = {value}")
        
        if key == 'bitrate':
            if not self.state.stream_info.bitrate:
                # Crea nuovo StreamInfo con bitrate aggiornato
                self.state.stream_info = StreamInfo(
                    artist=self.state.stream_info.artist,
                    song=self.state.stream_info.song,
                    title=self.state.stream_info.title,
                    bitrate=value,
                    audio_bitrate=self.state.stream_info.audio_bitrate,
                    codec=self.state.stream_info.codec,
                    buffer_status=self.state.stream_info.buffer_status,
                    cache_duration=self.state.stream_info.cache_duration,
                    start_time=self.state.stream_info.start_time,
                    song_start_time=self.state.stream_info.song_start_time,
                    pause_start_time=self.state.stream_info.pause_start_time,
                    total_pause_time=self.state.stream_info.total_pause_time
                )
                self.pending_updates |= UpdateFlags.SONG
        
        elif key == 'stream_title':
            old_title = self.state.stream_info.title
            
            # Ignora aggiornamenti vuoti se abbiamo già un titolo valido
            if not value and old_title:
                return

            if ' - ' in value:
                artist, song = value.split(' - ', 1)
                artist = artist.strip()
                song = song.strip()
                
                if artist != self.state.stream_info.artist or song != self.state.stream_info.song:
                    # Crea un NUOVO StreamInfo invece di modificare quello esistente
                    self.state.stream_info = StreamInfo(
                        artist=artist,
                        song=song,
                        title=value,
                        bitrate=self.state.stream_info.bitrate,
                        audio_bitrate=self.state.stream_info.audio_bitrate,
                        codec=self.state.stream_info.codec,
                        buffer_status=self.state.stream_info.buffer_status,
                        cache_duration=self.state.stream_info.cache_duration,
                        start_time=self.state.stream_info.start_time,
                        song_start_time=time.time(),
                        pause_start_time=None,
                        total_pause_time=0.0
                    )
                    
                    # Aggiungi a cronologia
                    if self.state.playing_station_index >= 0:
                        station_name = self.stations[self.state.playing_station_index].name
                        self.history.add(artist, song, station_name)
                    
                    # Mostra popup se abilitato
                    if self.state.show_song_popups and old_title:
                        self._show_notification(f"{artist} - {song}")
                    
                    # Mostra anche messaggio temporaneo in UI
                    self.show_temp_message(f"🎵 {artist} - {song}")
                    
                    self.pending_updates |= UpdateFlags.SONG | UpdateFlags.STATUS
                    logger.info(f"Nuovo brano: {artist} - {song}")
            else:
                if value != self.state.stream_info.song:
                    # Crea un NUOVO StreamInfo invece di modificare quello esistente
                    self.state.stream_info = StreamInfo(
                        artist="",
                        song=value,
                        title=value,
                        bitrate=self.state.stream_info.bitrate,
                        audio_bitrate=self.state.stream_info.audio_bitrate,
                        codec=self.state.stream_info.codec,
                        buffer_status=self.state.stream_info.buffer_status,
                        cache_duration=self.state.stream_info.cache_duration,
                        start_time=self.state.stream_info.start_time,
                        song_start_time=time.time(),
                        pause_start_time=None,
                        total_pause_time=0.0
                    )
                    
                    if self.state.playing_station_index >= 0:
                        station_name = self.stations[self.state.playing_station_index].name
                        self.history.add("", value, station_name)
                    
                    if self.state.show_song_popups and old_title:
                        self._show_notification(value)
                    
                    # Mostra anche messaggio temporaneo in UI
                    self.show_temp_message(f"🎵 {value}")
                    
                    self.pending_updates |= UpdateFlags.SONG | UpdateFlags.STATUS
                    logger.info(f"Nuovo brano: {value}")
    
    def _show_notification(self, message: str):
        """Mostra notifica di sistema"""
        if not self.state.show_song_popups:
            return
        
        try:
            if platform.system() == "Windows":
                # Windows notification
                try:
                    from win10toast import ToastNotifier
                    toaster = ToastNotifier()
                    toaster.show_toast("🎵 Radio Player", message, 
                                     icon_path=None, duration=4, threaded=True)
                except ImportError:
                    pass
            else:
                # Linux notification
                subprocess.run(
                    ['notify-send', '🎵 Radio Player', message,
                     '--icon=audio-x-generic', '--expire-time=4000'],
                    check=True, capture_output=True, timeout=2
                )
        except Exception as e:
            logger.debug(f"Notifica fallita: {e}")
    
    def play_selected(self):
        """Avvia riproduzione della stazione selezionata"""
        if not self.stations:
            return
        
        station = self.stations[self.state.selected_station_index]
        logger.info(f"Play stazione: {station.name}")
        
        # Stop precedente
        self.stop()
        
        # Avvia MPV
        if self.mpv_controller.start(station.url, self.state.volume):
            self.state.is_playing = True
            self.state.is_paused = False
            self.state.playing_station_index = self.state.selected_station_index
            # NON inizializzo più con "Caricamento..." - lascio vuoto
            self.state.stream_info = StreamInfo(
                start_time=time.time(),
                song_start_time=time.time()
            )
            
            # Avvia monitor metadata in thread pool
            self.metadata_monitor.start(station.url)
            self.executor.submit(self.metadata_monitor.monitor_loop)
            
            # Avvia monitor stats
            self.executor.submit(self._stats_monitor_loop)
            
            self.pending_updates |= UpdateFlags.STATUS | UpdateFlags.SONG | UpdateFlags.STATIONS
            
            logger.info("Riproduzione avviata")
        else:
            logger.error("Impossibile avviare riproduzione")
    
    def stop(self):
        """Ferma riproduzione"""
        if self.state.is_playing:
            logger.info("Stop riproduzione")
            
            # Ferma registrazione se attiva
            if self.is_recording:
                self.stop_recording()
            
            self.metadata_monitor.stop()
            self.mpv_controller.stop()
            
            self.state.is_playing = False
            self.state.is_paused = False
            self.state.playing_station_index = -1
            self.state.stream_info = StreamInfo()
            self._preview_station = None

            self.pending_updates |= UpdateFlags.STATUS | UpdateFlags.SONG | UpdateFlags.STATIONS
    
    def toggle_play_pause(self):
        """Toggle play/pause"""
        if not self.stations:
            return
        
        if not self.state.is_playing:
            # Non in riproduzione -> avvia
            self.play_selected()
        else:
            if self.state.playing_station_index != self.state.selected_station_index:
                # Stazione diversa selezionata -> cambia stazione
                self.play_selected()
            else:
                # Stessa stazione -> pausa/riprendi
                if self.state.is_paused:
                    # Era in pausa -> riprendi
                    self.state.is_paused = False
                    self.state.stream_info.total_pause_time += time.time() - self.state.stream_info.pause_start_time
                    self.state.stream_info.pause_start_time = None
                    self.pending_updates |= UpdateFlags.STATUS | UpdateFlags.SONG
                    logger.info("Riproduzione ripresa")
                else:
                    # Era in play -> pausa
                    self.state.is_paused = True
                    self.state.stream_info.pause_start_time = time.time()
                    self.pending_updates |= UpdateFlags.STATUS | UpdateFlags.SONG
                    logger.info("Riproduzione in pausa")
    
    def change_volume(self, delta: int):
        """Cambia volume"""
        self.state.volume = max(0, min(100, self.state.volume + delta))
        
        if self.state.is_playing:
            self.mpv_controller.set_volume(self.state.volume)
        
        self.pending_updates |= UpdateFlags.TIMER
        logger.debug(f"Volume: {self.state.volume}%")
    
    def toggle_mute(self):
        """Toggle muto"""
        self.state.is_muted = not self.state.is_muted
        
        if self.state.is_playing:
            self.mpv_controller.set_mute(self.state.is_muted)
        
        self.pending_updates |= UpdateFlags.TIMER
        logger.debug(f"Muto: {self.state.is_muted}")
    
    def change_selection(self, delta: int):
        """Cambia stazione selezionata"""
        if not self.stations:
            return
        
        self.state.selected_station_index = (
            self.state.selected_station_index + delta
        ) % len(self.stations)
        
        self.pending_updates |= UpdateFlags.STATIONS
    
    def select_by_number(self, number: int):
        """Seleziona stazione per numero"""
        if 1 <= number <= len(self.stations):
            self.state.selected_station_index = number - 1
            self.pending_updates |= UpdateFlags.STATIONS
            logger.debug(f"Selezionata stazione #{number}")
    
    def toggle_notifications(self):
        """Toggle notifiche cambio brano"""
        self.state.show_song_popups = not self.state.show_song_popups
        self.pending_updates |= UpdateFlags.TIMER
        
        status = "ON" if self.state.show_song_popups else "OFF"
        self.show_temp_message(f"🔔 Notifiche: {status}")
        logger.info(f"Notifiche: {status}")
    
    def toggle_logging(self):
        """Toggle logging su file"""
        self.logging_enabled = not self.logging_enabled
        
        if self.logging_enabled:
            # Rimuovi NullHandler e aggiungi RotatingFileHandler
            for handler in logger.handlers[:]:
                if isinstance(handler, logging.NullHandler):
                    logger.removeHandler(handler)
            
            # Crea il file handler solo ora
            if hasattr(logger, '_log_file_path'):
                file_handler = RotatingFileHandler(
                    logger._log_file_path, 
                    maxBytes=5*1024*1024, 
                    backupCount=3, 
                    encoding='utf-8'
                )
                file_handler.setLevel(logging.DEBUG)
                formatter = logging.Formatter(
                    '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
                )
                file_handler.setFormatter(formatter)
                logger.addHandler(file_handler)
                logger.info("Logging abilitato dall'utente")
        else:
            # Rimuovi file handler e aggiungi NullHandler
            for handler in logger.handlers[:]:
                if isinstance(handler, RotatingFileHandler):
                    logger.removeHandler(handler)
                    handler.close()
            
            if not any(isinstance(h, logging.NullHandler) for h in logger.handlers):
                logger.addHandler(logging.NullHandler())
        
        status = "ON" if self.logging_enabled else "OFF"
        self.show_temp_message(f"📝 Logging: {status}")
        self.pending_updates |= UpdateFlags.TIMER
    
    def toggle_recording(self):
        """Toggle registrazione stream"""
        if not self.state.is_playing:
            self.show_temp_message("❌ Avvia prima una stazione")
            return
        
        if self.is_recording:
            # Stop recording
            self.stop_recording()
        else:
            # Start recording
            self.start_recording()
    
    def start_recording(self):
        """Avvia registrazione stream"""
        if self.is_recording or not self.state.is_playing:
            return
        
        station = self.stations[self.state.playing_station_index]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        station_name = re.sub(r'[^\w\s-]', '', station.name)[:30]
        
        self.recording_file = Path(f"recording_{station_name}_{timestamp}.mp3")
        
        try:
            # Usa ffmpeg per registrare
            cmd = [
                'ffmpeg',
                '-i', station.url,
                '-c', 'copy',
                '-y',
                str(self.recording_file)
            ]
            
            self.recording_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            
            self.is_recording = True
            self.pending_updates |= UpdateFlags.STATUS
            self.show_temp_message(f"🔴 Registrazione avviata: {self.recording_file.name}")
            logger.info(f"Registrazione avviata: {self.recording_file}")
            
        except FileNotFoundError:
            self.show_temp_message("❌ ffmpeg non installato (apt install ffmpeg)")
            logger.error("ffmpeg non disponibile per registrazione")
        except Exception as e:
            self.show_temp_message(f"❌ Errore registrazione: {e}")
            logger.error(f"Errore avvio registrazione: {e}")
    
    def stop_recording(self):
        """Ferma registrazione"""
        if not self.is_recording:
            return
        
        try:
            if self.recording_process:
                self.recording_process.terminate()
                self.recording_process.wait(timeout=2)
                self.recording_process = None
            
            self.is_recording = False
            self.pending_updates |= UpdateFlags.STATUS
            
            if self.recording_file and self.recording_file.exists():
                size_mb = self.recording_file.stat().st_size / (1024 * 1024)
                self.show_temp_message(f"⏹️ Registrazione salvata: {self.recording_file.name} ({size_mb:.1f} MB)")
                logger.info(f"Registrazione salvata: {self.recording_file} ({size_mb:.1f} MB)")
            else:
                self.show_temp_message("⏹️ Registrazione fermata")
            
            self.recording_file = None
            
        except Exception as e:
            self.show_temp_message(f"❌ Errore stop registrazione: {e}")
            logger.error(f"Errore stop registrazione: {e}")
    
    def show_temp_message(self, message: str):
        """Mostra messaggio temporaneo nell'UI"""
        self.temp_message = message
        self.temp_message_time = time.time()
        self.pending_updates |= UpdateFlags.STATUS
    
    def show_history(self):
        """Mostra cronologia ultimi brani"""
        last = self.history.get_last(10)
        
        if not last:
            self.show_temp_message("📜 Cronologia vuota")
            return
        
        # Costruisci messaggio
        msg_lines = ["📜 Ultimi 10 brani:"]
        for i, entry in enumerate(reversed(last), 1):
            artist = entry.get('artist', '')
            song = entry.get('song', '')
            station = entry.get('station', '')
            
            if artist and song:
                msg_lines.append(f"{i}. {artist} - {song} ({station})")
            elif song:
                msg_lines.append(f"{i}. {song} ({station})")
        
        msg = "\n".join(msg_lines)
        self.show_temp_message(msg)
        logger.info(msg)
    
    # ========================================================================
    # RICERCA RADIOBROWSER
    # ========================================================================

    def enter_search_mode(self):
        """Entra in modalità sfoglia RadioBrowser.info"""
        self.search_mode = True
        self.search_query = ""
        self.search_results = []
        self.search_selected_idx = 0
        self.search_loading = False
        self.pending_updates |= UpdateFlags.FULL
        logger.info("Entrato in modalità ricerca RadioBrowser")

    def exit_search_mode(self):
        """Esce dalla modalità ricerca"""
        if self._search_timer:
            self._search_timer.cancel()
            self._search_timer = None
        self.search_mode = False
        self.pending_updates |= UpdateFlags.FULL
        logger.info("Uscito dalla modalità ricerca")

    def _trigger_search(self):
        """Avvia ricerca con debounce di 0.5s"""
        if self._search_timer:
            self._search_timer.cancel()
            self._search_timer = None

        if not self.search_query.strip():
            self.search_results = []
            self.search_selected_idx = 0
            self.search_loading = False
            self.pending_updates |= UpdateFlags.STATIONS
            return

        self.search_loading = True
        self.pending_updates |= UpdateFlags.STATIONS
        self._search_timer = threading.Timer(0.3, self._do_search)
        self._search_timer.daemon = True
        self._search_timer.start()

    def _do_search(self):
        """Esegue la chiamata API in background"""
        query = self.search_query
        if not query.strip():
            return
        try:
            results = self.radio_browser.search(query)
            if query == self.search_query:  # query non cambiata durante la ricerca
                self.search_results = results
                self.search_selected_idx = 0
                self.search_loading = False
                self._last_searched_query = query  # memorizza per il messaggio "nessun risultato"
                self.pending_updates |= UpdateFlags.STATIONS
        except Exception as e:
            logger.error(f"Errore ricerca: {e}")
            self.search_loading = False
            self._last_searched_query = query
            self.pending_updates |= UpdateFlags.STATIONS

    def play_preview(self, station: RadioStation):
        """Ascolta anteprima senza aggiungere al M3U"""
        self.stop()
        if self.mpv_controller.start(station.url, self.state.volume):
            self.state.is_playing = True
            self.state.is_paused = False
            self.state.playing_station_index = -1
            self._preview_station = station
            self.state.stream_info = StreamInfo(
                start_time=time.time(),
                song_start_time=time.time(),
            )
            self.metadata_monitor.start(station.url)
            self.executor.submit(self.metadata_monitor.monitor_loop)
            self.executor.submit(self._stats_monitor_loop)
            self.pending_updates |= UpdateFlags.STATUS | UpdateFlags.SONG
            self.show_temp_message(f"👂 Anteprima: {station.name}")
            logger.info(f"Preview: {station.name}")
        else:
            self.show_temp_message("❌ Impossibile avviare anteprima")

    def add_station_to_m3u(self, station: RadioStation) -> bool:
        """Aggiunge la stazione al file M3U evitando duplicati (URL e nome)"""
        if not self.m3u_file_path:
            self.show_temp_message("❌ Nessun file M3U caricato")
            return False

        # Controllo duplicato per URL (normalizzato senza trailing slash)
        station_url = station.url.rstrip("/")
        for existing in self.stations:
            if existing.url.rstrip("/") == station_url:
                self.show_temp_message(f"⚠️  Già presente: {existing.name}")
                return False

        # Controllo duplicato per nome (case-insensitive)
        station_name_lc = station.name.strip().lower()
        for existing in self.stations:
            if existing.name.strip().lower() == station_name_lc:
                self.show_temp_message(f"⚠️  Nome già presente: {existing.name}")
                return False

        try:
            try:
                content = self.m3u_file_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                content = self.m3u_file_path.read_text(encoding="latin-1")

            with open(self.m3u_file_path, "a", encoding="utf-8") as f:
                if content and not content.endswith("\n"):
                    f.write("\n")
                f.write(f"#EXTINF:-1,{station.name}\n{station.url}\n")

            self.stations.append(station)
            self.pending_updates |= UpdateFlags.STATIONS
            self.show_temp_message(f"✅ Aggiunta: {station.name}")
            logger.info(f"Aggiunta al M3U: {station.name} — {station.url}")
            return True

        except Exception as e:
            self.show_temp_message(f"❌ Errore salvataggio: {e}")
            logger.error(f"Errore aggiunta stazione: {e}")
            return False

    def _stats_monitor_loop(self):
        """Loop monitoraggio statistiche MPV e METADATA"""
        logger.info("Avviato monitor statistiche")
        
        while self.state.is_playing and self.mpv_controller.is_running():
            try:
                # Controlla pausa e muta/unmuta MPV
                if self.state.is_paused:
                    # In pausa -> muta
                    self.mpv_controller.set_mute(True)
                elif self.state.is_muted:
                    # Muto esplicito
                    self.mpv_controller.set_mute(True)
                else:
                    # Unmuta
                    self.mpv_controller.set_mute(False)
                
                stats = self.mpv_controller.get_audio_stats()
                
                if stats.get('bitrate'):
                    self.state.stream_info.audio_bitrate = stats['bitrate']
                
                if stats.get('codec'):
                    self.state.stream_info.codec = stats['codec']
                
                if stats.get('cache'):
                    self.state.stream_info.cache_duration = stats['cache']
                
                if stats.get('buffer_status'):
                    old_buffer = self.state.stream_info.buffer_status
                    self.state.stream_info.buffer_status = stats['buffer_status']
                    
                    # Solo BUFFERING forza update immediato
                    if stats['buffer_status'] == "BUFFERING" and old_buffer != "BUFFERING":
                        self.pending_updates |= UpdateFlags.TECHNICAL
                
                # FALLBACK: Recupera metadata completo da MPV
                # Questo è fondamentale per stream Shoutcast/Icecast
                metadata = self.mpv_controller.ipc_client.get_property("metadata")
                
                if metadata and isinstance(metadata, dict):
                    # Cerca il titolo in ordine di specificità
                    # 1. icy-title (standard per radio stream)
                    # 2. title (standard generico)
                    # 3. TITLE (variante)
                    current_title = metadata.get("icy-title") or metadata.get("title") or metadata.get("TITLE")
                    
                    if current_title:
                        # Se il titolo è diverso da quello attuale, aggiornalo
                        # Nota: normalizziamo eventuali spazi
                        current_title = str(current_title).strip()
                        if current_title and current_title != self.state.stream_info.title:
                            # Usa la stessa logica di callback per parsing e UI update
                            self._on_metadata_update('stream_title', current_title)
                
                time.sleep(2)
                
            except Exception as e:
                logger.error(f"Errore monitor stats: {e}")
                break
        
        logger.info("Terminato monitor statistiche")
    
    # ========================================================================
    # UI RICH
    # ========================================================================
    
    def _build_rich_layout(self) -> Optional[Any]:
        """Costruisce il layout Rich"""
        if not RICH_AVAILABLE:
            return None

        layout = Layout()

        # stations size=12: 10 stazioni + 2 bordi pannello sempre visibili
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="status", size=5),
            Layout(name="stations", size=12),
            Layout(name="controls", ratio=1),
        )

        return layout
    
    def _render_rich_header(self) -> Optional[Any]:
        """Renderizza header Rich"""
        if not RICH_AVAILABLE:
            return None
        
        current_time = datetime.now().strftime("%H:%M:%S")

        # Uptime di sessione: calcolato da session_start_time, mai resettato
        elapsed = time.time() - self.session_start_time
        h = int(elapsed // 3600)
        m = int((elapsed % 3600) // 60)
        s = int(elapsed % 60)
        uptime = f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"
        
        volume_icon = "🔇" if self.state.is_muted else "🔊"
        notif_icon = "🔔" if self.state.show_song_popups else "🔕"
        log_status = "📝 LOG" if self.logging_enabled else "📝 ✗"
        
        header_text = Text()
        header_text.append("🎵 RADIO PLAYER M3U", style="bold cyan")
        header_text.append(f"    ⏰ {current_time}", style="white")
        header_text.append(f"    Uptime: {uptime}", style="yellow")
        header_text.append(f"    {volume_icon} Volume: {self.state.volume}%", style="green")
        # --- MODIFICA QUI SOTTO PER LOG IN BOLD RED ---
        header_text.append(f"    {log_status}", style="bold red" if self.logging_enabled else "dim")
        # -----------------------------------------------
        header_text.append(f"    {notif_icon}", style="blue")
        
        return Panel(header_text, border_style="cyan")
    
    def _render_rich_status(self) -> Optional[Any]:
        """Renderizza status Rich (3 righe di contenuto, size=5)"""
        if not RICH_AVAILABLE:
            return None

        si = self.state.stream_info

        # Riga 1: stato + stazione + registrazione
        if self.state.is_playing and not self.state.is_paused:
            status_part = "[bold green]▶  IN RIPRODUZIONE[/bold green]"
        elif self.state.is_paused:
            status_part = "[bold yellow]⏸  IN PAUSA[/bold yellow]"
        else:
            status_part = "[bold red]⏹  FERMATO[/bold red]"

        station_part = ""
        if self.state.playing_station_index >= 0:
            station = self.stations[self.state.playing_station_index]
            station_part = f"  [dim]│[/dim]  [cyan]📡 {station.name}[/cyan]"
        elif self._preview_station:
            station_part = f"  [dim]│[/dim]  [magenta]👂 {self._preview_station.name} (anteprima)[/magenta]"

        rec_part = "  [bold red]🔴 REC[/bold red]" if self.is_recording else ""
        line1 = f"{status_part}{station_part}{rec_part}"

        # Riga 2: info brano
        if si.artist and si.song:
            song_time = si.get_song_time(self.state.is_playing, self.state.is_paused)
            time_str = f" [yellow][{song_time}][/yellow]" if song_time != "00:00" else ""
            line2 = f"[magenta]🎤 {si.artist}[/magenta]  [bold blue]🎼 {si.song}[/bold blue]{time_str}"
        elif si.song or si.title:
            song = si.song or si.title
            song_time = si.get_song_time(self.state.is_playing, self.state.is_paused)
            time_str = f" [yellow][{song_time}][/yellow]" if song_time != "00:00" else ""
            line2 = f"[bold blue]🎼 {song}[/bold blue]{time_str}"
        elif self.state.is_playing:
            line2 = "[dim italic]🎼 In attesa dei metadata dello stream...[/dim italic]"
        else:
            line2 = ""

        # Riga 3: messaggio temporaneo oppure info tecniche
        if self.temp_message and (time.time() - self.temp_message_time) < 2:
            line3 = f"[yellow]💬 {self.temp_message}[/yellow]"
        else:
            tech = []
            if si.audio_bitrate or si.bitrate:
                tech.append(f"🔊 {si.audio_bitrate or si.bitrate}")
            if si.codec:
                tech.append(si.codec)
            if si.buffer_status:
                if si.buffer_status == "BUFFERING":
                    tech.append("[bold red]🔄 BUFFERING[/bold red]")
                else:
                    tech.append(f"📦 {si.buffer_status}")
            line3 = f"[dim]{' • '.join(tech)}[/dim]" if tech else ""

        parts = [line1]
        if line2:
            parts.append(line2)
        if line3:
            parts.append(line3)

        return Panel("\n".join(parts), title="Status", border_style="green")
    
    def _render_rich_stations(self) -> Optional[Any]:
        """Renderizza lista stazioni Rich (sempre 10 righe, size=12)"""
        if not RICH_AVAILABLE:
            return None

        n_visible = 10
        n_stations = len(self.stations)

        # Centra la finestra sulla stazione selezionata
        start_idx = max(0, self.state.selected_station_index - n_visible // 2)
        if start_idx + n_visible > n_stations:
            start_idx = max(0, n_stations - n_visible)
        end_idx = min(n_stations, start_idx + n_visible)

        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Marker", style="cyan", width=4, no_wrap=True)
        table.add_column("Number", style="yellow", width=3, no_wrap=True)
        table.add_column("Name", style="white")

        for i in range(start_idx, end_idx):
            station = self.stations[i]

            marker = "👉" if i == self.state.selected_station_index else "  "

            if i == self.state.playing_station_index and self.state.is_playing:
                marker += "▶️" if not self.state.is_paused else "⏸️"
            else:
                marker += "  "

            style = "bold reverse" if i == self.state.selected_station_index else ""
            table.add_row(marker, str(i + 1), station.name, style=style)

        title = f"📻 Stazioni ({n_stations} totali)"
        if n_stations > n_visible:
            title += f"  [{start_idx + 1}–{end_idx} di {n_stations}]"

        return Panel(table, title=title, border_style="blue")
    
    def _render_rich_controls(self) -> Optional[Any]:
        """Renderizza controlli Rich (2 righe compatte + eventuale input numero)"""
        if not RICH_AVAILABLE:
            return None

        lines = [
            "[cyan]↑/↓[/cyan] Seleziona  "
            "[cyan]p/Space[/cyan] Play/Pausa  "
            "[cyan]+/=[/cyan] Vol+  "
            "[cyan]-/_[/cyan] Vol-  "
            "[cyan]m[/cyan] Muto  "
            "[cyan]b[/cyan] Sfoglia RadioBrowser",

            "[cyan]r[/cyan] Rec  "
            "[cyan]l[/cyan] Log  "
            "[cyan]t[/cyan] Notifiche  "
            "[cyan]h[/cyan] Cronologia  "
            "[cyan]s[/cyan] Salva  "
            "[cyan]1-9+↵[/cyan] Vai a #  "
            "[cyan]q[/cyan] Esci",
        ]

        if self.number_input_mode:
            lines.append(
                f"[bold yellow]🔢 NUMERO: {self.number_buffer}_[/bold yellow]"
                "  [dim](↵=conferma  Esc=annulla)[/dim]"
            )

        return Panel("\n".join(lines), title="🎮 Controlli", border_style="yellow")
    
    def _render_rich_footer(self) -> Optional[Any]:
        """Renderizza footer Rich"""
        if not RICH_AVAILABLE:
            return None
        
        footer = Text()
        footer.append("© 2025 Andres Zanzani ", style="dim")
        footer.append("<azanzani@gmail.com>", style="dim blue")
        footer.append(" - GPL 3 License", style="dim")
        return footer
    
    def _render_rich_search(self) -> Optional[Any]:
        """Renderizza il pannello di ricerca RadioBrowser.info"""
        if not RICH_AVAILABLE:
            return None

        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="search_input", size=3),
            Layout(name="search_results", ratio=1),
            Layout(name="search_controls", size=4),
        )

        layout["header"].update(self._render_rich_header())

        # --- Stato corrente: determina titoli e colori ---
        spinner = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")[int(time.time() * 8) % 10]
        cursor  = "_" if int(time.time() * 2) % 2 == 0 else " "

        if self.search_loading:
            input_title   = f"🔍 RadioBrowser.info  [bold yellow]{spinner} RICERCA IN CORSO...[/bold yellow]"
            input_border  = "yellow"
            res_title     = f"[bold yellow]{spinner} Ricerca in corso...[/bold yellow]"
            res_border    = "yellow"
            res_body      = (
                f"\n[bold yellow]{spinner}  Interrogazione RadioBrowser.info...[/bold yellow]\n\n"
                f'[dim]Cerca: "[italic]{self.search_query}[/italic]"[/dim]'
            )
        elif self.search_results:
            input_title   = f"🔍 RadioBrowser.info  [bold green]✅ {len(self.search_results)} stazioni trovate[/bold green]"
            input_border  = "green"
            n             = len(self.search_results)
            res_title     = f"Risultati ({n})"
            res_border    = "green"
            res_body      = None  # usa la tabella
        elif self._last_searched_query:
            input_title   = f'🔍 RadioBrowser.info  [bold red]❌ Nessun risultato per "{self._last_searched_query}"[/bold red]'
            input_border  = "red"
            res_title     = "Risultati"
            res_border    = "red"
            res_body      = f'[bold red]❌  Nessuna stazione trovata per "[italic]{self._last_searched_query}[/italic]"[/bold red]\n\n[dim]Prova con termini diversi (es. solo il nome, senza prefisso paese)[/dim]'
        else:
            input_title   = "🔍 RadioBrowser.info — sfoglia 40.000+ stazioni"
            input_border  = "magenta"
            res_title     = "Risultati"
            res_border    = "magenta"
            res_body      = "[dim italic]Inizia a digitare il nome della stazione...[/dim italic]"

        # --- Barra di ricerca ---
        input_content = f"[bold white]{self.search_query}{cursor}[/bold white]"
        layout["search_input"].update(
            Panel(input_content, title=input_title, border_style=input_border)
        )

        # --- Lista risultati ---
        if self.search_results and not self.search_loading:
            table = Table(show_header=True, box=None, padding=(0, 1))
            table.add_column("", width=2, no_wrap=True)
            table.add_column("Nome", style="white", ratio=3)
            table.add_column("Paese", style="cyan", width=6, no_wrap=True)
            table.add_column("kbps", style="yellow", width=6, no_wrap=True, justify="right")
            table.add_column("Codec", style="dim", width=6, no_wrap=True)
            table.add_column("★ Voti", style="green", width=8, no_wrap=True, justify="right")

            n_visible = 15
            start = max(0, self.search_selected_idx - n_visible // 2)
            if start + n_visible > len(self.search_results):
                start = max(0, len(self.search_results) - n_visible)
            end = min(len(self.search_results), start + n_visible)

            for i in range(start, end):
                s = self.search_results[i]
                marker  = "👉" if i == self.search_selected_idx else "  "
                already = any(e.url.rstrip("/") == s.url.rstrip("/") for e in self.stations)
                name    = f"[dim]{s.name} ✓[/dim]" if already else s.name
                country = s.metadata.get("rb-country", "")[:5]
                bitrate = s.metadata.get("rb-bitrate", "0")
                codec   = s.metadata.get("rb-codec", "")[:6]
                votes   = s.metadata.get("rb-votes", "0")
                style   = "bold reverse" if i == self.search_selected_idx else ""
                table.add_row(marker, name, country, bitrate, codec, votes, style=style)

            if len(self.search_results) > n_visible:
                res_title += f"  [{start + 1}–{end}]"

            layout["search_results"].update(Panel(table, title=res_title, border_style=res_border))
        else:
            layout["search_results"].update(Panel(res_body, title=res_title, border_style=res_border))

        # --- Controlli contestuali ---
        preview_stop = "  [cyan]Space[/cyan] Ferma anteprima" if self.state.is_playing else ""
        ctrl = (
            "[cyan]↑/↓[/cyan] Naviga  "
            "[cyan]↵[/cyan] Aggiungi a M3U  "
            "[cyan]p[/cyan] Ascolta anteprima"
            f"{preview_stop}  "
            "[cyan]⌫[/cyan] Cancella  "
            "[cyan]Esc[/cyan] Torna alla lista"
        )
        layout["search_controls"].update(Panel(ctrl, title="🎮 Comandi ricerca", border_style="yellow"))

        return layout

    def _render_rich(self) -> Optional[Any]:
        """Renderizza interfaccia completa Rich"""
        if not RICH_AVAILABLE:
            return None

        if self.search_mode:
            return self._render_rich_search()

        layout = self._build_rich_layout()

        layout["header"].update(self._render_rich_header())
        layout["status"].update(self._render_rich_status())
        layout["stations"].update(self._render_rich_stations())
        layout["controls"].update(self._render_rich_controls())

        return layout
    
    # ========================================================================
    # INPUT E LOOP PRINCIPALE
    # ========================================================================
    
    def setup_terminal(self):
        """Configura terminale per input raw"""
        if platform.system() != "Windows":
            self.old_settings = termios.tcgetattr(sys.stdin)
            tty.setcbreak(sys.stdin.fileno())
    
    def restore_terminal(self):
        """Ripristina terminale"""
        if platform.system() != "Windows" and self.old_settings:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self.old_settings)
    
    def get_char(self) -> Optional[str]:
        """Legge carattere da stdin (non bloccante)"""
        if platform.system() == "Windows":
            if msvcrt.kbhit():
                char = msvcrt.getch().decode('utf-8', errors='ignore')
                if char == '\xe0':
                    char = msvcrt.getch().decode('utf-8', errors='ignore')
                    return {'H': 'UP', 'P': 'DOWN', 'M': 'RIGHT', 'K': 'LEFT'}.get(char)
                return char if char != '\x1b' else 'ESC'
            return None
        else:
            fd = sys.stdin.fileno()
            # Usa os.read() direttamente: sys.stdin.read(1) chiama internamente
            # os.read(fd, 8192) e mette [A nel buffer Python; il select() successivo
            # controlla il fd OS (ora vuoto) e restituisce False → frecce rotte.
            if not select.select([fd], [], [], 0.05)[0]:
                return None
            try:
                char = os.read(fd, 1).decode('utf-8', errors='ignore')
            except Exception:
                return None
            if char == '\x1b':
                # Controlla se seguono byte di sequenza (frecce) senza bloccare
                if select.select([fd], [], [], 0.05)[0]:
                    try:
                        seq = os.read(fd, 2).decode('utf-8', errors='ignore')
                        return {'[A': 'UP', '[B': 'DOWN', '[C': 'RIGHT', '[D': 'LEFT'}.get(seq, 'ESC')
                    except Exception:
                        pass
                return 'ESC'
            return char
    
    def handle_input(self):
        """Loop gestione input"""
        while self.running:
            char = self.get_char()
            
            if not char:
                continue
            
            try:
                # Modalità ricerca RadioBrowser
                if self.search_mode:
                    if char == 'ESC':
                        self.exit_search_mode()
                    elif char == 'UP':
                        if self.search_results:
                            self.search_selected_idx = max(0, self.search_selected_idx - 1)
                            self.pending_updates |= UpdateFlags.STATIONS
                    elif char == 'DOWN':
                        if self.search_results:
                            self.search_selected_idx = min(
                                len(self.search_results) - 1, self.search_selected_idx + 1
                            )
                            self.pending_updates |= UpdateFlags.STATIONS
                    elif char in ('\r', '\n'):
                        # Aggiungi stazione selezionata al M3U
                        if self.search_results and 0 <= self.search_selected_idx < len(self.search_results):
                            self.add_station_to_m3u(self.search_results[self.search_selected_idx])
                    elif char.lower() == 'p':
                        # Ascolta anteprima senza aggiungere al M3U
                        if self.search_results and 0 <= self.search_selected_idx < len(self.search_results):
                            self.play_preview(self.search_results[self.search_selected_idx])
                    elif char == ' ':
                        # Ferma anteprima
                        if self.state.is_playing:
                            self.stop()
                            self.show_temp_message("⏹ Anteprima fermata")
                    elif char in ('\x7f', '\x08'):  # Backspace / DEL
                        if self.search_query:
                            self.search_query = self.search_query[:-1]
                            self._trigger_search()
                            self.pending_updates |= UpdateFlags.STATUS
                    elif len(char) == 1 and char.isprintable():
                        self.search_query += char
                        self._trigger_search()
                        self.pending_updates |= UpdateFlags.STATUS
                    continue

                # Modalità input numerico
                if self.number_input_mode:
                    if char.isdigit():
                        self.number_buffer += char
                        self.pending_updates |= UpdateFlags.INPUT
                    elif char in ('\r', '\n'):
                        if self.number_buffer:
                            self.select_by_number(int(self.number_buffer))
                        self.number_input_mode = False
                        self.number_buffer = ""
                        self.pending_updates |= UpdateFlags.INPUT
                    elif char == 'ESC':
                        self.number_input_mode = False
                        self.number_buffer = ""
                        self.pending_updates |= UpdateFlags.INPUT
                    continue
                
                # Comandi normali
                if char.lower() == 'q':
                    logger.info("Richiesta uscita utente")
                    self.running = False
                elif char.lower() == 'p' or char == ' ' or char in ('\r', '\n'):
                    self.toggle_play_pause()
                elif char.lower() == 'm':
                    self.toggle_mute()
                elif char in ('+', '='):
                    self.change_volume(5)
                elif char in ('-', '_'):
                    self.change_volume(-5)
                elif char == 'UP':
                    self.change_selection(-1)
                elif char == 'DOWN':
                    self.change_selection(1)
                elif char.lower() == 't':
                    self.toggle_notifications()
                elif char.lower() == 'l':
                    # Toggle logging
                    self.toggle_logging()
                elif char.lower() == 'r':
                    # Toggle registrazione
                    self.toggle_recording()
                elif char.lower() == 's':
                    # Salva cronologia
                    path = Path(f"radio_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
                    self.history.export(path)
                    self.show_temp_message(f"💾 Salvato: {path.name}")
                    logger.info(f"Cronologia salvata: {path}")
                elif char.lower() == 'h':
                    self.show_history()
                elif char.lower() == 'b':
                    self.enter_search_mode()
                elif char.isdigit():
                    self.number_input_mode = True
                    self.number_buffer = char
                    self.pending_updates |= UpdateFlags.INPUT
                
            except Exception as e:
                logger.error(f"Errore gestione input: {e}", exc_info=True)
    
    def run(self, m3u_file: Optional[Path] = None):
        """Loop principale"""
        try:
            self.setup_terminal()
            
            # Carica M3U
            if m3u_file:
                if not self.load_m3u(m3u_file):
                    print(f"❌ Impossibile caricare {m3u_file}")
                    return
            else:
                # Cerca file M3U nella directory corrente
                m3u_files = list(Path('.').glob('*.m3u'))
                if m3u_files:
                    if not self.load_m3u(m3u_files[0]):
                        print("❌ Errore caricamento M3U")
                        return
                else:
                    print("❌ Nessun file M3U trovato")
                    print("Uso: python3 radio_player_improved.py [file.m3u]")
                    return
            
            # Avvia thread input
            self.executor.submit(self.handle_input)
            
            # Loop principale con Rich o TUI base
            if self.use_rich:
                self._run_rich_loop()
            else:
                self._run_tui_loop()
            
        except KeyboardInterrupt:
            logger.info("Interrotto da utente (Ctrl+C)")
        except Exception as e:
            logger.error(f"Errore critico: {e}", exc_info=True)
        finally:
            self.stop()
            self.metadata_monitor.stop()
            self.executor.shutdown(wait=False)
            self.restore_terminal()
            
            if self.use_rich:
                self.console.clear()
            else:
                os.system('clear' if os.name == 'posix' else 'cls')
            
            print("👋 Arrivederci!")
            logger.info("Applicazione terminata")
    
    def _run_rich_loop(self):
        """Loop principale con Rich UI"""
        logger.info("Avvio loop Rich UI")
        
        with Live(self._render_rich(), console=self.console, 
                 refresh_per_second=10, screen=True) as live:
            self.live = live
            
            last_timer_update = 0
            
            while self.running:
                current_time = time.time()
                
                # Aggiorna timer ogni secondo
                if current_time - last_timer_update >= 1.0:
                    self.pending_updates |= UpdateFlags.TIMER
                    last_timer_update = current_time
                
                # In riproduzione, aggiorna anche info brano ogni secondo (per il tempo)
                if self.state.is_playing:
                    self.pending_updates |= UpdateFlags.SONG
                
                # Aggiorna status se c'è messaggio temporaneo
                if self.temp_message and (current_time - self.temp_message_time) < 5:
                    self.pending_updates |= UpdateFlags.STATUS
                
                # SEMPRE renderizza se ci sono aggiornamenti o se sta riproducendo
                # (per catturare metadata che arrivano dai thread)
                if self.pending_updates != UpdateFlags.NONE or self.state.is_playing:
                    live.update(self._render_rich())
                    self.pending_updates = UpdateFlags.NONE
                
                time.sleep(0.1)
    
    def _run_tui_loop(self):
        """Loop principale con TUI base (fallback)"""
        logger.info("Avvio loop TUI base")
        
        os.system('clear' if os.name == 'posix' else 'cls')
        print("=" * 70)
        print("🎵 RADIO PLAYER M3U")
        print("=" * 70)
        print("\nModalità TUI base (installa 'rich' per UI migliorata)")
        print("\nComandi: p=play, q=quit, ↑/↓=seleziona, +/-=volume, m=muto\n")
        
        while self.running:
            current_time = time.time()
            
            if current_time - self.last_render_time >= 1.0:
                # Aggiornamento base ogni secondo
                status = "▶️ Playing" if self.state.is_playing else "⏹️ Stopped"
                
                if self.state.playing_station_index >= 0:
                    station = self.stations[self.state.playing_station_index]
                    print(f"\r{status} | {station.name[:40]:<40} | Vol: {self.state.volume}%", end="", flush=True)
                else:
                    print(f"\r{status} | {'No station':<40} | Vol: {self.state.volume}%", end="", flush=True)
                
                self.last_render_time = current_time
            
            time.sleep(0.1)

# ============================================================================
# MAIN
# ============================================================================

def main():
    """Funzione principale"""
    print("=" * 70)
    print("Radio Player M3U v2.0 - VERSIONE MIGLIORATA")
    print("Copyright (C) 2025 Andres Zanzani <azanzani@gmail.com>")
    print("=" * 70)
    print()
    
    m3u_file = None
    if len(sys.argv) > 1:
        m3u_file = Path(sys.argv[1])
        if not m3u_file.exists():
            print(f"❌ File non trovato: {m3u_file}")
            return
    
    try:
        player = RadioPlayer()
        player.run(m3u_file)
    except Exception as e:
        logger.error(f"Errore fatale: {e}", exc_info=True)
        print(f"❌ Errore: {e}")

if __name__ == "__main__":
    main()
