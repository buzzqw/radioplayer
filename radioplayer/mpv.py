"""Client IPC MPV per comunicazione via socket/named-pipe."""

import json
import logging
import os
import platform
import socket
import threading
import time
from typing import Any, Optional

logger = logging.getLogger("RadioPlayer")


class MPVIPCClient:
    """Client IPC per comunicare con MPV tramite socket.

    Su Unix mantiene una connessione persistente: aprire un socket per ogni
    proprieta' (come nella versione precedente) costa decine di connessioni al
    minuto durante il polling delle statistiche.
    """

    def __init__(self, socket_path: str):
        self.socket_path = socket_path
        self._request_id = 0
        self._lock = threading.Lock()
        self._sock: Optional[socket.socket] = None
        self._file: Optional[Any] = None
        logger.info(f"Inizializzato MPV IPC client: {socket_path}")

    @property
    def _is_windows(self) -> bool:
        return platform.system() == "Windows"

    def _close_unix(self) -> None:
        file_obj, sock = self._file, self._sock
        self._file = None
        self._sock = None
        for obj in (file_obj, sock):
            if obj is not None:
                try:
                    obj.close()
                except Exception:
                    pass

    def close(self) -> None:
        """Chiude la connessione persistente (se presente)."""
        with self._lock:
            self._close_unix()

    def _ensure_unix(self, timeout: float) -> bool:
        if self._sock is not None:
            return True
        if not os.path.exists(self.socket_path):
            return False
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            sock.connect(self.socket_path)
        except Exception:
            sock.close()
            raise
        self._sock = sock
        self._file = sock.makefile("rwb")
        return True

    def send_command(self, command: str, *args, timeout: float = 2.0) -> Optional[Any]:
        """Invia un comando a MPV e restituisce il campo data."""
        success, data = self._dispatch(command, args, timeout)
        return data if success else None

    def send_command_ok(self, command: str, *args, timeout: float = 2.0) -> bool:
        """Invia un comando e restituisce True se MPV lo ha accettato."""
        success, _ = self._dispatch(command, args, timeout)
        return success

    def _dispatch(self, command: str, args: tuple, timeout: float):
        with self._lock:
            self._request_id += 1
            request = {
                "command": [command, *args],
                "request_id": self._request_id,
            }

            logger.debug(f"IPC send: {request}")

            try:
                if self._is_windows:
                    return self._send_windows(request, timeout)
                return self._send_unix(request, timeout)
            except Exception as e:
                logger.error(f"Errore IPC command '{command}': {e}")
                self._close_unix()
                return False, None

    def _send_unix(self, request: dict, timeout: float):
        """Invia comando su Unix socket, riconnettendosi se necessario."""
        for attempt in range(2):
            try:
                if not self._ensure_unix(timeout):
                    logger.warning(f"Socket non esiste: {self.socket_path}")
                    return False, None

                assert self._file is not None
                assert self._sock is not None
                self._file.write((json.dumps(request) + "\n").encode("utf-8"))
                self._file.flush()

                deadline = time.monotonic() + timeout
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise socket.timeout()
                    self._sock.settimeout(remaining)
                    line = self._file.readline()
                    if not line:
                        raise ConnectionError("socket chiuso da mpv")

                    try:
                        response = json.loads(line.decode("utf-8").strip())
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        continue

                    logger.debug(f"IPC response: {response}")

                    if response.get("request_id") != request["request_id"]:
                        # Evento asincrono di mpv: ignoralo.
                        continue

                    if response.get("error") == "success":
                        return True, response.get("data")
                    logger.warning(f"IPC error: {response.get('error')}")
                    return False, None

            except (socket.timeout, ConnectionError, OSError) as e:
                self._close_unix()
                if attempt == 0:
                    logger.debug(f"IPC riconnessione dopo errore: {e}")
                    continue
                logger.warning(f"IPC errore su '{request['command'][0]}': {e}")
                return False, None
            except Exception as e:
                self._close_unix()
                logger.error(f"Errore IPC Unix: {e}")
                return False, None

        return False, None

    def _send_windows(self, request: dict, timeout: float):
        """Invia comando su Windows named pipe."""
        try:
            import pywintypes  # noqa: F401
            import win32file

            handle = win32file.CreateFile(
                self.socket_path,
                win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                0, None,
                win32file.OPEN_EXISTING,
                0, None
            )

            try:
                message = (json.dumps(request) + "\n").encode('utf-8')
                win32file.WriteFile(handle, message)

                _result, data = win32file.ReadFile(handle, 4096)
            finally:
                win32file.CloseHandle(handle)

            if data:
                for line in data.decode("utf-8", errors="ignore").split("\n"):
                    if not line.strip():
                        continue
                    try:
                        response = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if response.get("request_id") != request["request_id"]:
                        continue
                    if response.get("error") == "success":
                        return True, response.get("data")
                    logger.warning(f"IPC error: {response.get('error')}")
                    return False, None

            return False, None

        except ImportError:
            logger.error("win32file non disponibile per IPC Windows")
            return False, None
        except Exception as e:
            logger.error(f"Errore IPC Windows: {e}")
            return False, None

    def get_property(self, property_name: str) -> Optional[Any]:
        """Ottiene una proprieta' da MPV"""
        return self.send_command("get_property", property_name)

    def set_property(self, property_name: str, value: Any) -> bool:
        """Imposta una proprieta' in MPV"""
        return self.send_command_ok("set_property", property_name, value)
