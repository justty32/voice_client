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

from protocol.commands import HOTKEY_SIGNALS

log = logging.getLogger(__name__)

# 白名單＝熱鍵五訊號，單一來源在 protocol/commands.py。
ALLOWED_COMMANDS = HOTKEY_SIGNALS


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
            # stop() 可能在另一執行緒把 _socket 設為 None；先取區域參照，None 即視為已停機（B9）
            sock = self._socket
            if sock is None:
                break
            try:
                data = sock.recv(128)
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


def main(argv: list[str] | None = None) -> int:
    """命令列入口：送出一個白名單命令，回傳 exit code（根層 local_control.py shim 呼叫此函式）。"""
    argv = sys.argv if argv is None else argv
    if len(argv) != 2:
        print(f"Usage: {argv[0]} COMMAND", file=sys.stderr)
        return 2
    return send_command(argv[1])


if __name__ == "__main__":
    raise SystemExit(main())
