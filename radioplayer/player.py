"""RadioPlayer core class."""

import logging
import os
import platform
import queue
import re
import select
import signal
import subprocess
import sys
import termios
import threading
import time
import tty
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Any

from .config import load_config, save_config
from .logging_setup import setup_logging, enable_file_logging, disable_file_logging
from .m3u import M3UParser
from .metadata import MetadataHistory, MetadataMonitor
from .models import RadioStation, StreamInfo, PlayerState, UpdateFlags
from .mpv_controller import MPVController
from .radio_browser import RadioBrowserAPI
from .tray import SystemTrayIcon
from .ui import RichUIMixin, RICH_AVAILABLE, Live

logger = setup_logging()

if platform.system() == "Windows":
    import msvcrt


class RadioPlayer(RichUIMixin):
    """Radio Player principale con gestione avanzata"""

    def __init__(self, use_rich: bool = RICH_AVAILABLE):
        self.use_rich = use_rich and RICH_AVAILABLE

        self.stations: List[RadioStation] = []
        self.state = PlayerState()
        self.mpv_controller = MPVController()
        self.metadata_monitor = MetadataMonitor(self._on_metadata_update)
        self.history = MetadataHistory()

        self.executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="RadioPlayer")
        self.update_queue: queue.Queue = queue.Queue()

        self.running = True
        self.pending_updates = UpdateFlags.FULL
        self._executor_closed = False
        self._last_notified_title = ""

        if self.use_rich:
            from rich.console import Console
            self.console = Console()
        self.live = None

        self.old_settings = None

        self.number_input_mode = False
        self.number_buffer = ""

        self.is_recording = False
        self.recording_process: Optional[subprocess.Popen] = None
        self.recording_file: Optional[Path] = None

        self.logging_enabled = False

        self.temp_message = ""
        self.temp_message_time = 0.0

        self.show_history_overlay = False

        self.radio_browser = RadioBrowserAPI()
        self.search_mode = False
        self.search_query = ""
        self.search_results: List[RadioStation] = []
        self.search_selected_idx = 0
        self.search_loading = False
        self._search_timer: Optional[threading.Timer] = None
        self._last_searched_query = ""
        self._preview_station: Optional[RadioStation] = None
        self.m3u_file_path: Optional[Path] = None

        # Group filter
        self.group_filter: Optional[str] = None
        self.available_groups: List[str] = []

        # Favorites (set of URLs)
        self.favorites: set = set()

        # Local M3U search
        self.local_search_mode = False
        self.local_search_query = ""

        # EQ presets (filter string per IPC mpv, senza prefisso --af=)
        self.eq_presets = [
            "",
            "equalizer=f=100:width=200:g=3,equalizer=f=200:width=200:g=3",
            "equalizer=f=3000:width=1000:g=-2",
            "equalizer=f=100:width=200:g=6,equalizer=f=10000:width=2000:g=-3",
            "equalizer=f=400:width=400:g=4,equalizer=f=2500:width=1000:g=2",
        ]
        self.eq_preset_idx = 0
        self.eq_names = ["Flat", "Bass Boost", "Voice", "Classical", "Rock"]

        # Help overlay
        self.show_help_overlay = False

        self.tray = SystemTrayIcon(self)

        self.session_start_time = time.time()
        self.last_render_time = 0.0
        self.min_render_interval = 0.1

        self._load_user_config()

        logger.info(f"Inizializzato RadioPlayer (Rich UI: {self.use_rich})")

        if not self._check_mpv():
            print("\u274c MPV non installato!")
            print("   Ubuntu/Debian: sudo apt install mpv")
            print("   Fedora: sudo dnf install mpv")
            print("   macOS: brew install mpv")
            sys.exit(1)

    def _check_mpv(self) -> bool:
        """Verifica disponibilita' MPV"""
        try:
            subprocess.run(
                ['mpv', '--version'],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
            )
            logger.info("MPV disponibile")
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.error("MPV non trovato")
            return False

    def _load_user_config(self) -> None:
        """Carica config utente e applica le preferenze salvate."""
        config = load_config()
        self.state.volume = config.get("volume", 50)
        self.state.show_song_popups = config.get("show_song_popups", True)
        if config.get("logging_enabled"):
            self.logging_enabled = True
            enable_file_logging(logger)
        self.favorites = set(config.get("favorites", []))
        self.group_filter = config.get("group_filter")
        self.eq_preset_idx = config.get("eq_preset_idx", 0)

    def _save_user_config(self) -> None:
        """Salva config utente."""
        save_config({
            "volume": self.state.volume,
            "show_song_popups": self.state.show_song_popups,
            "logging_enabled": self.logging_enabled,
            "last_m3u": str(self.m3u_file_path) if self.m3u_file_path else None,
            "favorites": list(self.favorites),
            "group_filter": self.group_filter,
            "eq_preset_idx": self.eq_preset_idx,
        })

    def _submit_worker(self, fn, *args, **kwargs):
        """Sottomette un task all'executor se ancora aperto, altrimenti no-op."""
        if self.running and not self._executor_closed:
            try:
                return self.executor.submit(fn, *args, **kwargs)
            except RuntimeError:
                pass
        return None

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
        logger.info(f"Metadata update: {key} = {value}")

        if key == 'bitrate':
            if not self.state.stream_info.bitrate:
                self.state.stream_info = self.state.stream_info.replace(bitrate=value)
                self.pending_updates |= UpdateFlags.SONG

        elif key == 'stream_title':
            old_title = self.state.stream_info.title

            if not value and old_title:
                return

            if ' - ' in value:
                artist, song = value.split(' - ', 1)
                artist = artist.strip()
                song = song.strip()

                if artist != self.state.stream_info.artist or song != self.state.stream_info.song:
                    self.state.stream_info = self.state.stream_info.replace(
                        artist=artist,
                        song=song,
                        title=value,
                        song_start_time=time.time(),
                        pause_start_time=None,
                        total_pause_time=0.0,
                    )

                    if self.state.playing_station_index >= 0:
                        station_name = self.stations[self.state.playing_station_index].name
                        self.history.add(artist, song, station_name)

                    if self.state.show_song_popups and old_title and value != self._last_notified_title:
                        self._last_notified_title = value
                        self._show_notification(f"{artist} - {song}")

                    self.show_temp_message(f"\U0001f3b5 {artist} - {song}")
                    self.pending_updates |= UpdateFlags.SONG | UpdateFlags.STATUS
                    logger.info(f"Nuovo brano: {artist} - {song}")
                    self.tray.update()
            else:
                if value != self.state.stream_info.song:
                    self.state.stream_info = self.state.stream_info.replace(
                        artist="",
                        song=value,
                        title=value,
                        song_start_time=time.time(),
                        pause_start_time=None,
                        total_pause_time=0.0,
                    )

                    if self.state.playing_station_index >= 0:
                        station_name = self.stations[self.state.playing_station_index].name
                        self.history.add("", value, station_name)

                    if self.state.show_song_popups and old_title and value != self._last_notified_title:
                        self._last_notified_title = value
                        self._show_notification(value)

                    self.show_temp_message(f"\U0001f3b5 {value}")
                    self.pending_updates |= UpdateFlags.SONG | UpdateFlags.STATUS
                    logger.info(f"Nuovo brano: {value}")
                    self.tray.update()

    def _show_notification(self, message: str):
        """Mostra notifica di sistema"""
        if not self.state.show_song_popups:
            return

        try:
            if platform.system() == "Windows":
                try:
                    from win10toast import ToastNotifier
                    toaster = ToastNotifier()
                    toaster.show_toast("\U0001f3b5 Radio Player", message,
                                     icon_path=None, duration=4, threaded=True)
                except ImportError:
                    pass
            else:
                subprocess.run(
                    ['notify-send', '\U0001f3b5 Radio Player', message,
                     '--icon=audio-x-generic', '--expire-time=4000'],
                    check=True, capture_output=True, timeout=2,
                )
        except Exception:
            logger.debug("Notifica fallita")

    def play_selected(self):
        """Avvia riproduzione della stazione selezionata"""
        if not self.stations:
            return

        station = self.stations[self.state.selected_station_index]
        logger.info(f"Play stazione: {station.name}")

        self.stop()

        if self.mpv_controller.start(station.url, self.state.volume):
            self.state.is_playing = True
            self.state.is_paused = False
            self.state.playing_station_index = self.state.selected_station_index
            self.state.stream_info = StreamInfo(
                start_time=time.time(),
                song_start_time=time.time(),
            )

            self.metadata_monitor.start(station.url)
            self._submit_worker(self.metadata_monitor.monitor_loop)
            self._submit_worker(self._stats_monitor_loop)

            self.pending_updates |= UpdateFlags.STATUS | UpdateFlags.SONG | UpdateFlags.STATIONS

            logger.info("Riproduzione avviata")
            self.tray.update()
        else:
            logger.error("Impossibile avviare riproduzione")

    def stop(self):
        """Ferma riproduzione. MPV e' SEMPRE ucciso (anche se lo stato e' desync)."""
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
        self.tray.update()

    def toggle_play_pause(self):
        """Toggle play/pause"""
        if not self.stations:
            return

        if not self.state.is_playing:
            self.play_selected()
        else:
            if self.state.playing_station_index != self.state.selected_station_index:
                self.play_selected()
            else:
                if self.state.is_paused:
                    self.state.is_paused = False
                    extra_pause = time.time() - self.state.stream_info.pause_start_time if self.state.stream_info.pause_start_time else 0
                    self.state.stream_info = self.state.stream_info.replace(
                        total_pause_time=self.state.stream_info.total_pause_time + extra_pause,
                        pause_start_time=None,
                    )
                    self.pending_updates |= UpdateFlags.STATUS | UpdateFlags.SONG
                    logger.info("Riproduzione ripresa")
                    self.tray.update()
                else:
                    self.state.is_paused = True
                    self.state.stream_info = self.state.stream_info.replace(
                        pause_start_time=time.time(),
                    )
                    self.pending_updates |= UpdateFlags.STATUS | UpdateFlags.SONG
                    logger.info("Riproduzione in pausa")
                    self.tray.update()

    def change_volume(self, delta: int):
        """Cambia volume"""
        self.state.volume = max(0, min(100, self.state.volume + delta))

        if self.state.is_playing:
            self.mpv_controller.set_volume(self.state.volume)

        self.pending_updates |= UpdateFlags.TIMER
        logger.debug(f"Volume: {self.state.volume}%")
        self.tray.update()
        self._save_user_config()

    def toggle_mute(self):
        """Toggle muto"""
        self.state.is_muted = not self.state.is_muted

        if self.state.is_playing:
            self.mpv_controller.set_mute(self.state.is_muted)

        self.pending_updates |= UpdateFlags.TIMER
        logger.debug(f"Muto: {self.state.is_muted}")
        self.tray.update()

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
        self.show_temp_message(f"\U0001f514 Notifiche: {status}")
        logger.info(f"Notifiche: {status}")
        self._save_user_config()

    def toggle_logging(self):
        """Toggle logging su file"""
        self.logging_enabled = not self.logging_enabled

        if self.logging_enabled:
            enable_file_logging(logger)
            logger.info("Logging abilitato dall'utente")
        else:
            disable_file_logging(logger)

        status = "ON" if self.logging_enabled else "OFF"
        self.show_temp_message(f"\U0001f4dd Logging: {status}")
        self.pending_updates |= UpdateFlags.TIMER
        self._save_user_config()

    def toggle_recording(self):
        """Toggle registrazione stream"""
        if not self.state.is_playing:
            self.show_temp_message("\u274c Avvia prima una stazione")
            return

        if self.is_recording:
            self.stop_recording()
        else:
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
            # ffmpeg apre una seconda connessione allo stream per registrare.
            # Questo raddoppia la banda ma garantisce una registrazione
            # indipendente dal player (se MPV ha glitch, il file e' pulito).
            cmd = [
                'ffmpeg',
                '-i', station.url,
                '-c', 'copy',
                '-y',
                str(self.recording_file),
            ]

            self.recording_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            self.is_recording = True
            self.pending_updates |= UpdateFlags.STATUS
            self.show_temp_message(f"\U0001f534 Registrazione avviata: {self.recording_file.name}")
            logger.info(f"Registrazione avviata: {self.recording_file}")

        except FileNotFoundError:
            self.show_temp_message("\u274c ffmpeg non installato (apt install ffmpeg)")
            logger.error("ffmpeg non disponibile per registrazione")
        except Exception as e:
            self.show_temp_message(f"\u274c Errore registrazione: {e}")
            logger.error(f"Errore avvio registrazione: {e}")

    def stop_recording(self):
        """Ferma registrazione"""
        if not self.is_recording:
            return

        try:
            if self.recording_process:
                self.recording_process.terminate()
                try:
                    self.recording_process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.recording_process.kill()
                    self.recording_process.wait(timeout=2)
                self.recording_process = None

            self.is_recording = False
            self.pending_updates |= UpdateFlags.STATUS

            if self.recording_file and self.recording_file.exists():
                size_mb = self.recording_file.stat().st_size / (1024 * 1024)
                self.show_temp_message(f"\u23f9\ufe0f Registrazione salvata: {self.recording_file.name} ({size_mb:.1f} MB)")
                logger.info(f"Registrazione salvata: {self.recording_file} ({size_mb:.1f} MB)")
            else:
                self.show_temp_message("\u23f9\ufe0f Registrazione fermata")

            self.recording_file = None

        except Exception as e:
            self.show_temp_message(f"\u274c Errore stop registrazione: {e}")
            logger.error(f"Errore stop registrazione: {e}")

    def show_temp_message(self, message: str):
        """Mostra messaggio temporaneo nell'UI"""
        self.temp_message = message
        self.temp_message_time = time.time()
        self.pending_updates |= UpdateFlags.STATUS

    def show_history(self):
        """Mostra/nasconde overlay cronologia ultimi brani"""
        self.show_history_overlay = not self.show_history_overlay
        self.pending_updates |= UpdateFlags.FULL
        last = self.history.get_last(10)
        if not last:
            self.show_temp_message("\U0001f4dc Cronologia vuota")
            self.show_history_overlay = False
        logger.info("Toggle overlay cronologia")

    # ========================================================================
    # FILTRO GRUPPI, PREFERITI, RICERCA LOCALE, EQ
    # ========================================================================

    def _get_filtered_stations(self):
        """Restituisce le stazioni filtrate per gruppo e/o ricerca locale."""
        stations = self.stations
        if self.group_filter:
            stations = [s for s in stations if s.group == self.group_filter]
        if self.local_search_mode and self.local_search_query:
            query = self.local_search_query.lower()
            stations = [s for s in stations if query in s.name.lower()]
        return stations

    def _refresh_groups(self):
        """Aggiorna la lista dei gruppi disponibili."""
        groups = set()
        for s in self.stations:
            groups.add(s.group)
        self.available_groups = sorted(groups)

    def cycle_group_filter(self):
        """Cicla il filtro per gruppo."""
        self._refresh_groups()
        if not self.available_groups:
            self.group_filter = None
            self.show_temp_message("\U0001f4cb Nessun gruppo trovato")
            return
        if self.group_filter is None:
            self.group_filter = self.available_groups[0]
        else:
            try:
                idx = self.available_groups.index(self.group_filter)
                next_idx = (idx + 1) % (len(self.available_groups) + 1)
                if next_idx == len(self.available_groups):
                    self.group_filter = None
                else:
                    self.group_filter = self.available_groups[next_idx]
            except ValueError:
                self.group_filter = self.available_groups[0]
        label = self.group_filter or "Tutti"
        self.show_temp_message(f"\U0001f4cb Gruppo: {label}")
        self.state.selected_station_index = 0
        self.pending_updates |= UpdateFlags.FULL
        self._save_user_config()

    def toggle_favorite(self):
        """Aggiunge/rimuove stazione selezionata dai preferiti."""
        if not self.stations:
            return
        station = self.stations[self.state.selected_station_index]
        if station.url in self.favorites:
            self.favorites.discard(station.url)
            self.show_temp_message(f"\u2b50 Rimossa: {station.name}")
        else:
            self.favorites.add(station.url)
            self.show_temp_message(f"\u2b50 Preferita: {station.name}")
        self.pending_updates |= UpdateFlags.STATIONS
        self._save_user_config()

    def enter_local_search_mode(self):
        """Entra in modalita' ricerca locale nel M3U."""
        self.local_search_mode = True
        self.local_search_query = ""
        self.pending_updates |= UpdateFlags.FULL

    def exit_local_search_mode(self):
        """Esce dalla modalita' ricerca locale."""
        self.local_search_mode = False
        self.local_search_query = ""
        self.pending_updates |= UpdateFlags.FULL

    def _update_local_search(self):
        """Aggiorna la selezione in base alla ricerca locale."""
        query = self.local_search_query.lower()
        if not query:
            return
        for i, s in enumerate(self.stations):
            if query in s.name.lower():
                self.state.selected_station_index = i
                break
        self.pending_updates |= UpdateFlags.STATIONS

    def cycle_eq(self):
        """Cicla tra i preset di equalizzazione."""
        self.eq_preset_idx = (self.eq_preset_idx + 1) % len(self.eq_presets)
        preset = self.eq_presets[self.eq_preset_idx]
        name = self.eq_names[self.eq_preset_idx]
        if self.state.is_playing:
            self.mpv_controller.ipc_client.send_command("af", "set", preset)
        self.show_temp_message(f"\U0001f3a7 EQ: {name}")
        self._save_user_config()

    def toggle_help(self):
        """Mostra/nasconde la schermata di aiuto."""
        self.show_help_overlay = not self.show_help_overlay
        self.pending_updates |= UpdateFlags.FULL

    def jump_to_letter(self, letter: str):
        """Salta alla prima stazione (dalla corrente, con wrap) che inizia con la lettera."""
        if not self.stations:
            return
        letter = letter.lower()
        n = len(self.stations)
        for offset in range(1, n + 1):
            idx = (self.state.selected_station_index + offset) % n
            if self.stations[idx].name.lower().startswith(letter):
                self.state.selected_station_index = idx
                self.pending_updates |= UpdateFlags.STATIONS
                self.show_temp_message(f"\U0001f50d {letter.upper()}: {self.stations[idx].name}")
                return
        # Nessuna stazione trovata
        self.show_temp_message(f"\U0001f50d Nessuna stazione con {letter.upper()}")

    def remove_selected_station(self):
        """Rimuove la stazione selezionata dalla lista e dal file M3U."""
        if not self.stations or not self.m3u_file_path:
            self.show_temp_message("\u274c Nessuna stazione da rimuovere")
            return
        idx = self.state.selected_station_index
        if idx < 0 or idx >= len(self.stations):
            return
        station = self.stations[idx]
        name = station.name

        if self.state.playing_station_index == idx:
            self.stop()
        elif self.state.playing_station_index > idx:
            self.state.playing_station_index -= 1

        self.favorites.discard(station.url)
        self.stations.pop(idx)

        if idx >= len(self.stations):
            self.state.selected_station_index = max(0, len(self.stations) - 1)

        self._save_m3u_file()
        self.show_temp_message(f"\U0001f5d1\ufe0f Rimossa: {name}")
        self.pending_updates |= UpdateFlags.STATIONS | UpdateFlags.STATUS
        self._save_user_config()

    def _save_m3u_file(self):
        """Riscrive il file M3U con le stazioni correnti."""
        if not self.m3u_file_path:
            return
        lines = ["#EXTM3U\n"]
        for s in self.stations:
            attrs = []
            if s.metadata.get("group-title"):
                attrs.append(f'group-title="{s.metadata["group-title"]}"')
            if s.logo:
                attrs.append(f'tvg-logo="{s.logo}"')
            attr_str = " " + " ".join(attrs) if attrs else ""
            lines.append(f"#EXTINF:-1{attr_str},{s.name}\n")
            lines.append(f"{s.url}\n")
        try:
            self.m3u_file_path.write_text("".join(lines), encoding="utf-8")
        except OSError:
            pass

    # ========================================================================
    # RICERCA RADIOBROWSER
    # ========================================================================

    def enter_search_mode(self):
        """Entra in modalita' sfoglia RadioBrowser.info"""
        self.search_mode = True
        self.search_query = ""
        self.search_results = []
        self.search_selected_idx = 0
        self.search_loading = False
        self.pending_updates |= UpdateFlags.FULL
        logger.info("Entrato in modalita' ricerca RadioBrowser")

    def exit_search_mode(self):
        """Esce dalla modalita' ricerca"""
        if self._search_timer:
            self._search_timer.cancel()
            self._search_timer = None
        self.search_mode = False
        self.pending_updates |= UpdateFlags.FULL
        logger.info("Uscito dalla modalita' ricerca")

    def _trigger_search(self):
        """Avvia ricerca con debounce di 0.3s"""
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
            if query == self.search_query:
                self.search_results = results
                self.search_selected_idx = 0
                self.search_loading = False
                self._last_searched_query = query
                self.pending_updates |= UpdateFlags.STATIONS
        except Exception as e:
            logger.error(f"Errore ricerca: {e}")
            self.search_loading = False
            self._last_searched_query = query
            self.pending_updates |= UpdateFlags.STATIONS

    def play_preview(self, station: RadioStation):
        """Ascolta anteprima senza aggiungere al M3U. Toggle: p ferma se gia' attiva."""
        if self._preview_station and self._preview_station.url == station.url and self.state.is_playing:
            self.stop()
            self.show_temp_message("\u23f9 Anteprima fermata")
            return
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
            self._submit_worker(self.metadata_monitor.monitor_loop)
            self._submit_worker(self._stats_monitor_loop)
            self.pending_updates |= UpdateFlags.STATUS | UpdateFlags.SONG
            self.show_temp_message(f"\U0001f442 Anteprima: {station.name}")
            logger.info(f"Preview: {station.name}")
        else:
            self.show_temp_message("\u274c Impossibile avviare anteprima")

    def add_station_to_m3u(self, station: RadioStation) -> bool:
        """Aggiunge la stazione al file M3U evitando duplicati (URL e nome)"""
        if not self.m3u_file_path:
            self.show_temp_message("\u274c Nessun file M3U caricato")
            return False

        station_url = station.url.rstrip("/")
        for existing in self.stations:
            if existing.url.rstrip("/") == station_url:
                self.show_temp_message(f"\u26a0\ufe0f  Gia' presente: {existing.name}")
                return False

        station_name_lc = station.name.strip().lower()
        for existing in self.stations:
            if existing.name.strip().lower() == station_name_lc:
                self.show_temp_message(f"\u26a0\ufe0f  Nome gia' presente: {existing.name}")
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
            self.show_temp_message(f"\u2705 Aggiunta: {station.name}")
            logger.info(f"Aggiunta al M3U: {station.name} \u2014 {station.url}")
            return True

        except Exception as e:
            self.show_temp_message(f"\u274c Errore salvataggio: {e}")
            logger.error(f"Errore aggiunta stazione: {e}")
            return False

    def _stats_monitor_loop(self):
        """Loop monitoraggio statistiche MPV e METADATA"""
        logger.info("Avviato monitor statistiche")

        while self.state.is_playing and self.mpv_controller.is_running():
            try:
                if self.state.is_paused:
                    self.mpv_controller.set_mute(True)
                elif self.state.is_muted:
                    self.mpv_controller.set_mute(True)
                else:
                    self.mpv_controller.set_mute(False)

                stats = self.mpv_controller.get_audio_stats()

                updates = {}
                if stats.get('bitrate'):
                    updates['audio_bitrate'] = stats['bitrate']
                if stats.get('codec'):
                    updates['codec'] = stats['codec']
                if stats.get('cache'):
                    updates['cache_duration'] = stats['cache']
                if stats.get('buffer_status'):
                    old_buffer = self.state.stream_info.buffer_status
                    updates['buffer_status'] = stats['buffer_status']
                    if stats['buffer_status'] == "BUFFERING" and old_buffer != "BUFFERING":
                        self.pending_updates |= UpdateFlags.TECHNICAL

                if updates:
                    self.state.stream_info = self.state.stream_info.replace(**updates)

                # FALLBACK metadata via IPC MPV: usato SOLO se il monitor ICY
                # non sta gia' producendo titoli. Evita che MPV (piu' lento)
                # riproponga un titolo vecchio, causando notifiche duplicate.
                if not self.metadata_monitor.received_title:
                    metadata = self.mpv_controller.ipc_client.get_property("metadata")

                    if metadata and isinstance(metadata, dict):
                        current_title = (
                            metadata.get("icy-title")
                            or metadata.get("title")
                            or metadata.get("TITLE")
                        )

                        if current_title:
                            current_title = str(current_title).strip()
                            if current_title and current_title != self.state.stream_info.title:
                                self._on_metadata_update('stream_title', current_title)

                time.sleep(2)

            except Exception as e:
                logger.error(f"Errore monitor stats: {e}")
                break

        logger.info("Terminato monitor statistiche")

    # ========================================================================
    # INPUT E LOOP PRINCIPALE
    # ========================================================================

    def _install_signal_handlers(self):
        """Registra gestori per SIGHUP/SIGTERM per pulire mpv all'uscita forzata."""
        if platform.system() == "Windows":
            return
        try:
            signal.signal(signal.SIGHUP, self._handle_shutdown_signal)
            signal.signal(signal.SIGTERM, self._handle_shutdown_signal)
        except (ValueError, AttributeError, OSError):
            # Non siamo nel thread principale o segnale non disponibile
            pass

    def _handle_shutdown_signal(self, signum, frame):
        """Imposta running=False per far scattare la pulizia nel finally di run()."""
        logger.warning(f"Ricevuto segnale {signum}, chiusura in corso...")
        self.running = False

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
            if not select.select([fd], [], [], 0.05)[0]:
                return None
            try:
                char = os.read(fd, 1).decode('utf-8', errors='ignore')
            except Exception:
                return None
            if char == '\x1b':
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
                if self.search_mode:
                    if char == 'ESC':
                        self.exit_search_mode()
                        continue
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
                        if self.search_results and 0 <= self.search_selected_idx < len(self.search_results):
                            self.add_station_to_m3u(self.search_results[self.search_selected_idx])
                    elif char.lower() == 'p':
                        # p toggla anteprima: se gia' in ascolto di questa stazione, ferma
                        if self.search_results and 0 <= self.search_selected_idx < len(self.search_results):
                            self.play_preview(self.search_results[self.search_selected_idx])
                    elif char in ('\x7f', '\x08'):
                        if self.search_query:
                            self.search_query = self.search_query[:-1]
                            self._trigger_search()
                            self.pending_updates |= UpdateFlags.STATUS
                    elif len(char) == 1 and char.isprintable():
                        self.search_query += char
                        self._trigger_search()
                        self.pending_updates |= UpdateFlags.STATUS
                    continue

                # Modalita' ricerca locale M3U
                if self.local_search_mode:
                    if char == 'ESC' or char in ('\r', '\n'):
                        self.exit_local_search_mode()
                    elif char in ('\x7f', '\x08'):
                        if self.local_search_query:
                            self.local_search_query = self.local_search_query[:-1]
                            self._update_local_search()
                            self.pending_updates |= UpdateFlags.STATIONS
                    elif char == 'UP':
                        self.change_selection(-1)
                    elif char == 'DOWN':
                        self.change_selection(1)
                    elif len(char) == 1 and char.isprintable():
                        self.local_search_query += char
                        self._update_local_search()
                        self.pending_updates |= UpdateFlags.STATIONS
                    continue

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

                if self.show_help_overlay:
                    if char.lower() != '?':
                        self.show_help_overlay = False
                        self.pending_updates |= UpdateFlags.FULL
                        continue

                if self.show_history_overlay:
                    if char.lower() != 'h':
                        self.show_history_overlay = False
                        self.pending_updates |= UpdateFlags.FULL
                        continue

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
                    self.toggle_logging()
                elif char.lower() == 'r':
                    self.toggle_recording()
                elif char.lower() == 's':
                    path = Path(f"radio_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
                    self.history.export(path)
                    self.show_temp_message(f"\U0001f4be Salvato: {path.name}")
                    logger.info(f"Cronologia salvata: {path}")
                elif char.lower() == 'h':
                    self.show_history()
                elif char.lower() == 'b':
                    self.enter_search_mode()
                elif char.lower() == 'g':
                    self.cycle_group_filter()
                elif char == '*':
                    self.toggle_favorite()
                elif char.lower() == 'd':
                    self.remove_selected_station()
                elif char == '/':
                    self.enter_local_search_mode()
                elif char.lower() == 'e':
                    self.cycle_eq()
                elif char.lower() == '?':
                    self.toggle_help()
                elif char.isdigit():
                    self.number_input_mode = True
                    self.number_buffer = char
                    self.pending_updates |= UpdateFlags.INPUT
                elif char.isalpha():
                    self.jump_to_letter(char)

            except Exception as e:
                logger.error(f"Errore gestione input: {e}", exc_info=True)

    def run(self, m3u_file: Optional[Path] = None):
        """Loop principale"""
        try:
            self._install_signal_handlers()
            self.setup_terminal()

            if m3u_file:
                if not self.load_m3u(m3u_file):
                    print(f"\u274c Impossibile caricare {m3u_file}")
                    return
            else:
                m3u_files = find_m3u_files()
                if m3u_files:
                    if not self.load_m3u(m3u_files[0]):
                        print("\u274c Errore caricamento M3U")
                        return
                else:
                    print("\u274c Nessun file M3U trovato")
                    print(f"Uso: python3 {Path(sys.argv[0]).name} [file.m3u]")
                    return

            self.tray.start()

            self._submit_worker(self.handle_input)

            if self.use_rich:
                self._run_rich_loop()
            else:
                self._run_tui_loop()

        except KeyboardInterrupt:
            logger.info("Interrotto da utente (Ctrl+C)")
        except Exception as e:
            logger.error(f"Errore critico: {e}", exc_info=True)
        finally:
            self.running = False
            self._executor_closed = True
            self.stop()
            self.metadata_monitor.stop()
            self.tray.stop()
            self.executor.shutdown(wait=False)
            self.restore_terminal()

            if self.use_rich:
                self.console.clear()
            else:
                os.system('clear' if os.name == 'posix' else 'cls')

            print("\U0001f44b Arrivederci!")
            logger.info("Applicazione terminata")

    def _run_rich_loop(self):
        """Loop principale con Rich UI"""
        logger.info("Avvio loop Rich UI")

        with Live(self._render_rich(), console=self.console,
                  refresh_per_second=8, screen=True) as live:
            self.live = live

            last_timer_update = 0.0

            while self.running:
                current_time = time.time()

                if current_time - last_timer_update >= 1.0:
                    self.pending_updates |= UpdateFlags.TIMER
                    last_timer_update = current_time

                if self.state.is_playing:
                    self.pending_updates |= UpdateFlags.SONG

                if self.temp_message and (current_time - self.temp_message_time) < 2:
                    self.pending_updates |= UpdateFlags.STATUS

                if self.pending_updates != UpdateFlags.NONE or self.state.is_playing:
                    live.update(self._render_rich())
                    self.pending_updates = UpdateFlags.NONE

                time.sleep(0.125)

    def _run_tui_loop(self):
        """Loop principale con TUI base (fallback)"""
        logger.info("Avvio loop TUI base")

        os.system('clear' if os.name == 'posix' else 'cls')
        print("=" * 70)
        print("\U0001f3b5 RADIO PLAYER M3U")
        print("=" * 70)
        print("\nModalita' TUI base (installa 'rich' per UI migliorata)")
        print("\nComandi: p=play, q=quit, \u2191/\u2193=seleziona, +/-=volume, m=muto\n")

        while self.running:
            current_time = time.time()

            if current_time - self.last_render_time >= 1.0:
                status = "\u25b6\ufe0f Playing" if self.state.is_playing else "\u23f9\ufe0f Stopped"

                if self.state.playing_station_index >= 0:
                    station = self.stations[self.state.playing_station_index]
                    print(f"\r{status} | {station.name[:40]:<40} | Vol: {self.state.volume}%", end="", flush=True)
                else:
                    print(f"\r{status} | {'No station':<40} | Vol: {self.state.volume}%", end="", flush=True)

                self.last_render_time = current_time

            time.sleep(0.1)

    @staticmethod
    def _find_m3u_files() -> List[Path]:
        """Cerca file M3U nella directory dello script e nella directory corrente"""
        found: dict = {}
        for directory in (Path(__file__).parent, Path.cwd()):
            for f in sorted(directory.glob('*.m3u')):
                found[f.resolve()] = f
        return list(found.values())


# Alias per la funzione top-level (usata da run())
find_m3u_files = RadioPlayer._find_m3u_files
