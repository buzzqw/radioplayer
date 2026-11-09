"""System tray icon con menu contestuale."""

import logging
import platform
import threading
import time
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from .player import RadioPlayer

logger = logging.getLogger("RadioPlayer")

TRAY_AVAILABLE = False
TRAY_IMPORT_ERROR = ""
TRAY_BACKEND = ""

try:
    import pystray
    from pystray import Icon as TrayIcon, MenuItem as TrayItem, Menu as TrayMenu
    from PIL import Image as PILImage, ImageDraw as PILDraw
    TRAY_AVAILABLE = True
    TRAY_BACKEND = TrayIcon.__module__.rsplit(".", 1)[-1]
except Exception as exc:  # ImportError, oppure backend grafico non disponibile
    TRAY_IMPORT_ERROR = str(exc)


def tray_unavailable_message() -> str:
    """Messaggio esplicativo quando l'icona tray non può essere creata."""
    if TRAY_AVAILABLE:
        return ""
    detail = f" ({TRAY_IMPORT_ERROR})" if TRAY_IMPORT_ERROR else ""
    if platform.system() == "Linux":
        return (
            "System tray non disponibile: installa pystray e Pillow"
            " (Arch: sudo pacman -S python-pystray python-pillow;"
            " Debian/Ubuntu: sudo apt install python3-pystray python3-pil)"
            f"{detail}"
        )
    return (
        "System tray non disponibile: installa pystray e Pillow"
        f" con 'pip install pystray Pillow'{detail}"
    )


