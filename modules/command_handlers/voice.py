"""語音指令關鍵字解析。"""


class VoiceCommandMixin:
    """把語音文字轉為既有 CommandRouter 指令。"""

    def _handle_voice(self, args: list) -> None:
        """依 legacy 優先順序解析語音指令後重新派發。"""
        raw_text = args[0] if args else ""
        self._ui_msg(f"[語音指令] {raw_text}")
        text = raw_text.lower().strip()

        if "new" in text or "新建" in text or "開啟對話" in text:
            parts = text.split()
            self._dispatch({"cmd": "/new", "args": parts[1:] if len(parts) > 1 else []})
        elif "switch" in text or "切換" in text:
            parts = text.split()
            self._dispatch({"cmd": "/switch", "args": parts[1:] if len(parts) > 1 else []})
        elif "list" in text or "列表" in text or "清單" in text:
            self._dispatch({"cmd": "/list", "args": []})
        elif "delete" in text or "刪除" in text:
            self._dispatch({"cmd": "/delete", "args": self._args_after(text, ("delete", "刪除"))})
        elif "save" in text or "保存" in text or "儲存" in text:
            self._dispatch({"cmd": "/save", "args": self._args_after(text, ("save", "保存", "儲存"))})
        elif "concat" in text or "壓縮" in text or "連接" in text:
            self._dispatch({"cmd": "/concat", "args": []})
        elif "to top" in text or "置頂" in text or "移至最前" in text:
            self._dispatch({"cmd": "/to_top", "args": []})
        elif "send" in text or "發送" in text or "傳送" in text:
            self._dispatch({"cmd": "/send", "args": []})
        elif "export" in text or "匯出" in text:
            self._dispatch({"cmd": "/export", "args": self._args_after(text, ("export", "匯出"))})
        elif "import" in text or "匯入" in text:
            self._dispatch({"cmd": "/import", "args": self._args_after(text, ("import", "匯入"))})
        elif "copy" in text or "複製" in text:
            self._dispatch({"cmd": "/copy", "args": []})
        elif "paste" in text or "貼上" in text:
            self._dispatch({"cmd": "/paste", "args": []})
        elif "stop" in text or "停止" in text:
            self._dispatch({"cmd": "/stop", "args": []})
        elif "show" in text or "顯示" in text:
            self._dispatch({"cmd": "/show", "args": []})
        elif "history" in text or "歷史" in text or "紀錄" in text or "記錄" in text:
            self._dispatch({"cmd": "/history", "args": []})
        elif "help" in text or "幫助" in text or "說明" in text or "指令" in text:
            self._dispatch({"cmd": "/help", "args": []})
        elif "工作區" in text or "workspace" in text:
            self._dispatch({"cmd": "/ws", "args": self._args_after(text, ("工作區", "workspace"))})
        elif "clear" in text or "清除" in text:
            if "buffer" in text or "暫存" in text:
                self._dispatch({"cmd": "/clear", "args": ["buffer"]})
            elif "畫面" in text or "螢幕" in text or "ui" in text or "screen" in text:
                self._dispatch({"cmd": "/clear", "args": ["ui"]})
            else:
                self._dispatch({"cmd": "/clear", "args": []})
        else:
            self._ui_msg(f"無法識別的語音指令: {text}")

    @staticmethod
    def _args_after(text: str, keywords: tuple[str, ...]) -> list[str]:
        """回傳第一個含關鍵字詞之後的詞，維持 legacy token 比對語意。"""
        parts = text.split()
        for i, part in enumerate(parts):
            if any(keyword in part for keyword in keywords):
                return parts[i + 1:]
        return []
