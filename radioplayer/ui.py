"""Rich UI rendering mixin for RadioPlayer."""

import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, List

try:
    from rich.console import Console
    from rich.live import Live
    from rich.panel import Panel
    from rich.table import Table
    from rich.layout import Layout
    from rich.text import Text
    RICH_AVAILABLE = True
except ImportError:
    Console = None
    Live = None
    Panel = None
    Table = None
    Layout = None
    Text = None
    RICH_AVAILABLE = False

from .models import UpdateFlags


class RichUIMixin:
    """Mixin che contiene tutti i metodi di rendering Rich per RadioPlayer."""

    # Attributi definiti in RadioPlayer, usati qui
    use_rich: bool
    state: Any
    stations: List
    pending_updates: Any
    search_mode: bool
    search_query: str
    search_results: List
    search_selected_idx: int
    search_loading: bool
    _last_searched_query: str
    _preview_station: Optional[Any]
    is_recording: bool
    logging_enabled: bool
    temp_message: str
    temp_message_time: float
    show_history_overlay: bool
    history: Any
    number_input_mode: bool
    number_buffer: str
    session_start_time: float
    console: Any
    live: Any
    running: bool
    m3u_file_path: Optional[Path]
    group_filter: Optional[str]
    local_search_mode: bool
    local_search_query: str
    favorites: set
    eq_preset_idx: int
    eq_names: List[str]
    show_help_overlay: bool

    def _build_rich_layout(self) -> Optional[Any]:
        """Costruisce il layout Rich"""
        if not RICH_AVAILABLE:
            return None

        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="status", size=5),
            Layout(name="stations", size=12),
            Layout(name="controls", ratio=1),
            Layout(name="footer", size=1),
        )
        return layout

    def _render_rich_header(self) -> Optional[Any]:
        """Renderizza header Rich"""
        if not RICH_AVAILABLE:
            return None

        current_time = datetime.now().strftime("%H:%M:%S")
        elapsed = time.time() - self.session_start_time
        h = int(elapsed // 3600)
        m = int((elapsed % 3600) // 60)
        s = int(elapsed % 60)
        uptime = f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"

        volume_icon = "\U0001f507" if self.state.is_muted else "\U0001f50a"
        notif_icon = "\U0001f514" if self.state.show_song_popups else "\U0001f515"
        log_status = "\U0001f4dd LOG" if self.logging_enabled else "\U0001f4dd \u2717"

        # Barra volume visuale (10 segmenti)
        vol_bar = self._volume_bar(self.state.volume)
        vol_style = "red" if self.state.is_muted else "green"

        # Indicatore EQ corrente
        eq_name = self.eq_names[self.eq_preset_idx]
        eq_part = f"    \U0001f3a7 {eq_name}" if self.eq_preset_idx != 0 else ""

        header_text = Text()
        header_text.append("\U0001f3b5 RADIO PLAYER M3U", style="bold cyan")
        header_text.append(f"    \u23f0 {current_time}", style="white")
        header_text.append(f"    Uptime: {uptime}", style="yellow")
        header_text.append(f"    {volume_icon} Volume {vol_bar} {self.state.volume}%", style=vol_style)
        header_text.append(f"    {log_status}", style="bold red" if self.logging_enabled else "dim")
        header_text.append(f"    {notif_icon}", style="blue")
        header_text.append(eq_part, style="magenta")

        return Panel(header_text, border_style="cyan")

    def _volume_bar(self, volume: int, width: int = 10) -> str:
        """Barra del volume visuale (es. ████████░░)."""
        filled = round(volume / 100 * width)
        bar = "\u2588" * filled + "\u2591" * (width - filled)
        if self.state.is_muted:
            return f"[dim]\u2715 {bar}[/dim]"
        return bar

    def _equalizer(self, width: int = 8) -> str:
        """Equalizer animato deterministico basato sul tempo (8 barre)."""
        t = int(time.time() * 3)
        heights = [
            1, 2, 4, 3, 2, 5, 3, 1,
        ]
        bars = []
        for i, h in enumerate(heights):
            # Ampiezza oscillante: base h + onda sinusoidale spostata per barra
            amp = (t + i * 3) % (h + 2)
            level = 1 + (amp % h)
            bar = "\u2581\u2581\u2583\u2585\u2587\u258f"  # livelli Unicode
            seg = bar[min(level, 5) - 1]
            bars.append(f"[bold green]{seg}[/bold green]" if level >= 4 else f"[green]{seg}[/green]")
        return "".join(bars)

    def _render_rich_status(self) -> Optional[Any]:
        """Renderizza status Rich (3 righe di contenuto, size=5)"""
        if not RICH_AVAILABLE:
            return None

        si = self.state.stream_info

        if self.state.is_playing and not self.state.is_paused:
            status_part = "[bold green]\u25b6  IN RIPRODUZIONE[/bold green]"
        elif self.state.is_paused:
            status_part = "[bold yellow]\u23f8  IN PAUSA[/bold yellow]"
        else:
            status_part = "[bold red]\u23f9  FERMATO[/bold red]"

        station_part = ""
        if self.state.playing_station_index >= 0:
            station = self.stations[self.state.playing_station_index]
            station_part = f"  [dim]\u2502[/dim]  [cyan]\U0001f4e1 {station.name}[/cyan]"
        elif self._preview_station:
            station_part = f"  [dim]\u2502[/dim]  [magenta]\U0001f442 {self._preview_station.name} (anteprima)[/magenta]"

        rec_part = "  [bold red]\U0001f534 REC[/bold red]" if self.is_recording else ""
        line1 = f"{status_part}{station_part}{rec_part}"

        if si.artist and si.song:
            song_time = si.get_song_time(self.state.is_playing, self.state.is_paused)
            time_str = f" [yellow][{song_time}][/yellow]" if song_time != "00:00" else ""
            eq = f" {self._equalizer()}" if self.state.is_playing and not self.state.is_paused else ""
            line2 = f"[magenta]\U0001f3a4 {si.artist}[/magenta]  [bold blue]\U0001f3bc {si.song}[/bold blue]{time_str}{eq}"
        elif si.song or si.title:
            song = si.song or si.title
            song_time = si.get_song_time(self.state.is_playing, self.state.is_paused)
            time_str = f" [yellow][{song_time}][/yellow]" if song_time != "00:00" else ""
            eq = f" {self._equalizer()}" if self.state.is_playing and not self.state.is_paused else ""
            line2 = f"[bold blue]\U0001f3bc {song}[/bold blue]{time_str}{eq}"
        elif self.state.is_playing:
            line2 = "[dim italic]\U0001f3bc In attesa dei metadata dello stream...[/dim italic]"
        else:
            line2 = ""

        if self.temp_message and (time.time() - self.temp_message_time) < 2:
            line3 = f"[bold yellow]\U0001f4ac {self.temp_message}[/bold yellow]"
        else:
            tech = []
            if si.audio_bitrate or si.bitrate:
                tech.append(f"\U0001f50a {si.audio_bitrate or si.bitrate}")
            if si.codec:
                tech.append(f"[dim]{si.codec}[/dim]")
            if si.buffer_status:
                if si.buffer_status == "BUFFERING":
                    tech.append("[bold red blink]\U0001f504 BUFFERING[/bold red blink]")
                elif si.buffer_status.isdigit():
                    pct = int(si.buffer_status)
                    if pct < 30:
                        tech.append(f"[yellow]\U0001f4e6 Cache {pct}%[/yellow]")
                    else:
                        tech.append(f"[green]\U0001f4e6 Cache {pct}%[/green]")
                else:
                    tech.append(f"[green]\U0001f4e6 {si.buffer_status}[/green]")
            line3 = f"[dim]{'  \u2022  '.join(tech)}[/dim]" if tech else ""

        parts = [line1]
        if line2:
            parts.append(line2)
        if line3:
            parts.append(line3)

        status_title = "Status"
        if self.eq_preset_idx != 0:
            status_title += f"  [magenta]\U0001f3a7 {self.eq_names[self.eq_preset_idx]}[/magenta]"
        if self.is_recording:
            status_title += "  [bold red]\u23fa REC[/bold red]"
        if self.state.is_paused:
            status_title += "  [yellow]\u23f8 Pausa[/yellow]"

        return Panel("\n".join(parts), title=status_title, border_style="green")

    def _render_rich_stations(self) -> Optional[Any]:
        """Renderizza lista stazioni Rich con separatori di gruppo e highlight ricerca."""
        if not RICH_AVAILABLE:
            return None

        n_visible = 10

        filtered = self._get_filtered_stations()
        n_stations = len(filtered)
        total_stations = len(self.stations)

        start_idx = max(0, self.state.selected_station_index - n_visible // 2)
        if start_idx + n_visible > n_stations:
            start_idx = max(0, n_stations - n_visible)
        end_idx = min(n_stations, start_idx + n_visible)

        query = self.local_search_query.lower() if self.local_search_mode else ""

        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Marker", style="cyan", width=5, no_wrap=True)
        table.add_column("Number", style="yellow", width=4, no_wrap=True)
        table.add_column("Name", style="white")

        last_group = None

        for fi in range(start_idx, end_idx):
            station = filtered[fi]
            try:
                i = self.stations.index(station)
            except ValueError:
                i = fi

            # Separatore di gruppo quando cambia il gruppo
            if station.group != last_group:
                last_group = station.group
                group_title = Text(f"  \u2500\u2500 {station.group or 'Generale'} ", style="bold dim cyan")
                table.add_row("", "", group_title)

            is_fav = station.url in self.favorites
            fav_star = "\u2b50" if is_fav else " "

            marker = "\U0001f449" if i == self.state.selected_station_index else "  "

            if i == self.state.playing_station_index and self.state.is_playing:
                marker += "\u25b6\ufe0f" if not self.state.is_paused else "\u23f8\ufe0f"
            else:
                marker += " "

            style = "bold reverse" if i == self.state.selected_station_index else ""

            # Evidenzia la parte del nome che combacia con la ricerca
            name_text = Text(station.name, style=style or "white")
            if query:
                idx = station.name.lower().find(query)
                if idx >= 0:
                    name_text = Text()
                    before = station.name[:idx]
                    match = station.name[idx:idx + len(query)]
                    after = station.name[idx + len(query):]
                    name_text.append(before, style=style or "white")
                    name_text.append(match, style="bold yellow")
                    name_text.append(after, style=style or "white")

            table.add_row(marker, f"{fav_star}{i + 1}", name_text, style=style)

        title_parts = ["\U0001f4fb Stazioni"]
        if self.group_filter:
            title_parts.append(f"[yellow]{self.group_filter}[/yellow]")
        if self.local_search_mode and self.local_search_query:
            title_parts.append(f"[magenta]/{self.local_search_query}[/magenta]")
        title_parts.append(f"({n_stations}")

        if n_stations != total_stations:
            title_parts.append(f" di {total_stations}")
        title_parts.append(" totali)")

        if n_stations > n_visible:
            title_parts.append(f"  [{start_idx + 1}\u2013{end_idx} di {n_stations}]")

        title = " ".join(title_parts)
        return Panel(table, title=title, border_style="blue")

    def _render_rich_controls(self) -> Optional[Any]:
        """Renderizza controlli Rich in tabella 4-colonne leggibile"""
        if not RICH_AVAILABLE:
            return None

        controls = [
            ("\u2191/\u2193", "\U0001f4cb Seleziona stazione", "+/=", "\U0001f50a Alza volume"),
            ("p/Spazio", "\u25b6\ufe0f  Play/Pausa", "-/_", "\U0001f509 Abbassa volume"),
            ("m", "\U0001f507 Muto/Riattiva", "1-9+\u21b5", "\U0001f522 Vai a numero"),
            ("r", "\u23fa\ufe0f  Rec ON/OFF", "l", "\U0001f4dd Log ON/OFF"),
            ("t", "\U0001f514 Toggle notifiche", "h", "\U0001f4dc Cronologia brani"),
            ("b", "\U0001f310 Sfoglia RadioBrowser", "s", "\U0001f4be Salva cronologia"),
            ("g", "\U0001f4cb Filtro gruppo", "*", "\u2b50 Preferiti"),
            ("d", "\U0001f5d1\ufe0f Rimuovi stazione", "/", "\U0001f50d Cerca nel M3U"),
            ("e", "\U0001f3a7 EQ", "?", "\U0001f4a1 Aiuto"),
            ("a-z", "\U0001f50d Salta a lettera", "q", "\U0001f6aa Esci"),
        ]

        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column(justify="left", no_wrap=True, style="cyan")
        table.add_column(justify="left", no_wrap=True)
        table.add_column(justify="left", no_wrap=True, style="cyan")
        table.add_column(justify="left", no_wrap=True)

        for left_key, left_desc, right_key, right_desc in controls:
            table.add_row(left_key, left_desc, right_key, right_desc)

        if self.local_search_mode:
            search_text = Text()
            cursor = "_" if int(time.time() * 2) % 2 == 0 else " "
            search_text.append("/", style="bold magenta")
            search_text.append(f"{self.local_search_query}{cursor}", style="bold white")
            table.add_row(search_text, "Cerca stazione locale...", "", "")

        if self.number_input_mode:
            input_text = Text()
            input_text.append("\U0001f522 INSERISCI NUMERO: ", style="bold yellow")
            input_text.append(f"{self.number_buffer}_", style="bold white")
            input_text.append(" (Invio=conferma, Esc=annulla)", style="dim")
            table.add_row(input_text, "", "", "")

        return Panel(table, title="\U0001f3ae Controlli", border_style="yellow")

    def _render_rich_footer(self) -> Optional[Any]:
        """Renderizza footer Rich"""
        if not RICH_AVAILABLE:
            return None

        footer = Text()
        footer.append("\u00a9 2025 Andres Zanzani ", style="dim")
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

        spinner_chars = ("\u280b", "\u2819", "\u2839", "\u2838", "\u283c", "\u2834", "\u2826", "\u2827", "\u2807", "\u280f")
        spinner = spinner_chars[int(time.time() * 8) % 10]
        cursor = "_" if int(time.time() * 2) % 2 == 0 else " "

        if self.search_loading:
            input_title = f"\U0001f50d RadioBrowser.info  [bold yellow]{spinner} RICERCA IN CORSO...[/bold yellow]"
            input_border = "yellow"
            res_title = f"[bold yellow]{spinner} Ricerca in corso...[/bold yellow]"
            res_border = "yellow"
            res_body = (
                f"\n[bold yellow]{spinner}  Interrogazione RadioBrowser.info...[/bold yellow]\n\n"
                f'[dim]Cerca: "[italic]{self.search_query}[/italic]"[/dim]'
            )
        elif self.search_results:
            input_title = f"\U0001f50d RadioBrowser.info  [bold green]\u2705 {len(self.search_results)} stazioni trovate[/bold green]"
            input_border = "green"
            n = len(self.search_results)
            res_title = f"Risultati ({n})"
            res_border = "green"
            res_body = None
        elif self._last_searched_query:
            input_title = f'\U0001f50d RadioBrowser.info  [bold red]\u274c Nessun risultato per "{self._last_searched_query}"[/bold red]'
            input_border = "red"
            res_title = "Risultati"
            res_border = "red"
            res_body = f'[bold red]\u274c  Nessuna stazione trovata per "[italic]{self._last_searched_query}[/italic]"[/bold red]\n\n[dim]Prova con termini diversi (es. solo il nome, senza prefisso paese)[/dim]'
        else:
            input_title = "\U0001f50d RadioBrowser.info \u2014 sfoglia 40.000+ stazioni"
            input_border = "magenta"
            res_title = "Risultati"
            res_border = "magenta"
            res_body = "[dim italic]Inizia a digitare il nome della stazione...[/dim italic]"

        input_content = f"[bold white]{self.search_query}{cursor}[/bold white]"
        layout["search_input"].update(
            Panel(input_content, title=input_title, border_style=input_border)
        )

        if self.search_results and not self.search_loading:
            table = Table(show_header=True, box=None, padding=(0, 1))
            table.add_column("", width=2, no_wrap=True)
            table.add_column("Nome", style="white", ratio=3)
            table.add_column("Paese", style="cyan", width=6, no_wrap=True)
            table.add_column("kbps", style="yellow", width=6, no_wrap=True, justify="right")
            table.add_column("Codec", style="dim", width=6, no_wrap=True)
            table.add_column("\u2605 Voti", style="green", width=8, no_wrap=True, justify="right")

            n_visible = 15
            start = max(0, self.search_selected_idx - n_visible // 2)
            if start + n_visible > len(self.search_results):
                start = max(0, len(self.search_results) - n_visible)
            end = min(len(self.search_results), start + n_visible)

            for i in range(start, end):
                s = self.search_results[i]
                marker = "\U0001f449" if i == self.search_selected_idx else "  "
                already = any(e.url.rstrip("/") == s.url.rstrip("/") for e in self.stations)
                name = f"[dim]{s.name} \u2713[/dim]" if already else s.name
                country = s.metadata.get("rb-country", "")[:5]
                bitrate = s.metadata.get("rb-bitrate", "0")
                codec = s.metadata.get("rb-codec", "")[:6]
                votes = s.metadata.get("rb-votes", "0")
                style = "bold reverse" if i == self.search_selected_idx else ""
                table.add_row(marker, name, country, bitrate, codec, votes, style=style)

            if len(self.search_results) > n_visible:
                res_title += f"  [{start + 1}\u2013{end}]"

            layout["search_results"].update(Panel(table, title=res_title, border_style=res_border))
        else:
            layout["search_results"].update(Panel(res_body, title=res_title, border_style=res_border))

        preview_hint = "  [cyan]p[/cyan] Ferma anteprima" if self.state.is_playing else "  [cyan]p[/cyan] Ascolta anteprima"
        ctrl = (
            "[cyan]\u2191/\u2193[/cyan] Naviga  "
            "[cyan]\u21b5[/cyan] Aggiungi a M3U  "
            f"{preview_hint}  "
            "[cyan]\u232b[/cyan] Cancella  "
            "[cyan]Esc[/cyan] Torna alla lista"
        )
        layout["search_controls"].update(Panel(ctrl, title="\U0001f3ae Comandi ricerca", border_style="yellow"))

        return layout

    def _render_rich_history(self) -> Optional[Any]:
        """Renderizza overlay cronologia brani"""
        if not RICH_AVAILABLE:
            return None

        last = self.history.get_last(10)

        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="hist_panel", ratio=1),
            Layout(name="footer", size=1),
        )
        layout["header"].update(self._render_rich_header())

        table = Table(show_header=True, box=None, padding=(0, 1))
        table.add_column("#", style="dim", width=3, justify="right")
        table.add_column("Artista", style="cyan", ratio=2)
        table.add_column("Brano", style="white", ratio=3)
        table.add_column("Stazione", style="green", ratio=2)
        table.add_column("Orario", style="dim", width=8)

        if last:
            for i, entry in enumerate(reversed(last), 1):
                artist = entry.get('artist', '') or ''
                song = entry.get('song', '') or ''
                station = entry.get('station', '') or ''
                ts = entry.get('timestamp', '')
                orario = ts[11:16] if len(ts) >= 16 else ''
                table.add_row(str(i), artist, song, station, orario)
        else:
            table.add_row("", "[dim italic]Nessun brano in cronologia[/dim italic]", "", "", "")

        layout["hist_panel"].update(
            Panel(table, title="\U0001f4dc Cronologia brani  [dim](premi H per chiudere)[/dim]",
                  border_style="magenta")
        )
        layout["footer"].update(self._render_rich_footer())
        return layout

    def _render_rich_help(self) -> Optional[Any]:
        """Renderizza overlay con tutti i comandi."""
        if not RICH_AVAILABLE:
            return None

        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="help_panel", ratio=1),
            Layout(name="footer", size=1),
        )
        layout["header"].update(self._render_rich_header())

        rows = [
            ("\u2191/\u2193", "Seleziona stazione", "p / Spazio", "Play/Pausa"),
            ("1-9 + \u21b5", "Vai a stazione numero", "g", "Filtro per gruppo"),
            ("*", "Aggiungi/rimuovi preferito", "d", "Rimuovi stazione"),
            ("/", "Cerca nel M3U", "e", "Preset EQ"),
            ("+ / = / - / _", "Volume \u00b1 5%", "m", "Muto/Riattiva"),
            ("r", "Registra stream", "t", "Notifiche ON/OFF"),
            ("l", "Logging ON/OFF", "b", "Sfoglia RadioBrowser"),
            ("s", "Salva cronologia", "h", "Cronologia brani"),
            ("?", "Questo aiuto", "q", "Esci"),
        ]

        table = Table(show_header=True, box=None, padding=(0, 2))
        table.add_column("Tasto", style="cyan", no_wrap=True)
        table.add_column("Azione", style="white")
        table.add_column("Tasto", style="cyan", no_wrap=True)
        table.add_column("Azione", style="white")

        for k1, d1, k2, d2 in rows:
            table.add_row(k1, d1, k2, d2)

        layout["help_panel"].update(
            Panel(table, title="\U0001f4a1 Aiuto  [dim](premi ? per chiudere)[/dim]",
                  border_style="yellow")
        )
        layout["footer"].update(self._render_rich_footer())
        return layout

    def _render_rich(self) -> Optional[Any]:
        """Renderizza interfaccia completa Rich. Rende solo i pannelli segnati dai flag."""
        if not RICH_AVAILABLE:
            return None

        if self.search_mode:
            self._ric_header = self._ric_status = self._ric_stations = None
            self._ric_controls = self._ric_footer = None
            return self._render_rich_search()

        if self.show_history_overlay:
            self._ric_header = self._ric_status = self._ric_stations = None
            self._ric_controls = self._ric_footer = None
            return self._render_rich_history()

        if self.show_help_overlay:
            self._ric_header = self._ric_status = self._ric_stations = None
            self._ric_controls = self._ric_footer = None
            return self._render_rich_help()

        flags = self.pending_updates

        # Prima volta o FULL: rigenera tutto
        if not hasattr(self, '_ric_header') or self._ric_header is None or (flags & UpdateFlags.FULL) == UpdateFlags.FULL:
            self._ric_header = self._render_rich_header()
            self._ric_status = self._render_rich_status()
            self._ric_stations = self._render_rich_stations()
            self._ric_controls = self._render_rich_controls()
            self._ric_footer = self._render_rich_footer()
        else:
            # Aggiornamenti selettivi: rigenera solo i pannelli segnati
            if flags & (UpdateFlags.TIMER | UpdateFlags.INPUT):
                self._ric_header = self._render_rich_header()

            if flags & (UpdateFlags.STATUS | UpdateFlags.SONG | UpdateFlags.TECHNICAL):
                self._ric_status = self._render_rich_status()

            if flags & UpdateFlags.STATIONS:
                self._ric_stations = self._render_rich_stations()

            if flags & UpdateFlags.INPUT:
                self._ric_controls = self._render_rich_controls()

        # Layout nuovo ogni frame (costo zero) per evitare il cache 'is' di Live
        layout = self._build_rich_layout()
        layout["header"].update(self._ric_header)
        layout["status"].update(self._ric_status)
        layout["stations"].update(self._ric_stations)
        layout["controls"].update(self._ric_controls)
        layout["footer"].update(self._ric_footer)
        return layout
