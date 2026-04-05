import configparser
import threading
from dataclasses import dataclass, field
from queue import Empty, Queue
from typing import Any

from rich.console import Console


@dataclass
class UiEvent:
    event_type: str  # message | status | approval_request | progress | tts_playing
    data: Any = field(default=None)


class TuiRenderer:
    """TUI 渲染層。從 ui_event_queue 取事件並渲染，授權請求結果放入 approval_result_queue。"""

    def __init__(self, config: configparser.ConfigParser, ui_event_queue: Queue, approval_result_queue: Queue):
        self._ui_event_queue = ui_event_queue
        self._approval_result_queue = approval_result_queue
        self._console = Console()
        self._thread: threading.Thread | None = None
        self._running = False

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._event_loop, daemon=True, name="TuiRenderer")
        self._thread.start()

    def stop(self):
        self._running = False

    # ── Event loop ─────────────────────────────────────────────────────

    def _event_loop(self):
        while self._running:
            try:
                event: UiEvent = self._ui_event_queue.get(timeout=0.1)
                self._handle(event)
            except Empty:
                continue

    def _handle(self, event: UiEvent):
        handlers = {
            "message": self._on_message,
            "status": self._on_status,
            "approval_request": self._on_approval,
            "progress": self._on_progress,
            "tts_playing": self._on_tts_playing,
        }
        handler = handlers.get(event.event_type)
        if handler:
            handler(event.data)

    # ── Renderers ──────────────────────────────────────────────────────

    def _on_message(self, data: dict):
        role = data.get("role", "system")
        text = data.get("text", "")
        if role == "user":
            self._console.print(f"[bold cyan]You:[/bold cyan] {text}")
        elif role == "voice":
            self._console.print(f"[bold magenta]🎙 Voice:[/bold magenta] {text}")
        elif role == "assistant":
            self._console.print(f"[bold green]AI:[/bold green] {text}")
        elif role == "sending":
            self._console.print(f"[bold blue]📤 {text}[/bold blue]")
        elif role == "summary":
            self._console.print(f"[bold yellow]💡 {text}[/bold yellow]")
        else:
            self._console.print(f"[dim italic]{text}[/dim italic]")

    def _on_status(self, status: str):
        icons = {
            "待機": "[grey50]●[/grey50]",
            "錄音中": "[bold red]◉[/bold red]",
            "處理中": "[bold yellow]◌[/bold yellow]",
            "傳送中": "[bold blue]◈[/bold blue]",
            "靜音": "[grey50]◯[/grey50]",
        }
        icon = icons.get(status, "[grey50]●[/grey50]")
        self._console.print(f"{icon} [dim]{status}[/dim]")

    def _on_progress(self, data: dict):
        self._console.print(f"[dim]  ⋯ {data.get('text', '')}[/dim]")

    def _on_tts_playing(self, data: dict):
        pass  # TODO: update status bar indicator

    def _on_approval(self, data: dict):
        request_id = data.get("request_id", "")
        description = data.get("description", "授權請求")
        action = data.get("action", "")

        self._console.print(f"\n[bold red]⚠ 授權請求[/bold red]: {description}")
        self._console.print("  [1] 允許本次  [2] 永久允許  [3] 拒絕  （逾時自動拒絕）")

        try:
            choice = input("選擇 [1/2/3]: ").strip()
        except (EOFError, KeyboardInterrupt):
            choice = "3"

        result_map = {"1": "approved_once", "2": "approved_always", "3": "rejected"}
        result = result_map.get(choice, "rejected")

        self._approval_result_queue.put({
            "request_id": request_id,
            "action": action,
            "result": result,
        })
