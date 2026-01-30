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
        logger.info("Inizializzato MetadataMonitor")
    
    def start(self, url: str):
        """Avvia il monitoraggio dei metadata"""
        self.current_url = url
        self.running = True
        logger.info(f"Avviato monitoraggio metadata per: {url}")
    
    def stop(self):
        """Ferma il monitoraggio"""
        self.running = False
        self.current_url = None
        logger.info("Fermato monitoraggio metadata")
    
    def monitor_loop(self):
        """Loop di monitoraggio metadata ICY"""
        while self.running and self.current_url:
            try:
                headers = {
                    'Icy-MetaData': '1',
                    'User-Agent': 'RadioPlayer/2.0'
                }
                
                with requests.get(self.current_url, headers=headers, 
                                stream=True, timeout=5) as response:
                    
                    # Estrai bitrate ICY
                    icy_bitrate = response.headers.get('icy-br', '')
                    if icy_bitrate:
                        self.update_callback('bitrate', f"{icy_bitrate} kbps")
                    
                    # Estrai metaint
                    metaint = response.headers.get('icy-metaint')
                    if not metaint:
                        logger.debug("Nessun icy-metaint, attendo...")
                        time.sleep(5)
                        continue
                    
                    metaint = int(metaint)
                    logger.debug(f"ICY metaint: {metaint}")
                    
                    while self.running:
                        # Leggi chunk audio
                        audio_data = response.raw.read(metaint)
                        if not audio_data:
                            break
                        
                        # Leggi lunghezza metadata
                        meta_length_byte = response.raw.read(1)
                        if not meta_length_byte:
                            break
                        
                        meta_length = ord(meta_length_byte) * 16
                        
                        if meta_length > 0:
                            # Leggi metadata
                            metadata = response.raw.read(meta_length)
                            metadata_str = metadata.decode('utf-8', errors='ignore')
                            
                            # Estrai StreamTitle
                            title_match = re.search(r"StreamTitle='([^']*)'", metadata_str)
                            if title_match:
                                stream_title = title_match.group(1).strip()
                                if stream_title:
                                    self.update_callback('stream_title', stream_title)
                                    logger.info(f"Metadata ICY: {stream_title}")
                
            except requests.RequestException as e:
                logger.warning(f"Errore richiesta metadata: {e}")
                time.sleep(5)
            except Exception as e:
                logger.error(f"Errore monitor metadata: {e}", exc_info=True)
                time.sleep(5)
        
        logger.info("Loop metadata terminato")

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
        self.executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="RadioPlayer")
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
            
            logger.info(f"Caricate {len(self.stations)} stazioni")
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
        
        # FIX UI: Aumentato size da 4 a 6 per garantire spazio al titolo brano
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="status", size=6), 
            Layout(name="stations", ratio=2),
            Layout(name="controls", size=8),
            Layout(name="footer", size=1)
        )
        
        return layout
    
    def _render_rich_header(self) -> Optional[Any]:
        """Renderizza header Rich"""
        if not RICH_AVAILABLE:
            return None
        
        current_time = datetime.now().strftime("%H:%M:%S")
        uptime = self.state.stream_info.get_uptime(
            self.state.is_playing, self.state.is_paused
        )
        
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
        """Renderizza status Rich"""
        if not RICH_AVAILABLE:
            return None
        if self.state.is_playing and not self.state.is_paused:
            status_icon = "▶️"
            status_text = "IN RIPRODUZIONE"
            status_style = "green"
        elif self.state.is_paused:
            status_icon = "⏸️"
            status_text = "IN PAUSA"
            status_style = "yellow"
        else:
            status_icon = "⏹️"
            status_text = "FERMATO"
            status_style = "red"
        
        lines = []
        lines.append(f"[bold {status_style}]{status_icon} {status_text}[/bold {status_style}]")
        
        # Info brano - SEMPRE VISIBILE SE CI SONO
        # NOTA: Spostate SOPRA il nome della stazione per evitare che vengano tagliate
        if self.state.stream_info.artist and self.state.stream_info.song:
            lines.append(f"[magenta]🎤 {self.state.stream_info.artist}[/magenta]")
            song_time = self.state.stream_info.get_song_time(
                self.state.is_playing, self.state.is_paused
            )
            lines.append(f"[bold blue]🎼 {self.state.stream_info.song}[/bold blue] [yellow][{song_time}][/yellow]")
            
        elif self.state.stream_info.song:
            song_time = self.state.stream_info.get_song_time(
                self.state.is_playing, self.state.is_paused
            )
            if song_time != "00:00":
                lines.append(f"[bold blue]🎼 {self.state.stream_info.song}[/bold blue] [yellow][{song_time}][/yellow]")
            else:
                lines.append(f"[bold blue]🎼 {self.state.stream_info.song}[/bold blue]")
                
        elif self.state.stream_info.title:
            lines.append(f"[bold blue]🎼 {self.state.stream_info.title}[/bold blue]")
            
        elif self.state.is_playing:
            lines.append("[dim italic]🎼 In attesa dei metadata dello stream...[/dim italic]")

        # Aggiungi indicatore registrazione
        if self.is_recording:
            lines.append("[bold red]  🔴 REGISTRAZIONE IN CORSO[/bold red]")
        
        if self.state.playing_station_index >= 0:
            station = self.stations[self.state.playing_station_index]
            lines.append(f"[cyan]📡 {station.name}[/cyan]")
        
        # Messaggio temporaneo DOPO le info brano
        if self.temp_message and (time.time() - self.temp_message_time) < 2:
            lines.append(f"[yellow]💬 {self.temp_message}[/yellow]")
        
        # Info tecniche
        tech_info = []
        if self.state.stream_info.audio_bitrate:
            tech_info.append(f"🔊 {self.state.stream_info.audio_bitrate}")
        elif self.state.stream_info.bitrate:
            tech_info.append(f"🔊 {self.state.stream_info.bitrate}")
        if self.state.stream_info.codec:
            tech_info.append(self.state.stream_info.codec)
        if self.state.stream_info.buffer_status:
            if self.state.stream_info.buffer_status == "BUFFERING":
                tech_info.append(f"🔄 {self.state.stream_info.buffer_status}")
            else:
                tech_info.append(f"📦 {self.state.stream_info.buffer_status}")
        
        if tech_info:
            lines.append(f"[dim]{' • '.join(tech_info)}[/dim]")
        
        content_str = "\n".join(lines)
        return Panel(content_str, title="Status", border_style="green")
    
    def _render_rich_stations(self) -> Optional[Any]:
        """Renderizza lista stazioni Rich"""
        if not RICH_AVAILABLE:
            return None
        
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Marker", style="cyan", width=4, no_wrap=True)
        table.add_column("Number", style="yellow", width=3, no_wrap=True)
        table.add_column("Name", style="white")
        
        # Mostra 10 stazioni centrate sulla selezione
        start_idx = max(0, self.state.selected_station_index - 5)
        end_idx = min(len(self.stations), start_idx + 10)
        
        if start_idx > 0:
            table.add_row("", "...", "⬆️  Altre stazioni sopra")
        
        for i in range(start_idx, end_idx):
            station = self.stations[i]
            
            # Marker con larghezza fissa (4 caratteri totali)
            # Formato: "XX  " dove XX può essere: "👉", "▶️", "⏸️", "  "
            marker = ""
            
            # Prima parte: selezione (2 char)
            if i == self.state.selected_station_index:
                marker += "👉"
            else:
                marker += "  "
            
            # Seconda parte: play status (2 char)  
            if i == self.state.playing_station_index and self.state.is_playing:
                if not self.state.is_paused:
                    marker += "▶️"
                else:
                    marker += "⏸️"
            else:
                marker += "  "
            
            # Applica stile inversione solo se selezionata
            style = "bold reverse" if i == self.state.selected_station_index else ""
            
            table.add_row(marker, str(i + 1), station.name, style=style)
        
        if end_idx < len(self.stations):
            table.add_row("", "...", "⬇️  Altre stazioni sotto")
        
        return Panel(table, title=f"📻 Stazioni ({len(self.stations)} totali)", 
                    border_style="blue")
    
    def _render_rich_controls(self) -> Optional[Any]:
        """Renderizza controlli Rich"""
        if not RICH_AVAILABLE:
            return None
        
        # Uso padding esplicito con spazi per allineamento
        controls = [
            ("↑/↓          ", "Seleziona stazione    ", "+/=           ", "Alza volume"),
            ("p/Spazio     ", "Play/Pausa            ", "-/_           ", "Abbassa volume"),
            ("m            ", "Muto/Riattiva         ", "1-9+Invio     ", "Vai a numero"),
            ("r            ", "Rec ON/OFF            ", "l             ", "Log ON/OFF"),
            ("t            ", "Toggle notifiche      ", "h             ", "Cronologia brani"),
            ("s            ", "Salva cronologia      ", "q             ", "Esci")
        ]
        
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column(justify="left", no_wrap=True, style="cyan")
        table.add_column(justify="left", no_wrap=True)
        table.add_column(justify="left", no_wrap=True, style="cyan")
        table.add_column(justify="left", no_wrap=True)
        
        for left_key, left_desc, right_key, right_desc in controls:
            table.add_row(left_key, left_desc, right_key, right_desc)
        
        # Input numerico
        if self.number_input_mode:
            input_text = Text()
            input_text.append("🔢 INSERISCI NUMERO: ", style="bold yellow")
            input_text.append(f"{self.number_buffer}_", style="bold white")
            input_text.append(" (Invio=conferma, Esc=annulla)", style="dim")
            table.add_row(input_text, "", "", "")
        
        return Panel(table, title="🎮 Controlli", border_style="yellow")
    
    def _render_rich_footer(self) -> Optional[Any]:
        """Renderizza footer Rich"""
        if not RICH_AVAILABLE:
            return None
        
        footer = Text()
        footer.append("© 2025 Andres Zanzani ", style="dim")
        footer.append("<azanzani@gmail.com>", style="dim blue")
        footer.append(" - GPL 3 License", style="dim")
        return footer
    
    def _render_rich(self) -> Optional[Any]:
        """Renderizza interfaccia completa Rich"""
        if not RICH_AVAILABLE:
            return None
        
        layout = self._build_rich_layout()
        
        layout["header"].update(self._render_rich_header())
        layout["status"].update(self._render_rich_status())
        layout["stations"].update(self._render_rich_stations())
        layout["controls"].update(self._render_rich_controls())
        layout["footer"].update(self._render_rich_footer())
        
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
            if select.select([sys.stdin], [], [], 0.05)[0]:
                char = sys.stdin.read(1)
                if char == '\x1b':
                    try:
                        next_chars = sys.stdin.read(2)
                        return {'[A': 'UP', '[B': 'DOWN', '[C': 'RIGHT', '[D': 'LEFT'}.get(next_chars, 'ESC')
                    except:
                        return 'ESC'
                return char
            return None
    
    def handle_input(self):
        """Loop gestione input"""
        while self.running:
            char = self.get_char()
            
            if not char:
                continue
            
            try:
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
                    # Mostra cronologia
                    self.show_history()
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
