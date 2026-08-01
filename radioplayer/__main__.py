"""Entry point for Radio Player M3U."""

import sys
from pathlib import Path

if sys.version_info < (3, 8):
    sys.exit("Python 3.8+ richiesto")

from radioplayer.player import RadioPlayer
from radioplayer.logging_setup import setup_logging

logger = setup_logging()


def find_m3u_files():
    """Cerca file M3U nella directory dello script e nella directory corrente"""
    found = {}
    try:
        script_dir = Path(__file__).parent.parent.resolve()
    except Exception:
        script_dir = Path.cwd()
    for directory in (script_dir, Path.cwd()):
        for f in sorted(directory.glob('*.m3u')):
            found[f.resolve()] = f
    return list(found.values())


def main():
    """Funzione principale"""
    print("=" * 70)
    print("Radio Player M3U v3.0")
    print("Copyright (C) 2025 Andres Zanzani <azanzani@gmail.com>")
    print("=" * 70)
    print()

    m3u_file = None
    if len(sys.argv) > 1:
        m3u_file = Path(sys.argv[1])
        if not m3u_file.exists():
            print(f"\u274c File non trovato: {m3u_file}")
            return
    else:
        m3u_files = find_m3u_files()
        if not m3u_files:
            print("\u274c Nessun file M3U trovato")
            print(f"   Directory script:   {Path(__file__).parent.parent}")
            print(f"   Directory corrente: {Path.cwd()}")
            print(f"Uso: python3 -m radioplayer [file.m3u]")
            return
        elif len(m3u_files) == 1:
            m3u_file = m3u_files[0]
            print(f"\U0001f4c2 File M3U trovato: {m3u_file}")
        else:
            print("\U0001f4c2 File M3U disponibili:")
            for i, f in enumerate(m3u_files, 1):
                print(f"   {i}. {f}")
            print()
            while True:
                try:
                    raw = input(f"Scegli il file da usare (1-{len(m3u_files)}): ").strip()
                    idx = int(raw) - 1
                    if 0 <= idx < len(m3u_files):
                        m3u_file = m3u_files[idx]
                        break
                    print(f"\u274c Inserisci un numero tra 1 e {len(m3u_files)}")
                except ValueError:
                    print("\u274c Inserisci un numero valido")
                except (KeyboardInterrupt, EOFError):
                    print("\n\U0001f44b Annullato")
                    return

    try:
        player = RadioPlayer()
        player.run(m3u_file)
    except Exception as e:
        logger.error(f"Errore fatale: {e}", exc_info=True)
        print(f"\u274c Errore: {e}")


if __name__ == "__main__":
    main()
