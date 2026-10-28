"""Sistema di logging per Radio Player."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional


def setup_logging(log_file: Optional[Path] = None,
                  level: int = logging.INFO) -> logging.Logger:
    """Configura il sistema di logging con rotazione file.

    Il RotatingFileHandler viene creato subito ma con livello CRITICAL+1
    (spento), e viene attivato a runtime con handler.setLevel().
    """

    if log_file is None:
        config_dir = Path.home() / ".config" / "radioplayer"
        config_dir.mkdir(parents=True, exist_ok=True)
        log_file = config_dir / "radioplayer.log"

    logger = logging.getLogger("RadioPlayer")
    logger.setLevel(level)

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
    )

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.ERROR)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding='utf-8',
    )
    file_handler.setLevel(logging.CRITICAL + 1)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


def enable_file_logging(logger: logging.Logger) -> None:
    """Attiva il logging su file."""
    for handler in logger.handlers:
        if isinstance(handler, RotatingFileHandler):
            handler.setLevel(logging.DEBUG)


def disable_file_logging(logger: logging.Logger) -> None:
    """Disattiva il logging su file."""
    for handler in logger.handlers:
        if isinstance(handler, RotatingFileHandler):
            handler.setLevel(logging.CRITICAL + 1)


def set_console_logging(enabled: bool) -> None:
    """Abilita/disabilita l'output su console.

    Con la UI Rich attiva, un log su stderr corromperebbe lo schermo: in quel
    caso gli errori restano nel file di log e vengono mostrati nell'UI.
    """
    logger = logging.getLogger("RadioPlayer")
    for handler in logger.handlers:
        if isinstance(handler, RotatingFileHandler):
            continue
        if isinstance(handler, logging.StreamHandler):
            handler.setLevel(logging.ERROR if enabled else logging.CRITICAL + 1)