class SystemTrayIcon:
    """Icona nel system tray con menu contestuale per controllare il player"""

    ICON_SIZE = 64

    def __init__(self, player: 'RadioPlayer'):
        self.player = player
        self._icon: Optional[Any] = None
        self._thread: Optional[threading.Thread] = None
        self._update_lock = threading.Lock()
        self._last_update = 0.0
        self._update_timer: Optional[threading.Timer] = None
        self._start_error = ""

    def error_message(self) -> str:
        """Motivo per cui l'icona tray non è disponibile (vuoto se attiva)."""
        return self._start_error or tray_unavailable_message()

    def _make_icon_image(self, playing: bool = True, muted: bool = False) -> Any:
        """Crea un'immagine PIL per l'icona tray (nota musicale colorata)"""
        size = self.ICON_SIZE
        img = PILImage.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = PILDraw.Draw(img)

        if muted:
            bg_color = (180, 50, 50, 220)
        elif playing:
            bg_color = (30, 160, 90, 220)
        else:
            bg_color = (80, 80, 80, 220)

        draw.ellipse([2, 2, size - 2, size - 2], fill=bg_color)

        note_color = (255, 255, 255, 255)
        draw.ellipse([14, 38, 30, 50], fill=note_color)
        draw.rectangle([28, 14, 32, 44], fill=note_color)
        draw.rectangle([28, 14, 48, 20], fill=note_color)
        draw.rectangle([28, 24, 44, 30], fill=note_color)

        if muted:
            draw.line([8, 8, size - 8, size - 8], fill=(255, 60, 60, 255), width=5)

        return img

    def _action_play_pause(self, icon=None, item=None):
        self.player.toggle_play_pause()
        self._refresh_menu()

    def _action_stop(self, icon=None, item=None):
        self.player.stop()
        self._refresh_menu()

    def _action_mute(self, icon=None, item=None):
        self.player.toggle_mute()
        self._refresh_menu()

    def _action_vol_up5(self, icon=None, item=None):
        self.player.change_volume(5)
        self._refresh_menu()

    def _action_vol_down5(self, icon=None, item=None):
        self.player.change_volume(-5)
        self._refresh_menu()

    def _action_set_volume(self, value: int):
        """Imposta il volume a un valore assoluto (usato dal sottomenu)."""
        return lambda icon=None, item=None: self._set_volume(value)

    def _set_volume(self, value: int):
        value = max(0, min(100, int(value)))
        self.player.change_volume(value - self.player.state.volume)
        self._refresh_menu()

    def _action_next_station(self, icon=None, item=None):
        self.player.change_selection(1)
        self.player.play_selected()
        self._refresh_menu()

    def _action_prev_station(self, icon=None, item=None):
        self.player.change_selection(-1)
        self.player.play_selected()
        self._refresh_menu()

    def _action_quit(self, icon=None, item=None):
        self.player.running = False
        self.stop()

    def _build_menu(self) -> Any:
        """Costruisce il menu contestuale con stato corrente"""
        st = self.player.state

        if st.playing_station_index >= 0 and self.player.stations:
            station_label = f"\U0001f4fb {self.player.stations[st.playing_station_index].name[:50]}"
        else:
            station_label = "\U0001f4fb Radio Player"

        if st.stream_info and st.stream_info.song:
            song_label = f"\U0001f3b5 {st.stream_info.song[:60]}"
        elif st.is_playing:
            song_label = "\U0001f3b5 Titolo non disponibile"
        else:
            song_label = "\U0001f3b5 Nessuna traccia"

        play_label = "\u23f8  Pausa" if (st.is_playing and not st.is_paused) else "\u25b6  Play"
        mute_label = "\U0001f50a Riattiva audio" if st.is_muted else "\U0001f507 Muto"
        vol_label = f"\U0001f50a Volume: {st.volume}%"

        volume_items = [
            TrayItem("\U0001f50a Volume +5%", self._action_vol_up5),
            TrayItem("\U0001f509 Volume -5%", self._action_vol_down5),
            TrayMenu.SEPARATOR,
        ]
        for level in (0, 25, 50, 75, 100):
            check = "\u2713" if level == st.volume else "  "
            volume_items.append(
                TrayItem(f"{check}  {level}%", self._action_set_volume(level))
            )
        volume_menu = TrayMenu(*volume_items)

        return TrayMenu(
            TrayItem(station_label, None, enabled=False),
            TrayItem(song_label, None, enabled=False),
            TrayMenu.SEPARATOR,
            TrayItem(play_label, self._action_play_pause, default=True),
            TrayItem("\u23f9  Stop", self._action_stop),
            TrayMenu.SEPARATOR,
            TrayItem("\u23ed  Stazione successiva", self._action_next_station),
            TrayItem("\u23ee  Stazione precedente", self._action_prev_station),
            TrayMenu.SEPARATOR,
            TrayItem(mute_label, self._action_mute, checked=lambda item: st.is_muted),
            TrayItem(vol_label, volume_menu),
            TrayMenu.SEPARATOR,
            TrayItem("\u274c Esci", self._action_quit),
        )

    def _refresh_menu(self):
        """Aggiorna menu e icona con lo stato corrente"""
        if self._icon is None:
            return
        try:
            st = self.player.state
            self._icon.icon = self._make_icon_image(
                playing=st.is_playing and not st.is_paused,
                muted=st.is_muted,
            )
            self._icon.menu = self._build_menu()
            self._icon.title = self._make_tooltip()
        except Exception as exc:
            # Un problema grafico non deve mai fermare il player o i metadata.
            logger.debug("Aggiornamento icona tray fallito: %s", exc)

    def _make_tooltip(self) -> str:
        """Crea il testo tooltip per l'icona"""
        st = self.player.state
        parts = []
        if st.playing_station_index >= 0 and self.player.stations:
            parts.append(self.player.stations[st.playing_station_index].name)
        if st.stream_info and st.stream_info.song:
            parts.append(st.stream_info.song)
        if st.is_playing and not st.is_paused:
            status = "\u25b6 In riproduzione"
        elif st.is_paused:
            status = "\u23f8 In pausa"
        else:
            status = "\u23f9 Fermo"
        if st.is_muted:
            status += " \U0001f507"
        parts.append(status)
        parts.append(f"\U0001f50a {st.volume}%")
        return " | ".join(parts) if parts else "Radio Player"

    def update(self):
        """Aggiorna tooltip e icona, al massimo ogni 200 ms."""
        if self._icon is None:
            return

        now = time.monotonic()
        with self._update_lock:
            if now - self._last_update >= 0.2:
                self._last_update = now
                refresh_now = True
            else:
                refresh_now = False
                if self._update_timer is None:
                    delay = max(0.05, 0.2 - (now - self._last_update))
                    timer = threading.Timer(delay, self._delayed_update)
                    timer.daemon = True
                    self._update_timer = timer
                    timer.start()

        if refresh_now:
            self._refresh_menu()

    def _delayed_update(self):
        with self._update_lock:
            self._update_timer = None
            self._last_update = time.monotonic()
        self._refresh_menu()

    def _run(self):
        """Esegue il loop dell'icona tray nel thread dedicato."""
        try:
            self._icon.run()
        except Exception as exc:
            logger.error("Errore nel loop dell'icona tray: %s", exc, exc_info=True)

    def start(self) -> bool:
        """Avvia l'icona tray in un thread dedicato (non-bloccante).

        Restituisce True se l'icona è stata creata correttamente.
        """
        if not TRAY_AVAILABLE:
            self._start_error = tray_unavailable_message()
            logger.warning("pystray non disponibile: %s", self._start_error)
            return False
        if self._icon is not None:
            return True
        try:
            self._icon = TrayIcon(
                name="RadioPlayer",
                icon=self._make_icon_image(playing=False),
                title="Radio Player",
                menu=self._build_menu(),
            )
            self._thread = threading.Thread(
                target=self._run,
                name="SystemTray",
                daemon=True,
            )
            self._thread.start()
            self._start_error = ""
            logger.info("Icona tray avviata (backend %s)", TRAY_BACKEND or "auto")
            return True
        except Exception as exc:
            self._icon = None
            self._thread = None
            self._start_error = f"Impossibile avviare l'icona tray: {exc}"
            logger.warning("%s", self._start_error, exc_info=True)
            return False

    def stop(self):
        """Ferma l'icona tray"""
        with self._update_lock:
            if self._update_timer is not None:
                self._update_timer.cancel()
                self._update_timer = None
        if self._icon is not None:
            try:
                self._icon.stop()
            except Exception:
                pass
            self._icon = None
        logger.info("Icona tray fermata")
