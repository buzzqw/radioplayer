"""System tray icon con menu contestuale."""

import logging
import threading
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from .player import RadioPlayer

logger = logging.getLogger("RadioPlayer")

TRAY_AVAILABLE = False

try:
    import pystray
    from pystray import Icon as TrayIcon, MenuItem as TrayItem, Menu as TrayMenu
    from PIL import Image as PILImage, ImageDraw as PILDraw
    TRAY_AVAILABLE = True
except ImportError:
    pass


class SystemTrayIcon:
    """Icona nel system tray con menu contestuale per controllare il player"""

    ICON_SIZE = 64

    def __init__(self, player: 'RadioPlayer'):
        self.player = player
        self._icon: Optional[Any] = None
        self._thread: Optional[threading.Thread] = None

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

        if st.stream_info and st.stream_info.song:
            song_label = f"\U0001f3b5 {st.stream_info.song[:50]}"
        elif st.playing_station_index >= 0 and self.player.stations:
            song_label = f"\U0001f4fb {self.player.stations[st.playing_station_index].name[:50]}"
        else:
            song_label = "\U0001f4fb Radio Player"

        play_label = "\u23f8  Pausa" if (st.is_playing and not st.is_paused) else "\u25b6  Play"
        mute_label = "\U0001f507 Riattiva audio" if st.is_muted else "\U0001f507 Muto"
        vol_label = f"\U0001f50a Volume: {st.volume}%"

        return TrayMenu(
            TrayItem(song_label, None, enabled=False),
            TrayMenu.SEPARATOR,
            TrayItem(play_label, self._action_play_pause),
            TrayItem("\u23f9  Stop", self._action_stop),
            TrayMenu.SEPARATOR,
            TrayItem("\u23ed  Stazione successiva", self._action_next_station),
            TrayItem("\u23ee  Stazione precedente", self._action_prev_station),
            TrayMenu.SEPARATOR,
            TrayItem(mute_label, self._action_mute),
            TrayMenu.SEPARATOR,
            TrayItem(vol_label, None, enabled=False),
            TrayItem("\U0001f50a Volume +5%", self._action_vol_up5),
            TrayItem("\U0001f509 Volume -5%", self._action_vol_down5),
            TrayMenu.SEPARATOR,
            TrayItem("\u274c Esci", self._action_quit),
        )

    def _refresh_menu(self):
        """Aggiorna menu e icona con lo stato corrente"""
        if self._icon is None:
            return
        st = self.player.state
        self._icon.icon = self._make_icon_image(
            playing=st.is_playing and not st.is_paused,
            muted=st.is_muted,
        )
        self._icon.menu = self._build_menu()
        self._icon.title = self._make_tooltip()

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
        return " | ".join(parts) if parts else "Radio Player"

    def update(self):
        """Aggiorna tooltip e icona (chiamare ad ogni cambio stato/canzone)"""
        if self._icon is not None:
            self._refresh_menu()

    def start(self):
        """Avvia l'icona tray in un thread dedicato (non-bloccante)"""
        if not TRAY_AVAILABLE:
            logger.warning("pystray non disponibile: icona tray disabilitata")
            return
        try:
            self._icon = TrayIcon(
                name="RadioPlayer",
                icon=self._make_icon_image(playing=False),
                title="Radio Player",
                menu=self._build_menu(),
            )
            self._thread = threading.Thread(
                target=self._icon.run,
                name="SystemTray",
                daemon=True,
            )
            self._thread.start()
            logger.info("Icona tray avviata")
        except Exception as e:
            logger.warning(f"Impossibile avviare icona tray: {e}")

    def stop(self):
        """Ferma l'icona tray"""
        if self._icon is not None:
            try:
                self._icon.stop()
            except Exception:
                pass
            self._icon = None
        logger.info("Icona tray fermata")
