import configparser
import logging
import os
import sys
from queue import Queue

log = logging.getLogger(__name__)


def _hotkeys_supported() -> tuple[bool, str]:
    """回傳 (是否可啟用, 停用原因)。Linux 上 Wayland / headless 時回 False。"""
    if sys.platform in ("win32", "darwin"):
        return True, ""
    # Linux
    if os.environ.get("WAYLAND_DISPLAY"):
        return False, "Wayland 下 pynput 全域熱鍵不支援"
    if not os.environ.get("DISPLAY"):
        return False, "沒有 DISPLAY 環境變數（headless / SSH）"
    return True, ""


class KeyboardListener:
    """全域鍵盤監聽器，將按鍵事件轉譯為訊號並放入 key_signal_queue。

    Linux 上若環境不支援（Wayland / headless）或 pynput 啟動失敗，會靜默降級：
    `is_active()` 回 False，呼叫端應提示使用者改用 slash command。
    """

    def __init__(self, config: configparser.ConfigParser, key_signal_queue: Queue):
        self._key_signal_queue = key_signal_queue
        ctrl = config["CONTROL"]
        self._key_record = ctrl.get("key_record_toggle", "f8").lower()
        self._key_command = ctrl.get("key_command_toggle", "f7").lower()
        self._key_quick_send = ctrl.get("key_quick_send", "f9").lower()
        self._key_force_stop_tts = ctrl.get("key_force_stop_tts", "f10").lower()
        self._key_play_last_original = ctrl.get("key_play_last_original", "f6").lower()
        self._listener = None
        self._inactive_reason: str = ""

    def start(self):
        supported, reason = _hotkeys_supported()
        if not supported:
            self._inactive_reason = reason
            log.warning("全域熱鍵停用：%s。請改用 slash command（/send, /stop 等）。", reason)
            return
        try:
            from pynput.keyboard import Listener
            self._listener = Listener(on_press=self._on_press)
            self._listener.daemon = True
            self._listener.start()
        except Exception as exc:
            self._inactive_reason = f"pynput 啟動失敗：{exc}"
            log.warning("%s。改用 slash command。", self._inactive_reason)
            self._listener = None

    def stop(self):
        if self._listener:
            try:
                self._listener.stop()
            except Exception:
                pass

    def is_active(self) -> bool:
        return self._listener is not None

    def inactive_reason(self) -> str:
        return self._inactive_reason

    def _on_press(self, key):
        try:
            key_name = key.name if hasattr(key, "name") else (key.char or "")
            key_name = key_name.lower()
            if key_name == self._key_record:
                self._key_signal_queue.put("RECORD_TOGGLE")
            elif key_name == self._key_command:
                self._key_signal_queue.put("RECORD_COMMAND_TOGGLE")
            elif key_name == self._key_quick_send:
                self._key_signal_queue.put("QUICK_SEND")
            elif key_name == self._key_force_stop_tts:
                self._key_signal_queue.put("FORCE_STOP_TTS")
            elif key_name == self._key_play_last_original:
                self._key_signal_queue.put("PLAY_LAST_ORIGINAL")
        except Exception:
            pass
