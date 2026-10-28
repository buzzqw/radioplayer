"""Entry point for Radio Player M3U."""

import argparse
import os
import sys
from pathlib import Path
from typing import List, Optional

if sys.version_info < (3, 8):
    sys.exit("Python 3.8+ richiesto")

from radioplayer import __version__
from radioplayer.config import load_config
from radioplayer.logging_setup import setup_logging, enable_file_logging
from radioplayer.m3u import M3UParser, discover_m3u_files

logger = setup_logging()


def find_m3u_files() -> List[Path]:
    """Cerca file M3U nella directory dello script e nella directory corrente."""
    directories = []
    try:
        directories.append(Path(__file__).parent.parent.resolve())
    except Exception:
        pass
    directories.append(Path.cwd())
    return discover_m3u_files(*directories)


def _configure_output() -> None:
    """Evita UnicodeEncodeError sui terminali Windows legacy."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="radioplayer",
        description="Radio Player M3U - lettore radio da terminale",
    )
    parser.add_argument("file", nargs="?", help="file M3U da riprodurre")
    parser.add_argument(
        "--version", action="version", version=f"Radio Player M3U v{__version__}"
    )
    parser.add_argument(
        "--no-tray", action="store_true", help="disabilita l'icona nel system tray"
    )
    parser.add_argument(
        "--no-color", action="store_true", help="disabilita i colori (anche NO_COLOR)"
    )
    parser.add_argument(
        "--volume", type=int, metavar="0-100", help="volume iniziale"
    )
    parser.add_argument(
        "--ao", metavar="DRIVER", help="driver audio mpv (es. null, pulse, pipewire)"
    )
    parser.add_argument(
        "--list", action="store_true", help="elenca le stazioni della playlist ed esce"
    )
    parser.add_argument(
        "--choose", action="store_true", help="mostra sempre la scelta della playlist"
    )
    parser.add_argument(
        "--last", action="store_true", help="riprendi l'ultima playlist usata"
    )
    parser.add_argument(
        "--debug", action="store_true", help="abilita il log su file"
    )
    return parser


def _resolve_m3u_file(file_arg: Optional[str], force_choose: bool = False,
                      use_last: bool = False) -> Optional[Path]:
    """Sceglie il file M3U: argomento, ultima playlist (--last) o selezione."""
    if file_arg:
        path = Path(file_arg).expanduser()
        if not path.is_file():
            print(f"\u274c File non trovato: {path}")
            return None
        return path

    if use_last and not force_choose:
        last_m3u = load_config().get("last_m3u")
        if last_m3u:
            path = Path(str(last_m3u)).expanduser()
            if path.is_file():
                print(f"\U0001f4c2 Riprendo l'ultima playlist: {path}")
                return path

    m3u_files = find_m3u_files()
    if not m3u_files:
        print("\u274c Nessun file M3U trovato")
        print(f"   Directory script:   {Path(__file__).parent.parent}")
        print(f"   Directory corrente: {Path.cwd()}")
        print("   Uso: python3 -m radioplayer [file.m3u]")
        return None

    if len(m3u_files) == 1:
        print(f"\U0001f4c2 File M3U trovato: {m3u_files[0]}")
        return m3u_files[0]

    print("\U0001f4c2 File M3U disponibili:")
    for i, f in enumerate(m3u_files, 1):
        print(f"   {i}. {f}")
    print()

    while True:
        try:
            raw = input(
                f"Scegli il file da usare (1-{len(m3u_files)}, q per uscire): "
            ).strip()
            if raw.lower() in ("q", "quit", "esc"):
                print("\U0001f44b Annullato")
                return None
            idx = int(raw) - 1
            if 0 <= idx < len(m3u_files):
                return m3u_files[idx]
            print(f"\u274c Inserisci un numero tra 1 e {len(m3u_files)}")
        except ValueError:
            print("\u274c Inserisci un numero valido")
        except (KeyboardInterrupt, EOFError):
            print("\n\U0001f44b Annullato")
            return None


def _list_stations(path: Path) -> int:
    """Stampa le stazioni della playlist senza avviare il player."""
    try:
        stations = M3UParser().parse_file(path)
    except Exception as exc:
        print(f"\u274c Impossibile leggere {path}: {exc}")
        return 1

    if not stations:
        print(f"\u274c Nessuna stazione trovata in {path}")
        return 1

    print(f"{'#':>4}  {'Gruppo':<16}  {'Nome':<40}  URL")
    for i, station in enumerate(stations, 1):
        group = (station.group or "Generale")[:16]
        name = station.name[:40]
        print(f"{i:>4}  {group:<16}  {name:<40}  {station.url}")
    print(f"\n{len(stations)} stazioni")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    """Funzione principale."""
    _configure_output()
    args = _build_parser().parse_args(argv)

    no_color = args.no_color or bool(os.environ.get("NO_COLOR"))
    volume = args.volume
    if volume is not None:
        volume = max(0, min(100, volume))

    print("=" * 70)
    print(f"Radio Player M3U v{__version__}")
    print("Copyright (C) 2025 Andres Zanzani <azanzani@gmail.com>")
    print("=" * 70)
    print()

    m3u_file = _resolve_m3u_file(
        args.file, force_choose=args.choose, use_last=args.last
    )
    if m3u_file is None:
        return 1

    if args.list:
        return _list_stations(m3u_file)

    try:
        from radioplayer.player import RadioPlayer

        player = RadioPlayer(
            audio_device=args.ao,
            color=not no_color,
            use_tray=not args.no_tray,
        )
        if volume is not None:
            player.state.volume = volume
        if args.debug:
            player.logging_enabled = True
            enable_file_logging(logger)
        ok = player.run(m3u_file)
        return 0 if ok else 1
    except ImportError as e:
        missing = str(e).replace("No module named ", "").strip("'")
        print(f"\u274c Dipendenza mancante: {missing}")
        print("   Installa con: pip install -r requirements.txt")
        return 1
    except Exception as e:
        logger.error(f"Errore fatale: {e}", exc_info=True)
        print(f"\u274c Errore: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
