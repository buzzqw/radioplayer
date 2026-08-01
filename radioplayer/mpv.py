"""Client IPC MPV per comunicazione via socket/named-pipe."""

import json
import logging
import os
import socket
import platform
from typing import Any, Optional

logger = logging.getLogger("RadioPlayer")


class MPVIPCClient:
    """Client IPC per comunicare con MPV tramite socket"""

    def __init__(self, socket_path: str):
        self.socket_path = socket_path
        self._request_id = 0
        logger.info(f"Inizializzato MPV IPC client: {socket_path}")

    def send_command(self, command: str, *args, timeout: float = 2.0) -> Optional[Any]:
        """Invia un comando a MPV e attende la risposta"""
        self._request_id += 1
        request = {
            "command": [command, *args],
            "request_id": self._request_id
        }

        logger.debug(f"IPC send: {request}")

        try:
            if platform.system() == "Windows":
                return self._send_windows(request, timeout)
            else:
                return self._send_unix(request, timeout)
        except Exception as e:
            logger.error(f"Errore IPC command '{command}': {e}")
            return None

    def _send_unix(self, request: dict, timeout: float) -> Optional[Any]:
        """Invia comando su Unix socket"""
        if not os.path.exists(self.socket_path):
            logger.warning(f"Socket non esiste: {self.socket_path}")
            return None

        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(timeout)
                sock.connect(self.socket_path)
                sock.sendall((json.dumps(request) + "\n").encode('utf-8'))

                buffer = b""
                while True:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    buffer += chunk
                    if b"\n" in buffer:
                        break

                if buffer:
                    # mpv puo' inviare piu' oggetti JSON (risposta + eventi)
                    # separati da newline. Parsiamo tutte le righe e cerchiamo
                    # quella con il request_id che abbiamo inviato.
                    for line in buffer.decode('utf-8').split("\n"):
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            response = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        logger.debug(f"IPC response: {response}")

                        if response.get("request_id") == self._request_id:
                            if response.get("error") == "success":
                                return response.get("data")
                            else:
                                logger.warning(f"IPC error: {response.get('error')}")
                            return None

                return None

        except socket.timeout:
            logger.warning(f"IPC timeout per comando: {request['command'][0]}")
            return None
        except (ConnectionRefusedError, FileNotFoundError) as e:
            logger.warning(f"IPC Unix connection error: {e}")
            return None
        except Exception as e:
            logger.error(f"Errore IPC Unix: {e}")
            return None

    def _send_windows(self, request: dict, timeout: float) -> Optional[Any]:
        """Invia comando su Windows named pipe"""
        try:
            import win32file
            import win32pipe
            import pywintypes

            handle = win32file.CreateFile(
                self.socket_path,
                win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                0, None,
                win32file.OPEN_EXISTING,
                0, None
            )

            message = (json.dumps(request) + "\n").encode('utf-8')
            win32file.WriteFile(handle, message)

            result, data = win32file.ReadFile(handle, 4096)
            win32file.CloseHandle(handle)

            if data:
                response = json.loads(data.decode('utf-8').strip())
                logger.debug(f"IPC response: {response}")

                if response.get("error") == "success":
                    return response.get("data")

            return None

        except ImportError:
            logger.error("win32file non disponibile per IPC Windows")
            return None
        except Exception as e:
            logger.error(f"Errore IPC Windows: {e}")
            return None

    def get_property(self, property_name: str) -> Optional[Any]:
        """Ottiene una proprieta' da MPV"""
        return self.send_command("get_property", property_name)

    def set_property(self, property_name: str, value: Any) -> bool:
        """Imposta una proprieta' in MPV"""
        result = self.send_command("set_property", property_name, value)
        return result is not None
