"""Gestione configurazione persistente."""

import json
import logging
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger("RadioPlayer")

DEFAULT_CONFIG: Dict[str, Any] = {
    "volume": 50,
    "show_song_popups": True,
    "logging_enabled": False,
    "last_m3u": None,
    "favorites": [],
    "group_filter": None,
    "eq_preset_idx": 0,
}

CONFIG_DIR = Path.home() / ".config" / "radioplayer"
CONFIG_FILE = CONFIG_DIR / "config.json"


def load_config() -> Dict[str, Any]:
    """Carica la configurazione da file JSON."""
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            config = DEFAULT_CONFIG.copy()
            config.update(data)
            logger.info(f"Configurazione caricata da {CONFIG_FILE}")
            return config
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Errore lettura config: {e}")
    return DEFAULT_CONFIG.copy()


def save_config(config: Dict[str, Any]) -> None:
    """Salva la configurazione su file JSON."""
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(
            json.dumps(config, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info(f"Configurazione salvata in {CONFIG_FILE}")
    except (OSError, TypeError) as e:
        logger.error(f"Errore salvataggio config: {e}")
