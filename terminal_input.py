import configparser
import threading
from queue import Queue

EXIT_SIGNAL = "__EXIT__"

_SLASH_COMMANDS = {"/new", "/switch", "/list", "/perms", "/exit", "/help", "/clear", "/show", "/send", "/stop", "/export", "/import", "/delete", "/save", "/concat", "/to_top", "/load", "/rename", "/history"}


class TerminalInput:
    """從 stdin 讀取使用者輸入，區分純文字與斜線指令後分發至對應 Queue。"""

    def __init__(self, config: configparser.ConfigParser, cli_text_queue: Queue, cli_cmd_queue: Queue):
        self._cli_text_queue = cli_text_queue
        self._cli_cmd_queue = cli_cmd_queue
        self._thread: threading.Thread | None = None
        self._running = False

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="TerminalInput")
        self._thread.start()

    def stop(self):
        self._running = False

    def _loop(self):
        while self._running:
            try:
                line = input()
            except EOFError:
                self._cli_text_queue.put(EXIT_SIGNAL)
                break

            line = line.strip()
            if not line:
                continue

            if line.startswith("/"):
                parts = line.split()
                cmd = parts[0].lower()
                args = parts[1:]
                if cmd == "/exit":
                    self._cli_cmd_queue.put({"cmd": "/exit", "args": []})
                    self._cli_text_queue.put(EXIT_SIGNAL)
                    break
                elif cmd in _SLASH_COMMANDS:
                    self._cli_cmd_queue.put({"cmd": cmd, "args": args})
                else:
                    self._cli_cmd_queue.put({"cmd": "unknown", "args": [line]})
            else:
                self._cli_text_queue.put(line)
