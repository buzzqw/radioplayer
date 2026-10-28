"""Gestione configurazione persistente."""

import copy
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger("RadioPlayer")

DEFAULT_CONFIG: Dict[str, Any] = {
    "volume": 50,
    "show_song_popups": True,
    "logging_enabled": False,
    "last_m3u": None,
    "favorites": [],
    "favorites_only": False,
    "group_filter": None,
    "last_station": None,
    "eq_preset_idx": 0,
}

CONFIG_DIR = Path.home() / ".config" / "radioplayer"
CONFIG_FILE = CONFIG_DIR / "config.json"


def load_config() -> Dict[str, Any]:
    """Carica la configurazione da file JSON."""
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            config = copy.deepcopy(DEFAULT_CONFIG)
            if isinstance(data, dict):
                config.update(data)
            logger.info(f"Configurazione caricata da {CONFIG_FILE}")
            return config
        except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
            logger.warning(f"Errore lettura config: {e}")
    return copy.deepcopy(DEFAULT_CONFIG)


def save_config(config: Dict[str, Any]) -> None:
    """Salva la configurazione su file JSON in modo atomico."""
    tmp_path = None
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            dir=str(CONFIG_DIR), prefix=".config-", suffix=".tmp"
        )
        tmp_path = Path(tmp_name)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, CONFIG_FILE)
        logger.info(f"Configurazione salvata in {CONFIG_FILE}")
    except (OSError, TypeError) as e:
        logger.error(f"Errore salvataggio config: {e}")
        if tmp_path is not None:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
