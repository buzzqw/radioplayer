"""Tests for the persistent MPV IPC client."""

import json
import socket
import threading

from radioplayer.mpv import MPVIPCClient


class FakeMPVServer:
    def __init__(self, path):
        self.path = str(path)
        self.connections = 0
        self.commands = []
        self._stop = threading.Event()
        self._server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server.bind(self.path)
        self._server.listen(4)
        self._server.settimeout(0.2)
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        while not self._stop.is_set():
            try:
                conn, _ = self._server.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            self.connections += 1
            with conn:
                file_obj = conn.makefile("rwb")
                while not self._stop.is_set():
                    line = file_obj.readline()
                    if not line:
                        break
                    request = json.loads(line.decode("utf-8"))
                    self.commands.append(request)
                    command = request["command"][0]
                    data = 42 if command == "get_property" else None
                    response = {
                        "request_id": request["request_id"],
                        "error": "success",
                        "data": data,
                    }
                    file_obj.write((json.dumps(response) + "\n").encode("utf-8"))
                    file_obj.flush()

    def close(self):
        self._stop.set()
        try:
            self._server.close()
        except OSError:
            pass
        self._thread.join(timeout=1)


def test_ipc_reuses_connection_and_reports_success(tmp_path):
    server = FakeMPVServer(tmp_path / "mpv.sock")
    client = MPVIPCClient(server.path)
    try:
        assert client.get_property("volume") == 42
        assert client.get_property("volume") == 42
        assert client.set_property("pause", True) is True
        assert server.connections == 1
        assert len(server.commands) == 3
    finally:
        client.close()
        server.close()


def test_ipc_handles_missing_socket(tmp_path):
    client = MPVIPCClient(str(tmp_path / "missing.sock"))
    assert client.get_property("volume") is None
    assert client.set_property("pause", True) is False
