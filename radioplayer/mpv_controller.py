"""Controller MPV: gestione processo e ciclo di vita."""

import logging
import os
import platform
import signal
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Dict, Any, Optional

from .mpv import MPVIPCClient

logger = logging.getLogger("RadioPlayer")


def get_socket_path() -> str:
    """Restituisce il path del socket IPC per MPV."""
    if platform.system() == "Windows":
        return r"\\.\pipe\radio_player_mpv"

    socket_dir = Path(tempfile.gettempdir()) / f"radioplayer_{os.getuid()}"
    socket_dir.mkdir(exist_ok=True, mode=0o700)
    return str(socket_dir / "mpv.sock")


class MPVController:
    """Gestisce il processo MPV e la comunicazione IPC"""

    def __init__(self, socket_path: Optional[str] = None,
                 audio_device: Optional[str] = None):
        self.socket_path = socket_path or get_socket_path()
        self.audio_device = audio_device
        self.process: Optional[subprocess.Popen] = None
        self.ipc_client = MPVIPCClient(self.socket_path)
        logger.info(f"Inizializzato MPVController su {self.socket_path}")

    def start(self, url: str, volume: int = 50) -> bool:
        """Avvia MPV con lo stream"""
        try:
            self.ipc_client.close()
            if platform.system() != "Windows" and os.path.exists(self.socket_path):
                try:
                    os.remove(self.socket_path)
                except OSError:
                    pass
                logger.debug("Rimosso socket esistente")

            cmd = [
                'mpv',
                '--no-video',
                f'--volume={volume}',
                '--quiet',
                '--no-terminal',
                '--cache=yes',
                '--demuxer-max-bytes=8M',
                '--audio-buffer=0.5',
                f'--input-ipc-server={self.socket_path}',
            ]
            if self.audio_device:
                cmd.append(f'--ao={self.audio_device}')
            cmd.append(url)

            logger.info(f"Avvio MPV: {' '.join(cmd)}")

            kwargs = {}
            if platform.system() != "Windows":
                # start_new_session evita i rischi di preexec_fn in applicazioni
                # multithread (tray + input + monitor).
                kwargs["start_new_session"] = True

            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                **kwargs,
            )

            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    logger.error("MPV terminato durante l'avvio")
                    self.process = None
                    return False
                if platform.system() == "Windows":
                    time.sleep(0.2)
                    break
                if os.path.exists(self.socket_path):
                    break
                time.sleep(0.05)

            if self.process is not None and self.process.poll() is None:
                logger.info("MPV avviato con successo")
                return True

            logger.error("MPV terminato immediatamente")
            return False

        except Exception as e:
            logger.error(f"Errore avvio MPV: {e}", exc_info=True)
            return False

    def stop(self):
        """Ferma MPV"""
        if not self.process:
            self.ipc_client.close()
            return

        try:
            logger.info("Fermata MPV")
            if platform.system() == "Windows":
                self.process.terminate()
                self.process.wait(timeout=2)
            else:
                os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    pass
        except subprocess.TimeoutExpired:
            logger.warning("MPV non risponde, force kill")
            try:
                if platform.system() == "Windows":
                    self.process.kill()
                else:
                    os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass
        except ProcessLookupError:
            logger.warning("Processo MPV gia' terminato")
        except Exception as e:
            logger.error(f"Errore stop MPV: {e}")
        finally:
            self.ipc_client.close()
            self.process = None

            if platform.system() != "Windows" and os.path.exists(self.socket_path):
                try:
                    os.remove(self.socket_path)
                except OSError:
                    pass

    def is_running(self) -> bool:
        """Verifica se MPV e' in esecuzione"""
        return self.process is not None and self.process.poll() is None

    def set_volume(self, volume: int) -> bool:
        """Imposta il volume"""
        return self.ipc_client.set_property("volume", volume)

    def set_mute(self, muted: bool) -> bool:
        """Imposta muto"""
        return self.ipc_client.set_property("mute", muted)

    def set_pause(self, paused: bool) -> bool:
        """Mette in pausa/riprende MPV (non solo muto)."""
        return self.ipc_client.set_property("pause", paused)

    def get_audio_stats(self) -> Dict[str, Any]:
        """Ottiene statistiche audio."""
        stats = {}

        bitrate = self.ipc_client.get_property("audio-bitrate")
        if bitrate:
            stats['bitrate'] = f"{int(bitrate / 1000)} kbps"

        codec = self.ipc_client.get_property("audio-codec-name")
        if codec:
            stats['codec'] = str(codec).upper()

        cache = self.ipc_client.get_property("demuxer-cache-duration")
        if cache:
            stats['cache'] = f"{cache:.1f}s"

        buffering = self.ipc_client.get_property("paused-for-cache")
        if buffering:
            stats['buffer_status'] = "BUFFERING"
        else:
            cache_percent = self.ipc_client.get_property("cache-buffering-state")
            if cache_percent is not None:
                stats['buffer_status'] = f"{cache_percent}%"
            else:
                stats['buffer_status'] = "OK"

        return stats
