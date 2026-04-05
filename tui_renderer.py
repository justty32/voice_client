import configparser
import threading
from dataclasses import dataclass, field
from queue import Empty, Queue
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.text import Text


@dataclass
class UiEvent:
    event_type: str  # message | status | progress | tts_playing
    data: Any = field(default=None)


class TuiRenderer:
    """TUI 渲染層。回歸標準滾動輸出，保持最簡潔的 CLI 體驗。"""

    def __init__(self, config: configparser.ConfigParser, ui_event_queue: Queue):
        self._ui_event_queue = ui_event_queue
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
        if event.event_type == "message":
            self._on_message(event.data)
        elif event.event_type == "status":
            self._on_status(event.data)
        # Ignore volume events

    # ── Renderers ──────────────────────────────────────────────────────

    def _on_message(self, data: dict):
        role = data.get("role", "system")
        text = data.get("text", "")
        
        if role == "user":
            p = Panel(text, title="[bold cyan]You[/bold cyan]", border_style="cyan", expand=False)
        elif role == "voice":
            p = Panel(text, title="[bold magenta]🎙 Voice[/bold magenta]", border_style="magenta", expand=False)
        elif role == "assistant":
            p = Panel(text, title="[bold green]AI[/bold green]", border_style="green", expand=False)
        elif role == "sending":
            p = Text(f"📤 {text}", style="bold blue")
        elif role == "summary":
            p = Panel(text, title="[bold yellow]💡 Summary[/bold yellow]", border_style="yellow", expand=False)
        elif role == "system":
            p = Panel(text, title="[bold magenta]⌘ Command[/bold magenta]", border_style="magenta", expand=False)
        else:
            p = Text(text, style="dim italic")
        
        self._console.print(p)
        self._console.print()

    def _on_status(self, status: str):
        # 僅在狀態變更時打印簡潔的圖標
        icons = {
            "待機": "[grey50]●[/grey50]",
            "錄音中": "[bold red]◉[/bold red]",
            "語音指令中": "[bold magenta]⌘[/bold magenta]",
            "處理中": "[bold yellow]◌[/bold yellow]",
            "傳送中": "[bold blue]◈[/bold blue]",
        }
        icon = icons.get(status, "[grey50]●[/grey50]")
        # 為了保持底部簡潔，我們只打印狀態縮圖，不佔用固定行
        self._console.print(f"{icon} [dim]{status}[/dim]")
