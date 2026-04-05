import configparser
from queue import Queue
from pynput.keyboard import Key, Listener


class KeyboardListener:
    """全域鍵盤監聽器，將按鍵事件轉譯為訊號並放入 key_signal_queue。"""

    def __init__(self, config: configparser.ConfigParser, key_signal_queue: Queue):
        self._key_signal_queue = key_signal_queue
        ctrl = config["CONTROL"]
        self._key_record = ctrl.get("key_record_toggle", "f8").lower()
        self._key_command = ctrl.get("key_command_toggle", "f7").lower()
        self._key_quick_send = ctrl.get("key_quick_send", "f9").lower()
        self._key_force_stop_tts = ctrl.get("key_force_stop_tts", "f10").lower()
        self._key_play_last_original = ctrl.get("key_play_last_original", "f6").lower()
        self._listener: Listener | None = None

    def start(self):
        self._listener = Listener(on_press=self._on_press)
        self._listener.daemon = True
        self._listener.start()

    def stop(self):
        if self._listener:
            self._listener.stop()

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
