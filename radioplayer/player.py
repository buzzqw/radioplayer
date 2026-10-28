"""RadioPlayer core class."""

import logging
import os
import platform
import re
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Tuple

from .config import load_config, save_config
from .logging_setup import (
    setup_logging,
    enable_file_logging,
    disable_file_logging,
    set_console_logging,
)
from .m3u import M3UParser, discover_m3u_files
from .metadata import MetadataHistory, MetadataMonitor
from .models import RadioStation, StreamInfo, PlayerState, UpdateFlags
from .mpv_controller import MPVController
from .radio_browser import RadioBrowserAPI
from .tray import SystemTrayIcon
from .ui import RichUIMixin, RICH_AVAILABLE, Live

logger = setup_logging()

if platform.system() == "Windows":
    import msvcrt
else:
    import select
    import termios
    import tty


class RadioPlayer(RichUIMixin):
    """Radio Player principale con gestione avanzata"""

    def __init__(self, use_rich: bool = RICH_AVAILABLE,
                 audio_device: Optional[str] = None,
                 color: bool = True,
                 use_tray: bool = True):
        self.use_rich = use_rich and RICH_AVAILABLE
        self.use_tray = use_tray

        self.stations: List[RadioStation] = []
        self.state = PlayerState()
        self.mpv_controller = MPVController(audio_device=audio_device)
        self.metadata_monitor = MetadataMonitor(self._on_metadata_update)
        self.history = MetadataHistory()
        self.history_file = Path.home() / ".config" / "radioplayer" / "history.json"
        self.history.load(self.history_file)

        self.running = True
        self.pending_updates = UpdateFlags.FULL
        self._last_notified_title = ""
        self._play_generation = 0
        self._icy_fallback_started = False
        self._play_started_at = 0.0

        if self.use_rich:
            from rich.console import Console
            self.console = Console(no_color=not color)
        self.live = None

        self.old_settings = None

        self.number_input_mode = False
        self.number_buffer = ""

        self.is_recording = False
        self.recording_process: Optional[subprocess.Popen] = None
        self.recording_file: Optional[Path] = None
        self._recording_via_mpv = False

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
        self.search_error = ""
        self.search_offset = 0
        self.search_has_more = False
        self.search_loading_more = False
        self._search_timer: Optional[threading.Timer] = None
        self._last_searched_query = ""
        self._preview_station: Optional[RadioStation] = None
        self.m3u_file_path: Optional[Path] = None
        self._last_m3u: Optional[Path] = None
        self._last_station_url: Optional[str] = None

        # Group filter
        self.group_filter: Optional[str] = None
        self.available_groups: List[str] = []

        # Favorites (set of URLs)
        self.favorites: set = set()
        self.show_favorites_only = False

        # Local M3U search
        self.local_search_mode = False
        self.local_search_query = ""

        # Cache della lista visibile (filtri gruppo/preferiti/ricerca)
        self._filtered_cache: Optional[List[Tuple[int, RadioStation]]] = None
        self._filtered_positions: dict = {}

        # Eliminazione con doppia conferma + undo
        self._pending_delete: Optional[Tuple[int, float]] = None
        self._last_deleted: Optional[Tuple[RadioStation, int, float]] = None

        # Overlay selezione gruppo
        self.show_group_overlay = False
        self.group_overlay_idx = 0

        # Layout adattivo
        self._stations_visible_rows = 10
        self._last_console_size: Optional[Tuple[int, int]] = None
        self._layout_has_footer = True

        # Debounce salvataggio configurazione
        self._config_save_timer: Optional[threading.Timer] = None
        self._config_lock = threading.Lock()

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
            logger.warning("MPV non trovato")
            return False

    def _load_user_config(self) -> None:
        """Carica config utente e applica le preferenze salvate."""
        config = load_config()
        self.state.volume = max(0, min(100, int(config.get("volume", 50))))
        self.state.show_song_popups = bool(config.get("show_song_popups", True))
        if config.get("logging_enabled"):
            self.logging_enabled = True
            enable_file_logging(logger)
        self.favorites = set(config.get("favorites", []))
        self.show_favorites_only = bool(config.get("favorites_only", False))
        self.group_filter = config.get("group_filter")
        self.eq_preset_idx = int(config.get("eq_preset_idx", 0))
        if not 0 <= self.eq_preset_idx < len(self.eq_presets):
            self.eq_preset_idx = 0
        last_m3u = config.get("last_m3u")
        if last_m3u:
            try:
                path = Path(last_m3u)
                if path.exists():
                    self._last_m3u = path
            except (TypeError, ValueError, OSError):
                self._last_m3u = None
        last_station = config.get("last_station")
        self._last_station_url = str(last_station) if last_station else None

    def _save_user_config(self) -> None:
        """Salva config utente."""
        m3u_path = self.m3u_file_path or self._last_m3u
        selected_url = None
        if 0 <= self.state.selected_station_index < len(self.stations):
            selected_url = self.stations[self.state.selected_station_index].url
        with self._config_lock:
            save_config({
                "volume": self.state.volume,
                "show_song_popups": self.state.show_song_popups,
                "logging_enabled": self.logging_enabled,
                "last_m3u": str(m3u_path) if m3u_path else None,
                "last_station": selected_url or self._last_station_url,
                "favorites": list(self.favorites),
                "favorites_only": self.show_favorites_only,
                "group_filter": self.group_filter,
                "eq_preset_idx": self.eq_preset_idx,
            })

    def _schedule_config_save(self, delay: float = 1.0) -> None:
        """Salva la config dopo un breve ritardo (evita I/O a ogni tasto)."""
        if self._config_save_timer is not None:
            self._config_save_timer.cancel()
        timer = threading.Timer(delay, self._save_user_config)
        timer.daemon = True
        timer.start()
        self._config_save_timer = timer

    def _cancel_config_save(self) -> None:
        if self._config_save_timer is not None:
            self._config_save_timer.cancel()
            self._config_save_timer = None

    def _spawn_thread(self, target, *args, name: str = "RadioPlayer") -> Optional[threading.Thread]:
        """Avvia un thread demone dedicato (i loop non devono occupare l'executor)."""
        if not self.running:
            return None
        thread = threading.Thread(target=target, args=args, name=name, daemon=True)
        thread.start()
        return thread

    def _invalidate_filtered(self) -> None:
        """Invalida la cache della lista visibile."""
        self._filtered_cache = None
        self._filtered_positions = {}

    def _get_visible_entries(self) -> List[Tuple[int, RadioStation]]:
        """Restituisce (indice_globale, stazione) per la vista corrente."""
        if self._filtered_cache is not None:
            return self._filtered_cache

        query = self.local_search_query.lower() if self.local_search_mode else ""
        entries: List[Tuple[int, RadioStation]] = []
        for i, station in enumerate(self.stations):
            if self.group_filter and station.group != self.group_filter:
                continue
            if self.show_favorites_only and station.url not in self.favorites:
                continue
            if query and query not in station.name.lower():
                continue
            entries.append((i, station))

        self._filtered_cache = entries
        self._filtered_positions = {i: pos for pos, (i, _) in enumerate(entries)}
        return entries

    def _ensure_selection_visible(self) -> None:
        """Se la selezione e' fuori dalla vista filtrata, punta alla prima riga."""
        entries = self._get_visible_entries()
        if not entries:
            return
        if self.state.selected_station_index not in self._filtered_positions:
            self.state.selected_station_index = entries[0][0]
            self.pending_updates |= UpdateFlags.STATIONS

    def load_m3u(self, file_path: Path) -> bool:
        """Carica file M3U"""
        try:
            parser = M3UParser()
            self.stations = parser.parse_file(file_path)

            if not self.stations:
                logger.warning("Nessuna stazione trovata nel file M3U")
                return False

            self.m3u_file_path = file_path.resolve()
            self._last_m3u = self.m3u_file_path
            self._invalidate_filtered()
            self._refresh_groups()
            if self.group_filter and self.group_filter not in self.available_groups:
                self.group_filter = None
            self.state.selected_station_index = max(
                0, min(self.state.selected_station_index, len(self.stations) - 1)
            )
            if self._last_station_url:
                for i, station in enumerate(self.stations):
                    if station.url == self._last_station_url:
                        self.state.selected_station_index = i
                        break
            self._ensure_selection_visible()
            logger.info(f"Caricate {len(self.stations)} stazioni da {file_path}")
            self.pending_updates |= UpdateFlags.FULL
            self._save_user_config()
            return True

        except Exception as e:
            logger.error(f"Errore caricamento M3U: {e}", exc_info=True)
            return False

    def _on_metadata_update(self, key: str, value: str):
        """Callback per aggiornamenti metadata"""
        if not self.state.is_playing:
            return
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
                station_name = self._playing_station_name()
                if station_name and value.lower().startswith(station_name.lower() + " - "):
                    # Alcune radio prefissano il titolo con il proprio nome:
                    # "Virgin Radio - Style Rock" -> "Style Rock".
                    value = value[len(station_name) + 3:].strip()
                    if not value:
                        return

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

                    if self.state.playing_station_index >= 0 or self._preview_station:
                        station_name = self._playing_station_name() or "Anteprima"
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

                    if self.state.playing_station_index >= 0 or self._preview_station:
                        station_name = self._playing_station_name() or "Anteprima"
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
                # Popen: non bloccare il thread dei metadata con notify-send.
                proc = subprocess.Popen(
                    ['notify-send', '\U0001f3b5 Radio Player', message,
                     '--icon=audio-x-generic', '--expire-time=4000'],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                threading.Thread(target=proc.wait, daemon=True).start()
        except Exception:
            logger.debug("Notifica fallita")

    def _current_stream_url(self) -> Optional[str]:
        """URL dello stream attualmente in riproduzione."""
        if self._preview_station is not None:
            return self._preview_station.url
        idx = self.state.playing_station_index
        if 0 <= idx < len(self.stations):
            return self.stations[idx].url
        return None

    def _playing_station_name(self) -> Optional[str]:
        """Nome della stazione in riproduzione (anche in anteprima)."""
        if self._preview_station is not None:
            return self._preview_station.name
        idx = self.state.playing_station_index
        if 0 <= idx < len(self.stations):
            return self.stations[idx].name
        return None

    def _apply_eq(self) -> None:
        """Applica il preset EQ corrente allo stream appena avviato."""
        if self.eq_preset_idx:
            self.mpv_controller.ipc_client.send_command(
                "af", "set", self.eq_presets[self.eq_preset_idx]
            )

    def play_selected(self):
        """Avvia riproduzione della stazione selezionata"""
        if not self.stations:
            return

        entries = self._get_visible_entries()
        if not entries:
            self.show_temp_message("\U0001f4fb Nessuna stazione visibile con i filtri attivi")
            return

        idx = self.state.selected_station_index
        if not 0 <= idx < len(self.stations) or idx not in self._filtered_positions:
            self.show_temp_message("\U0001f4fb Seleziona una stazione visibile")
            return
        station = self.stations[idx]
        logger.info(f"Play stazione: {station.name}")

        self.stop()

        if not self.mpv_controller.start(station.url, self.state.volume):
            self.show_temp_message(f"\u274c Impossibile riprodurre {station.name}")
            logger.error("Impossibile avviare riproduzione")
            return

        self._play_generation += 1
        self._icy_fallback_started = False
        self.metadata_monitor.received_title = False
        self._play_started_at = time.time()

        self.state.is_playing = True
        self.state.is_paused = False
        self.state.playing_station_index = idx
        self.state.stream_info = StreamInfo(
            start_time=time.time(),
            song_start_time=time.time(),
        )

        self.mpv_controller.set_mute(self.state.is_muted)
        self._apply_eq()

        # I metadata vengono letti da mpv; il monitor ICY parte solo come
        # fallback se mpv non espone alcun titolo (evita un secondo stream).
        self._spawn_thread(
            self._stats_monitor_loop, self._play_generation, name="StatsMonitor"
        )

        self.pending_updates |= UpdateFlags.STATUS | UpdateFlags.SONG | UpdateFlags.STATIONS
        logger.info("Riproduzione avviata")
        self.tray.update()

    def stop(self):
        """Ferma riproduzione. MPV e' SEMPRE ucciso (anche se lo stato e' desync)."""
        self._play_generation += 1
        self._icy_fallback_started = False
        self.metadata_monitor.received_title = False
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

    def stop_playback(self):
        """Comando esplicito di stop con feedback in UI."""
        if not self.state.is_playing:
            self.show_temp_message("\u23f9 Nessuna riproduzione attiva")
            return
        self.stop()
        self.show_temp_message("\u23f9 Riproduzione fermata")

    def next_station(self, delta: int):
        """Cambia stazione e, se stava suonando, avvia subito la nuova."""
        if not self.stations:
            return
        was_playing = self.state.is_playing
        self.change_selection(delta)
        if was_playing:
            self.play_selected()

    def toggle_play_pause(self):
        """Toggle play/pause"""
        if not self.stations:
            return

        if not self.state.is_playing:
            self.play_selected()
        elif self.state.playing_station_index != self.state.selected_station_index:
            self.play_selected()
        elif self.state.is_paused:
            if not self.mpv_controller.set_pause(False):
                self.show_temp_message("\u274c Impossibile riprendere lo stream")
                return
            self.state.is_paused = False
            extra_pause = (
                time.time() - self.state.stream_info.pause_start_time
                if self.state.stream_info.pause_start_time else 0
            )
            self.state.stream_info = self.state.stream_info.replace(
                total_pause_time=self.state.stream_info.total_pause_time + extra_pause,
                pause_start_time=None,
            )
            self.pending_updates |= UpdateFlags.STATUS | UpdateFlags.SONG
            logger.info("Riproduzione ripresa")
            self.tray.update()
        else:
            if not self.mpv_controller.set_pause(True):
                self.show_temp_message("\u274c Impossibile mettere in pausa")
                return
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
        self._schedule_config_save()

    def toggle_mute(self):
        """Toggle muto"""
        self.state.is_muted = not self.state.is_muted

        if self.state.is_playing:
            self.mpv_controller.set_mute(self.state.is_muted)

        self.pending_updates |= UpdateFlags.TIMER
        logger.debug(f"Muto: {self.state.is_muted}")
        self.tray.update()

    def change_selection(self, delta: int):
        """Cambia stazione selezionata muovendosi nella lista visibile."""
        if not self.stations:
            return
        entries = self._get_visible_entries()
        if not entries:
            return

        current = self.state.selected_station_index
        pos = self._filtered_positions.get(current)
        if pos is None:
            new_idx = entries[0][0] if delta >= 0 else entries[-1][0]
        else:
            new_idx = entries[(pos + delta) % len(entries)][0]

        self.state.selected_station_index = new_idx
        self.pending_updates |= UpdateFlags.STATIONS

    def select_by_number(self, number: int):
        """Seleziona stazione per numero globale."""
        if not 1 <= number <= len(self.stations):
            return
        self.state.selected_station_index = number - 1
        if self.state.selected_station_index not in self._get_visible_positions():
            # Il numero e' valido ma nascosto dai filtri: mostralo.
            self.group_filter = None
            self.show_favorites_only = False
            if self.local_search_mode:
                self.local_search_mode = False
                self.local_search_query = ""
            self._invalidate_filtered()
            self.show_temp_message("\U0001f4cb Filtri rimossi per mostrare la stazione")
        self.pending_updates |= UpdateFlags.STATIONS | UpdateFlags.FULL
        logger.debug(f"Selezionata stazione #{number}")

    def _get_visible_positions(self) -> dict:
        self._get_visible_entries()
        return self._filtered_positions

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

        stream_url = self._current_stream_url()
        if not stream_url:
            self.show_temp_message("\u274c Nessuno stream da registrare")
            return

        if self._preview_station is not None:
            display_name = self._preview_station.name
        elif 0 <= self.state.playing_station_index < len(self.stations):
            display_name = self.stations[self.state.playing_station_index].name
        else:
            display_name = "stream"

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        station_name = re.sub(r'[^\w\s-]', '', display_name)[:30].strip() or "stream"

        codec = (self.state.stream_info.codec or "").lower()
        if ".m3u8" in stream_url.lower():
            extension = ".ts"
        else:
            extension = {
                "mp3": ".mp3",
                "aac": ".aac",
                "opus": ".opus",
                "vorbis": ".ogg",
            }.get(codec, ".mka")
        self.recording_file = Path(f"recording_{station_name}_{timestamp}{extension}")

        # ffmpeg scrive su disco in streaming ed e' la scelta piu' affidabile.
        # Se manca o fallisce subito, si usa stream-record di mpv.
        try:
            cmd = [
                'ffmpeg',
                '-i', stream_url,
                '-c', 'copy',
                '-y',
                str(self.recording_file),
            ]

            self.recording_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            # ffmpeg puo' uscire subito (URL/TLS non validi): in quel caso
            # proviamo la registrazione tramite la connessione mpv gia' aperta.
            time.sleep(0.3)
            if self.recording_process.poll() is not None:
                logger.warning("ffmpeg terminato subito, provo stream-record di mpv")
                self.recording_process = None
                if self._start_mpv_recording():
                    return
                self.show_temp_message("\u274c Registrazione non avviata (ffmpeg/mpv)")
                return

            self._recording_via_mpv = False
            self.is_recording = True
            self.pending_updates |= UpdateFlags.STATUS
            self.show_temp_message(f"\U0001f534 Registrazione avviata: {self.recording_file.name}")
            logger.info(f"Registrazione avviata via ffmpeg: {self.recording_file}")

        except FileNotFoundError:
            if not self._start_mpv_recording():
                self.show_temp_message("\u274c ffmpeg non installato (apt install ffmpeg)")
                logger.error("ffmpeg non disponibile per registrazione")
        except Exception as e:
            self.show_temp_message(f"\u274c Errore registrazione: {e}")
            logger.error(f"Errore avvio registrazione: {e}")

    def _start_mpv_recording(self) -> bool:
        """Avvia la registrazione usando la connessione mpv gia' attiva."""
        if self.recording_file is None or not self.mpv_controller.is_running():
            return False
        if not self.mpv_controller.ipc_client.set_property(
            "stream-record", str(self.recording_file)
        ):
            return False

        self._recording_via_mpv = True
        self.is_recording = True
        self.pending_updates |= UpdateFlags.STATUS
        self.show_temp_message(
            f"\U0001f534 Registrazione avviata: {self.recording_file.name}"
        )
        logger.info(f"Registrazione avviata via mpv: {self.recording_file}")
        return True

    def stop_recording(self):
        """Ferma registrazione"""
        if not self.is_recording:
            return

        try:
            if self._recording_via_mpv:
                self.mpv_controller.ipc_client.set_property("stream-record", "")
                self._recording_via_mpv = False
                time.sleep(0.5)
            elif self.recording_process:
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
        """Restituisce le stazioni filtrate per gruppo/preferiti/ricerca."""
        return [station for _, station in self._get_visible_entries()]

    def _refresh_groups(self):
        """Aggiorna la lista dei gruppi disponibili."""
        self.available_groups = sorted({s.group for s in self.stations})

    def _group_choices(self):
        return [None] + self.available_groups

    def open_group_picker(self):
        """Apre il selettore dei gruppi (invece del ciclo alla cieca)."""
        self._refresh_groups()
        if not self.available_groups:
            self.show_temp_message("\U0001f4cb Nessun gruppo trovato")
            return
        choices = self._group_choices()
        try:
            self.group_overlay_idx = choices.index(self.group_filter)
        except ValueError:
            self.group_overlay_idx = 0
        self.show_group_overlay = True
        self.pending_updates |= UpdateFlags.FULL

    def close_group_picker(self):
        self.show_group_overlay = False
        self.pending_updates |= UpdateFlags.FULL

    def move_group_selection(self, delta: int):
        choices = self._group_choices()
        if not choices:
            return
        self.group_overlay_idx = (self.group_overlay_idx + delta) % len(choices)

    def _apply_group_filter(self, group: Optional[str]):
        self.group_filter = group
        self.show_group_overlay = False
        self._invalidate_filtered()
        self._ensure_selection_visible()
        label = group or "Tutti i gruppi"
        self.show_temp_message(f"\U0001f4cb Gruppo: {label}")
        self.pending_updates |= UpdateFlags.FULL
        self._save_user_config()

    def confirm_group_selection(self):
        choices = self._group_choices()
        if choices:
            self._apply_group_filter(choices[self.group_overlay_idx % len(choices)])

    def cycle_group_filter(self):
        """Cicla rapidamente il filtro per gruppo."""
        self._refresh_groups()
        choices = self._group_choices()
        if len(choices) == 1:
            self.show_temp_message("\U0001f4cb Nessun gruppo trovato")
            return
        try:
            idx = choices.index(self.group_filter)
        except ValueError:
            idx = 0
        self._apply_group_filter(choices[(idx + 1) % len(choices)])

    def toggle_favorites_only(self):
        """Mostra/nasconde solo le stazioni preferite."""
        self.show_favorites_only = not self.show_favorites_only
        self._invalidate_filtered()
        self._ensure_selection_visible()
        status = "ON" if self.show_favorites_only else "OFF"
        if self.show_favorites_only and not self._get_visible_entries():
            self.show_temp_message("\u2b50 Nessun preferito: usa * per aggiungerne")
        else:
            self.show_temp_message(f"\u2b50 Solo preferiti: {status}")
        self.pending_updates |= UpdateFlags.FULL
        self._save_user_config()

    def toggle_favorite(self):
        """Aggiunge/rimuove stazione selezionata dai preferiti."""
        if not self.stations:
            return
        if not 0 <= self.state.selected_station_index < len(self.stations):
            return
        station = self.stations[self.state.selected_station_index]
        if station.url in self.favorites:
            self.favorites.discard(station.url)
            self.show_temp_message(f"\u2b50 Rimossa: {station.name}")
        else:
            self.favorites.add(station.url)
            self.show_temp_message(f"\u2b50 Preferita: {station.name}")
        self._invalidate_filtered()
        self._ensure_selection_visible()
        self.pending_updates |= UpdateFlags.STATIONS
        self._save_user_config()

    def enter_local_search_mode(self):
        """Entra in modalita' ricerca locale nel M3U."""
        self.local_search_mode = True
        self.local_search_query = ""
        self._invalidate_filtered()
        self.pending_updates |= UpdateFlags.FULL

    def exit_local_search_mode(self):
        """Esce dalla modalita' ricerca locale."""
        self.local_search_mode = False
        self.local_search_query = ""
        self._invalidate_filtered()
        self._ensure_selection_visible()
        self.pending_updates |= UpdateFlags.FULL

    def _update_local_search(self):
        """Aggiorna filtro e selezione in base alla ricerca locale."""
        self._invalidate_filtered()
        entries = self._get_visible_entries()
        if entries:
            self.state.selected_station_index = entries[0][0]
        self.pending_updates |= UpdateFlags.STATIONS | UpdateFlags.INPUT

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
        """Salta alla prossima stazione visibile che inizia con la lettera."""
        if not self.stations:
            return
        entries = self._get_visible_entries()
        if not entries:
            return
        letter = letter.lower()
        pos = self._filtered_positions.get(self.state.selected_station_index, 0)
        for offset in range(1, len(entries) + 1):
            idx, station = entries[(pos + offset) % len(entries)]
            if station.name.lower().startswith(letter):
                self.state.selected_station_index = idx
                self.pending_updates |= UpdateFlags.STATIONS
                self.show_temp_message(f"\U0001f50d {letter.upper()}: {station.name}")
                return
        self.show_temp_message(f"\U0001f50d Nessuna stazione con {letter.upper()}")

    def cancel_pending_delete(self):
        if self._pending_delete is not None:
            self._pending_delete = None
            self.show_temp_message("Eliminazione annullata")

    def remove_selected_station(self):
        """Rimuove la stazione selezionata, con doppia conferma."""
        if not self.stations or not self.m3u_file_path:
            self.show_temp_message("\u274c Nessuna stazione da rimuovere")
            return
        idx = self.state.selected_station_index
        if idx < 0 or idx >= len(self.stations):
            return

        now = time.time()
        pending = self._pending_delete
        if pending and pending[0] == idx and now - pending[1] <= 3.0:
            self._pending_delete = None
            self._delete_station(idx)
            return

        self._pending_delete = (idx, now)
        self.show_temp_message(
            f"\u26a0\ufe0f  Premi 'd' di nuovo per eliminare '{self.stations[idx].name}'"
        )

    def _delete_station(self, idx: int):
        station = self.stations[idx]
        name = station.name

        if self.state.playing_station_index == idx:
            self.stop()
        elif self.state.playing_station_index > idx:
            self.state.playing_station_index -= 1

        self.favorites.discard(station.url)
        self.stations.pop(idx)
        self._last_deleted = (station, idx, time.time())
        self._invalidate_filtered()
        self.state.selected_station_index = min(
            self.state.selected_station_index, max(0, len(self.stations) - 1)
        )
        self._ensure_selection_visible()

        if self._save_m3u_file():
            self.show_temp_message(
                f"\U0001f5d1\ufe0f Rimossa: {name}  (u per annullare)"
            )
        self.pending_updates |= UpdateFlags.STATIONS | UpdateFlags.STATUS
        self._save_user_config()

    def undo_delete(self):
        """Ripristina l'ultima stazione eliminata (entro 15 secondi)."""
        if self._last_deleted is None:
            self.show_temp_message("\u21a9\ufe0f Nessuna eliminazione da annullare")
            return
        station, idx, deleted_at = self._last_deleted
        if time.time() - deleted_at > 15:
            self._last_deleted = None
            self.show_temp_message("\u231b Tempo per annullare scaduto")
            return
        if any(s.url == station.url for s in self.stations):
            self._last_deleted = None
            self.show_temp_message("\u26a0\ufe0f La stazione e' gia' presente")
            return

        idx = max(0, min(idx, len(self.stations)))
        self.stations.insert(idx, station)
        self.state.selected_station_index = idx
        self._invalidate_filtered()
        self._refresh_groups()
        self._last_deleted = None
        if self._save_m3u_file():
            self.show_temp_message(f"\u21a9\ufe0f Ripristinata: {station.name}")
        self.pending_updates |= UpdateFlags.FULL | UpdateFlags.STATUS
        self._save_user_config()

    def _save_m3u_file(self) -> bool:
        """Riscrive il file M3U preservando tutti gli attributi delle stazioni."""
        if not self.m3u_file_path:
            return False
        tmp_path = self.m3u_file_path.with_name(self.m3u_file_path.name + ".tmp")
        try:
            tmp_path.write_text(M3UParser.serialize(self.stations), encoding="utf-8")
            os.replace(tmp_path, self.m3u_file_path)
            return True
        except OSError as e:
            logger.error(f"Errore salvataggio M3U: {e}")
            self.show_temp_message(f"\u274c Errore salvataggio M3U: {e}")
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
            return False

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
        self.search_error = ""
        self.search_offset = 0
        self.search_has_more = False
        self.search_loading_more = False
        self._last_searched_query = ""
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

        self.search_error = ""
        if not self.search_query.strip():
            self.search_results = []
            self.search_selected_idx = 0
            self.search_loading = False
            self.search_offset = 0
            self.search_has_more = False
            self.search_loading_more = False
            self.pending_updates |= UpdateFlags.STATIONS
            return

        self.search_offset = 0
        self.search_has_more = False
        self.search_loading_more = False
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
            results = self.radio_browser.search(query, limit=20, offset=0)
            if query == self.search_query and self.search_mode:
                self.search_results = results
                self.search_selected_idx = 0
                self.search_loading = False
                self.search_error = "" if results else (self.radio_browser.last_error or "")
                self.search_offset = 20 if len(results) >= 20 else len(results)
                self.search_has_more = len(results) >= 20
                self._last_searched_query = query
                self.pending_updates |= UpdateFlags.STATIONS
        except Exception as e:
            logger.error(f"Errore ricerca: {e}")
            self.search_loading = False
            self.search_error = str(e)
            self.search_has_more = False
            self._last_searched_query = query
            self.pending_updates |= UpdateFlags.STATIONS

    def load_more_search(self):
        """Carica la pagina successiva dei risultati RadioBrowser."""
        if (
            self.search_loading
            or self.search_loading_more
            or not self.search_has_more
            or not self.search_query.strip()
        ):
            return
        self.search_loading_more = True
        self.pending_updates |= UpdateFlags.STATIONS
        self._spawn_thread(self._do_search_more, name="SearchMore")

    def _do_search_more(self):
        """Carica altri 20 risultati e li accoda a quelli esistenti."""
        query = self.search_query
        offset = self.search_offset
        try:
            results = self.radio_browser.search(query, limit=20, offset=offset)
        except Exception as e:
            logger.error(f"Errore ricerca (altri risultati): {e}")
            self.search_loading_more = False
            self.search_error = str(e)
            self.pending_updates |= UpdateFlags.STATIONS
            return

        if query != self.search_query or not self.search_mode:
            self.search_loading_more = False
            return

        existing = {s.url.rstrip("/") for s in self.search_results}
        added = 0
        for station in results:
            key = station.url.rstrip("/")
            if key not in existing:
                self.search_results.append(station)
                existing.add(key)
                added += 1

        self.search_offset += len(results)
        self.search_has_more = len(results) >= 20
        self.search_loading_more = False
        if self.radio_browser.last_error and not results:
            self.search_error = self.radio_browser.last_error
        elif added == 0 and results:
            self.show_temp_message("\u2139\ufe0f Nessun nuovo risultato")
        self.pending_updates |= UpdateFlags.STATIONS

    def play_preview(self, station: RadioStation):
        """Ascolta anteprima senza aggiungere al M3U. Toggle: p ferma se gia' attiva."""
        if self._preview_station and self._preview_station.url == station.url and self.state.is_playing:
            self.stop()
            self.show_temp_message("\u23f9 Anteprima fermata")
            return
        self.stop()

        if not self.mpv_controller.start(station.url, self.state.volume):
            self.show_temp_message("\u274c Impossibile avviare anteprima")
            return

        self._play_generation += 1
        self._icy_fallback_started = False
        self.metadata_monitor.received_title = False
        self._play_started_at = time.time()
        self.state.is_playing = True
        self.state.is_paused = False
        self.state.playing_station_index = -1
        self._preview_station = station
        self.state.stream_info = StreamInfo(
            start_time=time.time(),
            song_start_time=time.time(),
        )

        self.mpv_controller.set_mute(self.state.is_muted)
        self._apply_eq()
        self._spawn_thread(
            self._stats_monitor_loop, self._play_generation, name="StatsMonitor"
        )
        self.pending_updates |= UpdateFlags.STATUS | UpdateFlags.SONG
        self.show_temp_message(f"\U0001f442 Anteprima: {station.name}")
        logger.info(f"Preview: {station.name}")

    def add_station_to_m3u(self, station: RadioStation) -> bool:
        """Aggiunge la stazione al file M3U evitando duplicati (URL e nome)"""
        if not self.m3u_file_path:
            self.show_temp_message("\u274c Nessun file M3U caricato")
            return False

        station_url = station.url.rstrip("/")
        existing_urls = {s.url.rstrip("/") for s in self.stations}
        if station_url in existing_urls:
            existing = next(s for s in self.stations if s.url.rstrip("/") == station_url)
            self.show_temp_message(f"\u26a0\ufe0f  Gia' presente: {existing.name}")
            return False

        station_name_lc = station.name.strip().lower()
        existing_names = {s.name.strip().lower(): s for s in self.stations}
        if station_name_lc in existing_names:
            existing = existing_names[station_name_lc]
            self.show_temp_message(f"\u26a0\ufe0f  Nome gia' presente: {existing.name}")
            return False

        try:
            try:
                content = self.m3u_file_path.read_text(encoding="utf-8-sig")
            except UnicodeDecodeError:
                content = self.m3u_file_path.read_text(encoding="latin-1")

            with open(self.m3u_file_path, "a", encoding="utf-8") as f:
                if content and not content.endswith("\n"):
                    f.write("\n")
                f.write(M3UParser.format_extinf(station) + "\n")
                f.write(station.url + "\n")

            self.stations.append(station)
            self._invalidate_filtered()
            self._refresh_groups()
            self.pending_updates |= UpdateFlags.STATIONS
            self.show_temp_message(f"\u2705 Aggiunta: {station.name}")
            logger.info(f"Aggiunta al M3U: {station.name} \u2014 {station.url}")
            return True

        except Exception as e:
            self.show_temp_message(f"\u274c Errore salvataggio: {e}")
            logger.error(f"Errore aggiunta stazione: {e}")
            return False

    def _stats_monitor_loop(self, generation: int):
        """Loop monitoraggio statistiche MPV e metadata."""
        logger.info("Avviato monitor statistiche")
        errors = 0

        while (
            self.state.is_playing
            and generation == self._play_generation
            and self.mpv_controller.is_running()
        ):
            try:
                stats = self.mpv_controller.get_audio_stats()

                if (
                    self.is_recording
                    and not self._recording_via_mpv
                    and self.recording_process is not None
                    and self.recording_process.poll() is not None
                ):
                    self.is_recording = False
                    self.recording_process = None
                    self.show_temp_message("\u274c Registrazione interrotta (ffmpeg)")

                updates = {}
                if stats.get('bitrate'):
                    updates['audio_bitrate'] = stats['bitrate']
                if stats.get('codec'):
                    updates['codec'] = stats['codec']
                if stats.get('cache'):
                    updates['cache_duration'] = stats['cache']
                if stats.get('buffer_status'):
                    updates['buffer_status'] = stats['buffer_status']

                changed = {
                    key: value for key, value in updates.items()
                    if getattr(self.state.stream_info, key, None) != value
                }
                if changed:
                    self.state.stream_info = self.state.stream_info.replace(**changed)
                    if any(key != "cache_duration" for key in changed):
                        self.pending_updates |= UpdateFlags.TECHNICAL

                # Metadata da mpv (niente seconda connessione allo stream).
                # Il monitor ICY parte solo se dopo 10s non abbiamo un titolo.
                if not self.metadata_monitor.received_title:
                    metadata = self.mpv_controller.ipc_client.get_property("metadata")
                    current_title = None
                    if metadata and isinstance(metadata, dict):
                        current_title = metadata.get("icy-title")
                        if not current_title:
                            media_title = metadata.get("title") or metadata.get("TITLE")
                            if media_title and " - " in str(media_title):
                                current_title = media_title

                    if current_title:
                        current_title = str(current_title).strip()
                        if current_title and current_title != self.state.stream_info.title:
                            self._on_metadata_update('stream_title', current_title)
                    elif (
                        not self._icy_fallback_started
                        and time.time() - self._play_started_at >= 10
                    ):
                        url = self._current_stream_url()
                        if url:
                            self._icy_fallback_started = True
                            self.metadata_monitor.start(url)
                            self._spawn_thread(
                                self.metadata_monitor.monitor_loop, name="Metadata"
                            )
                            logger.info("Avviato fallback metadata ICY")

                time.sleep(2)
                errors = 0

            except Exception as e:
                errors += 1
                logger.error(f"Errore monitor stats ({errors}/3): {e}")
                if errors >= 3:
                    break
                time.sleep(2)

        # mpv e' terminato senza che l'utente abbia premuto stop.
        if (
            generation == self._play_generation
            and self.state.is_playing
            and not self.mpv_controller.is_running()
        ):
            logger.warning("Stream terminato inaspettatamente")
            self.stop()
            self.show_temp_message("\u274c Stream interrotto")

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

    def setup_terminal(self) -> bool:
        """Configura il terminale per l'input raw. False se non e' un TTY."""
        if platform.system() == "Windows":
            return True
        if not sys.stdin.isatty():
            return False
        try:
            self.old_settings = termios.tcgetattr(sys.stdin)
            tty.setcbreak(sys.stdin.fileno())
            return True
        except (termios.error, OSError, ValueError):
            self.old_settings = None
            return False

    def restore_terminal(self):
        """Ripristina terminale"""
        if platform.system() != "Windows" and self.old_settings:
            try:
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self.old_settings)
            except (termios.error, OSError, ValueError):
                pass
            self.old_settings = None

    def _read_unix_char(self, fd) -> Optional[str]:
        """Legge un carattere UTF-8 o una sequenza di escape da stdin."""
        try:
            first = os.read(fd, 1)
        except OSError:
            return None
        if not first:
            return None

        if first == b'\x1b':
            seq = b""
            deadline = time.monotonic() + 0.03
            mapping = {
                b'[A': 'UP', b'[B': 'DOWN', b'[C': 'RIGHT', b'[D': 'LEFT',
                b'OA': 'UP', b'OB': 'DOWN', b'OC': 'RIGHT', b'OD': 'LEFT',
                b'[5~': 'PGUP', b'[6~': 'PGDN',
                b'[H': 'HOME', b'[F': 'END', b'[1~': 'HOME', b'[4~': 'END',
                b'OH': 'HOME', b'OF': 'END',
            }
            while len(seq) < 6 and time.monotonic() < deadline:
                if seq in mapping:
                    break
                if not select.select([fd], [], [], 0.005)[0]:
                    break
                try:
                    seq += os.read(fd, 1)
                except OSError:
                    break
            return mapping.get(seq, 'ESC')

        data = first
        if first[0] >= 0xC0:
            extra = 1 if first[0] < 0xE0 else (2 if first[0] < 0xF0 else 3)
            for _ in range(extra):
                try:
                    data += os.read(fd, 1)
                except OSError:
                    break
        return data.decode('utf-8', errors='ignore')

    def get_char(self) -> Optional[str]:
        """Legge carattere da stdin (non bloccante)"""
        if platform.system() == "Windows":
            if msvcrt.kbhit():
                char = msvcrt.getwch()
                if char in ('\x00', '\xe0'):
                    code = msvcrt.getwch()
                    return {
                        'H': 'UP', 'P': 'DOWN', 'M': 'RIGHT', 'K': 'LEFT',
                        'I': 'PGUP', 'Q': 'PGDN', 'G': 'HOME', 'O': 'END',
                    }.get(code)
                if char == '\x1b':
                    return 'ESC'
                return char
            return None
        else:
            fd = sys.stdin.fileno()
            if not select.select([fd], [], [], 0.05)[0]:
                return None
            return self._read_unix_char(fd)

    def handle_input(self):
        """Loop gestione input"""
        while self.running:
            char = self.get_char()

            if not char:
                continue

            try:
                if char == '\x03':  # Ctrl+C su Windows
                    self.running = False
                    continue

                if self._pending_delete is not None and char.lower() != 'd':
                    if char == 'ESC':
                        self.cancel_pending_delete()
                        continue
                    self._pending_delete = None

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
                    elif char == 'PGUP' and self.search_results:
                        self.search_selected_idx = max(0, self.search_selected_idx - 10)
                        self.pending_updates |= UpdateFlags.STATIONS
                    elif char == 'PGDN' and self.search_results:
                        self.search_selected_idx = min(
                            len(self.search_results) - 1, self.search_selected_idx + 10
                        )
                        self.pending_updates |= UpdateFlags.STATIONS
                    elif char == '\t':
                        self.load_more_search()
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

                if self.show_group_overlay:
                    if char in ('ESC', 'g', 'G'):
                        self.close_group_picker()
                    elif char == 'UP':
                        self.move_group_selection(-1)
                    elif char == 'DOWN':
                        self.move_group_selection(1)
                    elif char in ('\r', '\n'):
                        self.confirm_group_selection()
                    continue

                if self.show_help_overlay:
                    if char in ('ESC', '?'):
                        self.show_help_overlay = False
                        self.pending_updates |= UpdateFlags.FULL
                    continue

                if self.show_history_overlay:
                    if char in ('ESC', 'h', 'H'):
                        self.show_history_overlay = False
                        self.pending_updates |= UpdateFlags.FULL
                    continue

                if char.lower() == 'q':
                    logger.info("Richiesta uscita utente")
                    self.running = False
                elif char.lower() == 'p' or char == ' ' or char in ('\r', '\n'):
                    self.toggle_play_pause()
                elif char.lower() == 'x':
                    self.stop_playback()
                elif char.lower() == 'n':
                    self.next_station(-1 if char == 'N' else 1)
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
                elif char == 'PGUP':
                    self.change_selection(-5)
                elif char == 'PGDN':
                    self.change_selection(5)
                elif char == 'HOME':
                    entries = self._get_visible_entries()
                    if entries:
                        self.state.selected_station_index = entries[0][0]
                        self.pending_updates |= UpdateFlags.STATIONS
                elif char == 'END':
                    entries = self._get_visible_entries()
                    if entries:
                        self.state.selected_station_index = entries[-1][0]
                        self.pending_updates |= UpdateFlags.STATIONS
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
                elif char == 'G':
                    self.cycle_group_filter()
                elif char.lower() == 'g':
                    self.open_group_picker()
                elif char == '*':
                    self.toggle_favorite()
                elif char.lower() == 'f':
                    self.toggle_favorites_only()
                elif char == 'ESC':
                    if self.group_filter or self.show_favorites_only:
                        self.group_filter = None
                        self.show_favorites_only = False
                        self._invalidate_filtered()
                        self._ensure_selection_visible()
                        self.show_temp_message("\U0001f4cb Filtri rimossi")
                        self.pending_updates |= UpdateFlags.FULL
                elif char.lower() == 'd':
                    self.remove_selected_station()
                elif char.lower() == 'u':
                    self.undo_delete()
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

    def run(self, m3u_file: Optional[Path] = None) -> bool:
        """Loop principale. Restituisce False se non riesce ad avviarsi."""
        success = False
        fatal_error: Optional[str] = None
        try:
            self._install_signal_handlers()
            if not self.setup_terminal():
                print("\u274c Radio Player richiede un terminale interattivo (TTY)")
                return False

            if m3u_file:
                if not self.load_m3u(m3u_file):
                    print(f"\u274c Impossibile caricare {m3u_file}")
                    return False
            else:
                candidates: List[Path] = discover_m3u_files(Path.cwd())
                if candidates:
                    if not self.load_m3u(candidates[0]):
                        print("\u274c Errore caricamento M3U")
                        return False
                else:
                    print("\u274c Nessun file M3U trovato")
                    print(f"Uso: python3 {Path(sys.argv[0]).name} [file.m3u]")
                    return False

            if self.use_tray:
                self.tray.start()

            if self.use_rich:
                set_console_logging(False)

            self._spawn_thread(self.handle_input, name="Input")

            if self.use_rich:
                self._run_rich_loop()
            else:
                self._run_tui_loop()
            success = True

        except KeyboardInterrupt:
            logger.info("Interrotto da utente (Ctrl+C)")
            success = True
        except Exception as e:
            logger.error(f"Errore critico: {e}", exc_info=True)
            fatal_error = str(e)
        finally:
            self.running = False
            self._cancel_config_save()
            self.stop()
            self.metadata_monitor.stop()
            if self.use_tray:
                self.tray.stop()
            try:
                self._save_user_config()
                self.history.export(self.history_file)
            except Exception:
                logger.debug("Salvataggio stato finale fallito", exc_info=True)
            self.restore_terminal()

            if self.use_rich:
                self.console.clear()
                set_console_logging(True)
            else:
                os.system('clear' if os.name == 'posix' else 'cls')

            if fatal_error:
                print(f"\u274c Errore: {fatal_error}")
            print("\U0001f44b Arrivederci!")
            logger.info("Applicazione terminata")

        return success

    def _run_rich_loop(self):
        """Loop principale con Rich UI, aggiornato solo quando serve."""
        logger.info("Avvio loop Rich UI")

        with Live(
            self._render_rich(),
            console=self.console,
            screen=True,
            auto_refresh=False,
            vertical_overflow="crop",
        ) as live:
            self.live = live

            last_timer_update = 0.0
            last_animation_update = 0.0

            while self.running:
                current_time = time.time()
                flags = self.pending_updates

                if current_time - last_timer_update >= 1.0:
                    flags |= UpdateFlags.TIMER
                    if self.state.is_playing and not self.state.is_paused:
                        flags |= UpdateFlags.SONG
                    last_timer_update = current_time

                # Equalizer a ~2.5 fps, non a 8 fps come prima.
                if (
                    self.state.is_playing
                    and not self.state.is_paused
                    and current_time - last_animation_update >= 0.4
                ):
                    flags |= UpdateFlags.SONG
                    last_animation_update = current_time

                if self.temp_message:
                    if current_time - self.temp_message_time < 2.0:
                        flags |= UpdateFlags.STATUS
                    else:
                        self.temp_message = ""
                        flags |= UpdateFlags.STATUS

                if flags != UpdateFlags.NONE:
                    live.update(self._render_rich(), refresh=True)
                    self.pending_updates = UpdateFlags(
                        self.pending_updates.value & ~flags.value
                    )

                time.sleep(0.1)

            self.live = None

    def _run_tui_loop(self):
        """Loop principale con TUI base (fallback senza Rich)."""
        logger.info("Avvio loop TUI base")

        os.system('clear' if os.name == 'posix' else 'cls')
        print("=" * 70)
        print("\U0001f3b5 RADIO PLAYER M3U")
        print("=" * 70)
        print("\nModalita' TUI base (installa 'rich' per UI migliorata)")
        print("\nComandi: p=play  x=stop  n/N=stazione  +/-=volume  m=muto")
        print("          /=cerca  g=gruppi  f=preferiti  ?=aiuto  q=esci\n")

        try:
            width = os.get_terminal_size().columns
        except OSError:
            width = 80

        while self.running:
            current_time = time.time()

            if current_time - self.last_render_time >= 1.0:
                status = "\u25b6\ufe0f Playing" if self.state.is_playing else "\u23f9\ufe0f Stopped"
                if self.state.is_paused:
                    status = "\u23f8\ufe0f Paused"

                if self.state.playing_station_index >= 0:
                    station = self.stations[self.state.playing_station_index]
                    name = station.name
                elif self._preview_station is not None:
                    name = f"{self._preview_station.name} (anteprima)"
                else:
                    name = "Nessuna stazione"

                song = self.state.stream_info.song
                line = (
                    f"{status} | {name[:40]:<40} | Vol: {self.state.volume:3d}%"
                    + (f" | {song[:35]}" if song else "")
                )
                print(f"\r{line[:max(20, width - 1)].ljust(max(20, width - 1))}", end="", flush=True)
                self.last_render_time = current_time

            time.sleep(0.1)
