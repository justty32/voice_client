"""Local IPC control for desktop-global shortcuts.

The running Voice Client listens on a per-user Unix datagram socket. Small
helper invocations send one allow-listed command to that socket and exit.
This lets a Wayland compositor own the global shortcut while keeping command
handling inside Voice Client.
"""

from __future__ import annotations

import logging
import os
import socket
import sys
import threading
import time
from pathlib import Path
from queue import Queue

log = logging.getLogger(__name__)

ALLOWED_COMMANDS = frozenset(
    {
        "RECORD_TOGGLE",
        "RECORD_COMMAND_TOGGLE",
        "QUICK_SEND",
        "FORCE_STOP_TTS",
        "PLAY_LAST_ORIGINAL",
    }
)


def socket_path() -> Path:
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    base = Path(runtime_dir) if runtime_dir else Path(f"/tmp/voice-client-{os.getuid()}")
    return base / "voice-client-control.sock"


class LocalControl:
    """Receive local desktop commands and place them on the command queue."""

    def __init__(self, command_queue: Queue):
        self._command_queue = command_queue
        self._socket: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._path = socket_path()
        self._last_command = ""
        self._last_command_at = 0.0

    def start(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._path.unlink(missing_ok=True)
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
            sock.bind(str(self._path))
            os.chmod(self._path, 0o600)
            sock.settimeout(0.2)
        except OSError as exc:
            log.warning("本機快捷鍵控制啟動失敗：%s", exc)
            return

        self._socket = sock
        self._running = True
        self._thread = threading.Thread(
            target=self._loop,
            daemon=True,
            name="LocalControl",
        )
        self._thread.start()
        log.info("本機快捷鍵控制已啟用：%s", self._path)

    def stop(self) -> None:
        self._running = False
        if self._socket is not None:
            self._socket.close()
            self._socket = None
        if self._thread is not None:
            self._thread.join(timeout=0.5)
            self._thread = None
        self._path.unlink(missing_ok=True)

    def is_active(self) -> bool:
        return self._socket is not None

    def _loop(self) -> None:
        while self._running:
            try:
                assert self._socket is not None
                data = self._socket.recv(128)
            except socket.timeout:
                continue
            except OSError:
                break

            command = data.decode("ascii", errors="ignore").strip()
            if command in ALLOWED_COMMANDS:
                now = time.monotonic()
                if command == self._last_command and now - self._last_command_at < 0.5:
                    log.debug("忽略重複的本機控制命令：%s", command)
                    continue
                self._last_command = command
                self._last_command_at = now
                log.info("收到本機控制命令：%s", command)
                self._command_queue.put(command)
            else:
                log.warning("忽略不允許的本機控制命令：%r", command)


def send_command(command: str) -> int:
    if command not in ALLOWED_COMMANDS:
        print(f"Unsupported Voice Client command: {command}", file=sys.stderr)
        return 2

    path = socket_path()
    if not path.exists():
        print("Voice Client is not running.", file=sys.stderr)
        return 1

    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
            sock.sendto(command.encode("ascii"), str(path))
    except OSError as exc:
        print(f"Could not contact Voice Client: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} COMMAND", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(send_command(sys.argv[1]))
