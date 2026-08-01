#!/usr/bin/env python3
"""
Radio Player M3U - Launcher
Avvio:  python radioplayer.py [file.m3u]
"""

import sys
from pathlib import Path

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent))

    try:
        from radioplayer.__main__ import main
    except ImportError as e:
        missing = str(e).replace("No module named ", "").strip("'")
        print("\U0001f3b5 Radio Player M3U")
        print(f"\u274c Dipendenza mancante: {missing}")
        print()
        print("   Installa le dipendenze con:")
        print("       pip install -r requirements.txt")
        print("   oppure:")
        print("       pip install rich requests pystray Pillow")
        sys.exit(1)

    main()
