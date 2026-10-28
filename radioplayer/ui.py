"""Rich UI rendering mixin for RadioPlayer."""

import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, List, Tuple

try:
    from rich.console import Console  # noqa: F401
    from rich.live import Live  # noqa: F401
    from rich.markup import escape
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
    escape = str
    RICH_AVAILABLE = False

from . import __version__
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
    search_error: str
    search_offset: int
    search_has_more: bool
    search_loading_more: bool
    _last_searched_query: str
    _preview_station: Optional[Any]
    is_recording: bool
    logging_enabled: bool
    temp_message: str
    temp_message_time: float
    show_history_overlay: bool
    show_group_overlay: bool
    group_overlay_idx: int
    history: Any
    number_input_mode: bool
    number_buffer: str
    session_start_time: float
    console: Any
    live: Any
    running: bool
    m3u_file_path: Optional[Path]
    group_filter: Optional[str]
    available_groups: List[str]
    local_search_mode: bool
    local_search_query: str
    favorites: set
    show_favorites_only: bool
    eq_preset_idx: int
    eq_names: List[str]
    show_help_overlay: bool
    _stations_visible_rows: int
    _last_console_size: Optional[Tuple[int, int]]
    _layout_has_footer: bool

    # ------------------------------------------------------------------
    # Helper di layout
    # ------------------------------------------------------------------

    def _terminal_size(self) -> Tuple[int, int]:
        try:
            size = self.console.size
            return max(40, size.width), max(10, size.height)
        except Exception:
            return 80, 24

    def _layout_mode(self) -> str:
        _, height = self._terminal_size()
        if height >= 40:
            return "full"
        if height >= 24:
            return "compact"
        return "mini"

    def _build_rich_layout(self) -> Optional[Any]:
        """Costruisce il layout Rich in base all'altezza del terminale."""
        if not RICH_AVAILABLE:
            return None

        mode = self._layout_mode()
        controls_size = {"full": 13, "compact": 8, "mini": 5}[mode]
        if mode == "mini" and (self.local_search_mode or self.number_input_mode):
            controls_size += 1
        footer_size = 0 if mode == "mini" else 1
        self._layout_has_footer = bool(footer_size)
        status_size = 5
        stations_size = max(
            3, self._terminal_size()[1] - (3 + status_size + controls_size + footer_size)
        )

        layout = Layout()
        sections = [
            Layout(name="header", size=3),
            Layout(name="status", size=status_size),
            Layout(name="stations", size=stations_size),
            Layout(name="controls", ratio=1),
        ]
        if footer_size:
            sections.append(Layout(name="footer", size=footer_size))
        layout.split_column(*sections)
        self._stations_visible_rows = max(3, stations_size - 2)
        return layout

    # ------------------------------------------------------------------
    # Header / status
    # ------------------------------------------------------------------

    def _render_rich_header(self) -> Optional[Any]:
        """Renderizza header Rich, adattato alla larghezza del terminale."""
        if not RICH_AVAILABLE:
            return None

        width, _ = self._terminal_size()
        current_time = datetime.now().strftime("%H:%M:%S")
        elapsed = time.time() - self.session_start_time
        h = int(elapsed // 3600)
        m = int((elapsed % 3600) // 60)
        s = int(elapsed % 60)
        uptime = f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"

        vol_bar = self._volume_bar(self.state.volume)

        header_text = Text()
        header_text.append("\U0001f3b5 RADIO PLAYER M3U", style="bold cyan")
        header_text.append(f"    \u23f0 {current_time}", style="white")
        if width >= 90:
            header_text.append(f"    Uptime: {uptime}", style="yellow")

        if self.state.is_muted:
            vol_text = f"    \U0001f507 {self.state.volume}%" if width < 70 else (
                f"    \U0001f507 Volume {vol_bar} {self.state.volume}%"
            )
            header_text.append(vol_text, style="dim red")
        else:
            vol_text = f"    \U0001f50a {self.state.volume}%" if width < 70 else (
                f"    \U0001f50a Volume {vol_bar} {self.state.volume}%"
            )
            header_text.append(vol_text, style="green")

        if width >= 100:
            log_status = "\U0001f4dd LOG" if self.logging_enabled else "\U0001f4dd \u2717"
            header_text.append(
                f"    {log_status}",
                style="bold red" if self.logging_enabled else "dim",
            )
            notif_icon = "\U0001f514" if self.state.show_song_popups else "\U0001f515"
            header_text.append(f"    {notif_icon}", style="blue")

        if width >= 110 and self.eq_preset_idx != 0:
            header_text.append(
                f"    \U0001f3a7 {self.eq_names[self.eq_preset_idx]}", style="magenta"
            )

        return Panel(header_text, border_style="cyan")

    def _volume_bar(self, volume: int, width: int = 10) -> str:
        """Barra del volume visuale (es. ████████░░), senza markup."""
        filled = round(volume / 100 * width)
        return "\u2588" * filled + "\u2591" * (width - filled)

    def _equalizer(self, width: int = 8) -> str:
        """Equalizer animato deterministico basato sul tempo (8 barre)."""
        t = int(time.time() * 3)
        heights = [1, 2, 4, 3, 2, 5, 3, 1]
        levels = "\u2581\u2581\u2583\u2585\u2587\u258f"
        bars = []
        for i, h in enumerate(heights):
            amp = (t + i * 3) % (h + 2)
            level = 1 + (amp % h)
            seg = levels[min(level, len(levels)) - 1]
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
        if 0 <= self.state.playing_station_index < len(self.stations):
            station = self.stations[self.state.playing_station_index]
            station_part = (
                f"  [dim]\u2502[/dim]  [cyan]\U0001f4e1 {escape(station.name)}[/cyan]"
            )
        elif self._preview_station:
            station_part = (
                f"  [dim]\u2502[/dim]  [magenta]\U0001f442 "
                f"{escape(self._preview_station.name)} (anteprima)[/magenta]"
            )

        rec_part = "  [bold red]\U0001f534 REC[/bold red]" if self.is_recording else ""
        line1 = f"{status_part}{station_part}{rec_part}"

        if si.artist and si.song:
            song_time = si.get_song_time(self.state.is_playing, self.state.is_paused)
            time_str = f" [yellow][{song_time}][/yellow]" if song_time != "00:00" else ""
            eq = f" {self._equalizer()}" if self.state.is_playing and not self.state.is_paused else ""
            line2 = (
                f"[magenta]\U0001f3a4 {escape(si.artist)}[/magenta]  "
                f"[bold blue]\U0001f3bc {escape(si.song)}[/bold blue]{time_str}{eq}"
            )
        elif si.song or si.title:
            song = si.song or si.title
            song_time = si.get_song_time(self.state.is_playing, self.state.is_paused)
            time_str = f" [yellow][{song_time}][/yellow]" if song_time != "00:00" else ""
            eq = f" {self._equalizer()}" if self.state.is_playing and not self.state.is_paused else ""
            line2 = f"[bold blue]\U0001f3bc {escape(song)}[/bold blue]{time_str}{eq}"
        elif self.state.is_playing:
            line2 = "[dim italic]\U0001f3bc In attesa dei metadata dello stream...[/dim italic]"
        else:
            line2 = ""

        if self.temp_message and (time.time() - self.temp_message_time) < 2:
            line3 = f"[bold yellow]\U0001f4ac {escape(self.temp_message)}[/bold yellow]"
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

    # ------------------------------------------------------------------
    # Lista stazioni
    # ------------------------------------------------------------------

    def _build_station_rows(self, entries: List[Tuple[int, Any]], selected_pos: int,
                            budget: int) -> Tuple[int, int, List[Tuple[int, Any, bool]]]:
        """Seleziona la finestra di stazioni che entra nel pannello."""
        budget = max(1, budget)
        start = max(0, selected_pos - budget // 2)

        def build(from_pos: int):
            rows: List[Tuple[int, Any, bool]] = []
            used = 0
            last_group = object()
            end = from_pos
            for pos in range(from_pos, len(entries)):
                global_idx, station = entries[pos]
                new_group = station.group != last_group
                need = 1 + (1 if new_group else 0)
                if used + need > budget:
                    break
                rows.append((global_idx, station, new_group))
                used += need
                last_group = station.group
                end = pos + 1
            return rows, end

        rows, end = build(start)
        if selected_pos >= end:
            start = selected_pos
            rows, end = build(start)
        return start, end, rows

    def _render_rich_stations(self) -> Optional[Any]:
        """Renderizza lista stazioni Rich con separatori di gruppo e filtri."""
        if not RICH_AVAILABLE:
            return None

        entries = self._get_visible_entries()
        n_stations = len(entries)
        total_stations = len(self.stations)
        selected_pos = self._filtered_positions.get(self.state.selected_station_index, 0)

        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Marker", style="cyan", width=5, no_wrap=True)
        table.add_column("Number", style="yellow", width=6, no_wrap=True)
        table.add_column("Name", style="white")

        query = self.local_search_query.lower() if self.local_search_mode else ""
        start_idx, end_idx, rows = self._build_station_rows(
            entries, selected_pos, self._stations_visible_rows
        )

        if not entries:
            table.add_row(
                "", "",
                Text("  Nessuna stazione con i filtri attivi", style="dim italic"),
            )
        else:
            for global_idx, station, new_group in rows:
                if new_group:
                    table.add_row(
                        "", "",
                        Text(f"  \u2500\u2500 {station.group or 'Generale'} ",
                             style="bold dim cyan"),
                    )

                is_fav = station.url in self.favorites
                fav_star = "\u2b50" if is_fav else " "

                is_selected = global_idx == self.state.selected_station_index
                is_playing = (
                    global_idx == self.state.playing_station_index
                    and self.state.is_playing
                )

                marker = "\U0001f449" if is_selected else "  "
                if is_playing:
                    marker += "\u25b6\ufe0f" if not self.state.is_paused else "\u23f8\ufe0f"
                else:
                    marker += " "

                row_style = ""
                if is_selected:
                    row_style = "bold reverse"
                elif is_playing:
                    row_style = "green"

                name_style = "white"
                if is_selected:
                    name_style = "bold reverse"
                elif is_playing:
                    name_style = "bold green"

                name_text = Text(station.name, style=name_style)
                if query:
                    idx = station.name.lower().find(query)
                    if idx >= 0:
                        name_text = Text()
                        before = station.name[:idx]
                        match = station.name[idx:idx + len(query)]
                        after = station.name[idx + len(query):]
                        name_text.append(before, style=name_style)
                        name_text.append(match, style="bold yellow")
                        name_text.append(after, style=name_style)

                table.add_row(marker, f"{fav_star}{global_idx + 1}", name_text,
                              style=row_style)

        title_parts = ["\U0001f4fb Stazioni"]
        if self.show_favorites_only:
            title_parts.append("\u2b50")
        if self.group_filter:
            title_parts.append(f"[yellow]{escape(self.group_filter)}[/yellow]")
        if self.local_search_mode and self.local_search_query:
            title_parts.append(f"[magenta]/{escape(self.local_search_query)}[/magenta]")

        if n_stations != total_stations:
            title_parts.append(f"({n_stations} di {total_stations} totali)")
        else:
            title_parts.append(f"({n_stations} totali)")

        if entries and len(rows) > 0:
            title_parts.append(f"  [{start_idx + 1}\u2013{end_idx} di {n_stations}]")

        title = " ".join(title_parts)
        return Panel(table, title=title, border_style="blue")

    # ------------------------------------------------------------------
    # Controlli
    # ------------------------------------------------------------------

    def _render_rich_controls(self) -> Optional[Any]:
        """Renderizza i controlli in forma compatta o completa."""
        if not RICH_AVAILABLE:
            return None

        mode = self._layout_mode()

        if mode == "full":
            controls = [
                ("\u2191/\u2193", "\U0001f4cb Seleziona", "p/Spazio", "\u25b6\ufe0f  Play/Pausa"),
                ("n/N", "\u23ed\ufe0f  Stazione \u00b1", "x", "\u23f9\ufe0f  Stop"),
                ("+/-", "\U0001f50a Volume", "m", "\U0001f507 Muto"),
                ("/", "\U0001f50d Cerca", "g", "\U0001f4cb Gruppi"),
                ("b", "\U0001f310 RadioBrowser", "f", "\u2b50 Solo preferiti"),
                ("*", "\u2b50 Preferito", "d", "\U0001f5d1\ufe0f Rimuovi"),
                ("u", "\u21a9\ufe0f  Annulla rimozione", "r", "\u23fa\ufe0f  Rec ON/OFF"),
                ("l", "\U0001f4dd Log ON/OFF", "t", "\U0001f514 Notifiche"),
                ("h", "\U0001f4dc Cronologia", "e", "\U0001f3a7 EQ"),
                ("1-9+\u21b5", "\U0001f522 Vai a numero", "?", "\U0001f4a1 Aiuto / q Esci"),
            ]
            columns = 4
        elif mode == "compact":
            controls = [
                ("\u2191/\u2193", "Seleziona", "p/Spazio", "Play/Pausa", "x", "Stop"),
                ("n/N", "Stazione", "+/-", "Volume", "m", "Muto"),
                ("/", "Cerca", "g", "Gruppi", "f", "Preferiti"),
                ("b", "RadioBrowser", "d", "Rimuovi", "e", "EQ"),
                ("?", "Aiuto", "q", "Esci", "*", "Preferito"),
            ]
            columns = 6
        else:
            controls = [
                ("p/Spazio", "Play/Pausa", "\u2191/\u2193", "Seleziona"),
                ("x", "Stop", "/", "Cerca"),
                ("?", "Aiuto", "q", "Esci"),
            ]
            columns = 4

        table = Table(show_header=False, box=None, padding=(0, 1))
        for col in range(columns):
            style = "cyan" if col % 2 == 0 else ""
            table.add_column(justify="left", no_wrap=True, style=style)

        for row in controls:
            table.add_row(*row)

        if self.local_search_mode:
            search_text = Text()
            cursor = "_" if int(time.time() * 2) % 2 == 0 else " "
            search_text.append("/", style="bold magenta")
            search_text.append(f"{self.local_search_query}{cursor}", style="bold white")
            table.add_row(search_text, "Cerca stazione locale...", *[""] * (columns - 2))

        if self.number_input_mode:
            input_text = Text()
            input_text.append("\U0001f522 INSERISCI NUMERO: ", style="bold yellow")
            input_text.append(f"{self.number_buffer}_", style="bold white")
            input_text.append(" (Invio=conferma, Esc=annulla)", style="dim")
            table.add_row(input_text, *[""] * (columns - 1))

        title = "\U0001f3ae Controlli"
        if mode == "full":
            title += "  [dim](? per tutti)[/dim]"

        return Panel(table, title=title, border_style="yellow")

    def _render_rich_footer(self) -> Optional[Any]:
        """Renderizza footer Rich, abbreviato sui terminali stretti."""
        if not RICH_AVAILABLE:
            return None

        width, _ = self._terminal_size()
        footer = Text()
        footer.append(f"v{__version__} ", style="dim")
        if width >= 100:
            footer.append("\u00a9 2025 Andres Zanzani ", style="dim")
            footer.append("<azanzani@gmail.com>", style="dim blue")
            footer.append(" - GPL 3 License", style="dim")
        else:
            footer.append("GPL 3 License", style="dim")
        return footer

    # ------------------------------------------------------------------
    # Overlay
    # ------------------------------------------------------------------

    def _render_rich_search(self) -> Optional[Any]:
        """Renderizza il pannello di ricerca RadioBrowser.info"""
        if not RICH_AVAILABLE:
            return None

        _, height = self._terminal_size()
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="search_input", size=3),
            Layout(name="search_results", ratio=1),
            Layout(name="search_controls", size=4),
        )

        layout["header"].update(self._render_rich_header())

        spinner_chars = ("\u280b", "\u2819", "\u2839", "\u2838", "\u283c",
                         "\u2834", "\u2826", "\u2827", "\u2807", "\u280f")
        spinner = spinner_chars[int(time.time() * 8) % 10]
        cursor = "_" if int(time.time() * 2) % 2 == 0 else " "

        if self.search_loading:
            input_title = f"\U0001f50d RadioBrowser.info  [bold yellow]{spinner} RICERCA IN CORSO...[/bold yellow]"
            input_border = "yellow"
            res_title = f"[bold yellow]{spinner} Ricerca in corso...[/bold yellow]"
            res_border = "yellow"
            res_body = (
                f"\n[bold yellow]{spinner}  Interrogazione RadioBrowser.info...[/bold yellow]\n\n"
                f'[dim]Cerca: "[italic]{escape(self.search_query)}[/italic]"[/dim]'
            )
        elif self.search_results:
            input_title = f"\U0001f50d RadioBrowser.info  [bold green]\u2705 {len(self.search_results)} stazioni trovate[/bold green]"
            input_border = "green"
            res_title = f"Risultati ({len(self.search_results)})"
            res_border = "green"
            res_body = None
        elif self.search_error:
            input_title = "\U0001f50d RadioBrowser.info  [bold red]\u274c Errore di connessione[/bold red]"
            input_border = "red"
            res_title = "Risultati"
            res_border = "red"
            res_body = (
                f"[bold red]\u274c  {escape(self.search_error)}[/bold red]\n\n"
                "[dim]Controlla la connessione e riprova; la ricerca riparte digitando.[/dim]"
            )
        elif self._last_searched_query:
            input_title = f'\U0001f50d RadioBrowser.info  [bold red]\u274c Nessun risultato per "{escape(self._last_searched_query)}"[/bold red]'
            input_border = "red"
            res_title = "Risultati"
            res_border = "red"
            res_body = (
                f'[bold red]\u274c  Nessuna stazione trovata per "[italic]{escape(self._last_searched_query)}[/italic]"[/bold red]\n\n'
                "[dim]Prova con termini diversi (es. solo il nome, senza prefisso paese)[/dim]"
            )
        else:
            input_title = "\U0001f50d RadioBrowser.info \u2014 sfoglia 40.000+ stazioni"
            input_border = "magenta"
            res_title = "Risultati"
            res_border = "magenta"
            res_body = "[dim italic]Inizia a digitare il nome della stazione...[/dim italic]"

        input_content = f"[bold white]{escape(self.search_query)}{cursor}[/bold white]"
        layout["search_input"].update(
            Panel(input_content, title=input_title, border_style=input_border)
        )

        if self.search_results and not self.search_loading:
            table = Table(show_header=True, box=None, padding=(0, 1))
            table.add_column("", width=2, no_wrap=True)
            table.add_column("Nome", style="white", ratio=3)
            table.add_column("Paese", style="cyan", width=7, no_wrap=True)
            table.add_column("kbps", style="yellow", width=6, no_wrap=True, justify="right")
            table.add_column("Codec", style="dim", width=6, no_wrap=True)
            table.add_column("\u2605 Voti", style="green", width=8, no_wrap=True, justify="right")

            n_visible = max(5, height - 11)
            start = max(0, self.search_selected_idx - n_visible // 2)
            if start + n_visible > len(self.search_results):
                start = max(0, len(self.search_results) - n_visible)
            end = min(len(self.search_results), start + n_visible)

            existing_urls = {s.url.rstrip("/") for s in self.stations}

            for i in range(start, end):
                s = self.search_results[i]
                marker = "\U0001f449" if i == self.search_selected_idx else "  "
                already = s.url.rstrip("/") in existing_urls
                name = f"[dim]{escape(s.name)} \u2713[/dim]" if already else escape(s.name)
                country = escape(s.metadata.get("rb-country", "")[:6])
                bitrate = escape(s.metadata.get("rb-bitrate", "0"))
                codec = escape(s.metadata.get("rb-codec", "")[:6])
                votes = escape(s.metadata.get("rb-votes", "0"))
                style = "bold reverse" if i == self.search_selected_idx else ""
                table.add_row(marker, name, country, bitrate, codec, votes, style=style)

            if len(self.search_results) > n_visible:
                res_title += f"  [{start + 1}\u2013{end}]"
            if self.search_loading_more:
                res_title += "  [yellow]caricamento...[/yellow]"

            layout["search_results"].update(Panel(table, title=res_title, border_style=res_border))
        else:
            layout["search_results"].update(Panel(res_body, title=res_title, border_style=res_border))

        preview_hint = (
            "  [cyan]p[/cyan] Ferma anteprima"
            if self.state.is_playing
            else "  [cyan]p[/cyan] Ascolta anteprima"
        )
        ctrl = (
            "[cyan]\u2191/\u2193[/cyan] Naviga  "
            "[cyan]PgUp/PgDn[/cyan] -10/+10  "
            + (
                "[cyan]Tab[/cyan] Altri 20  "
                if self.search_has_more or self.search_loading_more
                else ""
            )
            + "[cyan]\u21b5[/cyan] Aggiungi  "
            f"{preview_hint}  "
            "[cyan]\u232b[/cyan] Cancella  "
            "[cyan]Esc[/cyan] Torna"
        )
        layout["search_controls"].update(
            Panel(ctrl, title="\U0001f3ae Comandi ricerca", border_style="yellow")
        )

        return layout

    def _render_rich_groups(self) -> Optional[Any]:
        """Overlay per scegliere il gruppo con conteggi."""
        if not RICH_AVAILABLE:
            return None

        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="groups", ratio=1),
            Layout(name="footer", size=1),
        )
        layout["header"].update(self._render_rich_header())

        choices = [None] + self.available_groups
        total = len(self.stations)
        counts = {}
        for station in self.stations:
            counts[station.group] = counts.get(station.group, 0) + 1

        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("", width=2, no_wrap=True)
        table.add_column("Gruppo", style="cyan")
        table.add_column("Stazioni", style="yellow", justify="right", width=10)

        for i, group in enumerate(choices):
            marker = "\U0001f449" if i == self.group_overlay_idx else "  "
            label = "Tutti i gruppi" if group is None else group
            count = total if group is None else counts.get(group, 0)
            style = "bold reverse" if i == self.group_overlay_idx else ""
            table.add_row(marker, escape(label), str(count), style=style)

        layout["groups"].update(
            Panel(table, title="\U0001f4cb Gruppi  [dim](\u2191/\u2193, Invio, Esc)[/dim]",
                  border_style="magenta")
        )
        layout["footer"].update(self._render_rich_footer())
        return layout

    def _render_rich_history(self) -> Optional[Any]:
        """Renderizza overlay cronologia brani"""
        if not RICH_AVAILABLE:
            return None

        _, height = self._terminal_size()
        last = self.history.get_last(max(5, height - 9))

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
                table.add_row(
                    str(i), escape(artist), escape(song), escape(station), orario
                )
        else:
            table.add_row("", "[dim italic]Nessun brano in cronologia[/dim italic]", "", "", "")

        layout["hist_panel"].update(
            Panel(table,
                  title="\U0001f4dc Cronologia brani  [dim](Esc o H per chiudere)[/dim]",
                  border_style="magenta")
        )
        layout["footer"].update(self._render_rich_footer())
        return layout

    def _render_rich_help(self) -> Optional[Any]:
        """Renderizza overlay con tutti i comandi."""
        if not RICH_AVAILABLE:
            return None

        _, height = self._terminal_size()
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="help_panel", ratio=1),
            Layout(name="footer", size=1),
        )
        layout["header"].update(self._render_rich_header())

        rows = [
            ("\u2191/\u2193", "Seleziona stazione", "p / Spazio", "Play/Pausa"),
            ("n / N", "Stazione succ/prec", "x", "Stop"),
            ("1-9 + \u21b5", "Vai a stazione numero", "g", "Scegli gruppo"),
            ("G", "Cicla gruppo", "f", "Solo preferiti"),
            ("*", "Aggiungi/rimuovi preferito", "d / u", "Rimuovi / annulla"),
            ("/", "Cerca nel M3U", "e", "Preset EQ"),
            ("+ / -", "Volume \u00b1 5%", "m", "Muto/Riattiva"),
            ("r", "Registra stream", "t", "Notifiche ON/OFF"),
            ("l", "Logging ON/OFF", "b", "Sfoglia RadioBrowser"),
            ("s", "Salva cronologia", "h", "Cronologia brani"),
            ("PgUp/PgDn", "Salta 5 stazioni", "Home/End", "Prima/ultima"),
            ("?", "Questo aiuto", "q", "Esci"),
        ]
        max_rows = max(5, height - 8)
        rows = rows[:max_rows]

        table = Table(show_header=True, box=None, padding=(0, 2))
        table.add_column("Tasto", style="cyan", no_wrap=True)
        table.add_column("Azione", style="white")
        table.add_column("Tasto", style="cyan", no_wrap=True)
        table.add_column("Azione", style="white")

        for k1, d1, k2, d2 in rows:
            table.add_row(k1, d1, k2, d2)

        layout["help_panel"].update(
            Panel(table,
                  title="\U0001f4a1 Aiuto  [dim](Esc o ? per chiudere)[/dim]",
                  border_style="yellow")
        )
        layout["footer"].update(self._render_rich_footer())
        return layout

    # ------------------------------------------------------------------
    # Render principale
    # ------------------------------------------------------------------

    def _render_rich(self) -> Optional[Any]:
        """Renderizza interfaccia completa Rich. Rende solo i pannelli segnati dai flag."""
        if not RICH_AVAILABLE:
            return None

        # Un resize del terminale deve ridisegnare anche i pannelli in cache.
        size = self._terminal_size()
        if self._last_console_size != size:
            self._last_console_size = size
            self.pending_updates |= UpdateFlags.FULL

        if self.search_mode:
            self._ric_header = self._ric_status = self._ric_stations = None
            self._ric_controls = self._ric_footer = None
            return self._render_rich_search()

        if self.show_group_overlay:
            self._ric_header = self._ric_status = self._ric_stations = None
            self._ric_controls = self._ric_footer = None
            return self._render_rich_groups()

        if self.show_history_overlay:
            self._ric_header = self._ric_status = self._ric_stations = None
            self._ric_controls = self._ric_footer = None
            return self._render_rich_history()

        if self.show_help_overlay:
            self._ric_header = self._ric_status = self._ric_stations = None
            self._ric_controls = self._ric_footer = None
            return self._render_rich_help()

        layout = self._build_rich_layout()
        flags = self.pending_updates

        # Prima volta o FULL: rigenera tutto
        if (
            not hasattr(self, '_ric_header')
            or self._ric_header is None
            or (flags & UpdateFlags.FULL) == UpdateFlags.FULL
        ):
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

        layout["header"].update(self._ric_header)
        layout["status"].update(self._ric_status)
        layout["stations"].update(self._ric_stations)
        layout["controls"].update(self._ric_controls)
        if self._layout_has_footer:
            layout["footer"].update(self._ric_footer)
        return layout
