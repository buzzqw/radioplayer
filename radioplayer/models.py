"""Data models for Radio Player M3U."""

import time
from dataclasses import dataclass, field, replace
from typing import Optional, Dict, List, Any
from enum import Flag, auto


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


@dataclass(frozen=True)
class StreamInfo:
    """Informazioni sullo stream corrente (immutabile per thread safety)"""
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

    def replace(self, **kwargs) -> "StreamInfo":
        """Crea una nuova istanza con i campi specificati modificati."""
        return replace(self, **kwargs)


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
