"""對話管理指令處理。"""


class SessionCommandMixin:
    """提供 SessionManager 相關指令；由 CommandRouter 組合使用。"""

    def _handle_new(self, args: list) -> None:
        """建立新對話；無標題時使用 session_N 格式。"""
        title = " ".join(args) if args else f"session_{len(self._sm.list_sessions()) + 1}"
        self._sm.new_session(title)
        self._ui_msg(f"新建對話: {title}")

    def _handle_switch(self, args: list) -> None:
        """切換對話；無參數預設 default，default 不存在則建立。"""
        title = " ".join(args) if args else "default"
        if self._sm.switch_session(title):
            self._ui_msg(f"切換至: {title}")
        elif not args and title == "default":
            self._sm.new_session("default")
            self._ui_msg("建立並切換至: default")
        else:
            self._ui_msg(f"找不到對話: {title}")

    def _handle_list(self) -> None:
        """列出所有對話並標示當前。"""
        sessions = self._sm.list_sessions()
        current = self._sm.current_title or "無"
        text = "對話列表:\n" + "\n".join(f"  - {s}" for s in sessions)
        text += f"\n\n當前使用session：{current}"
        self._ui_msg(text)

    def _handle_delete(self, args: list) -> None:
        """刪除指定對話。"""
        title = " ".join(args)
        if not title:
            self._ui_msg("用法: /delete [對話名稱]")
            return
        _success, msg = self._sm.delete_session(title)
        self._ui_msg(msg)

    def _handle_rename(self, args: list) -> None:
        """更改對話名稱。"""
        if len(args) < 2:
            self._ui_msg("用法: /rename [舊名稱] [新名稱]")
            return
        old_t, new_t = args[0], args[1]
        _success, msg = self._sm.rename_session(old_t, new_t)
        self._ui_msg(msg)

    def _handle_history(self) -> None:
        """顯示當前對話的歷史紀錄。"""
        history = self._sm.get_history()
        self._ui_msg(history)

    def _handle_save(self, args: list) -> None:
        """將當前對話另存為 JSON 檔案。"""
        filename = " ".join(args) if args else None
        _success, msg = self._sm.save_session_to_file(filename)
        self._ui_msg(msg)

    def _handle_load(self, args: list) -> None:
        """從 JSON 檔案載入對話。"""
        if not args:
            self._ui_msg("用法: /load [檔名]")
            return
        filename = " ".join(args)
        _success, msg = self._sm.load_session_from_file(filename)
        self._ui_msg(msg)

    def _handle_help(self) -> None:
        """顯示所有可用指令說明。"""
        help_text = (
            "/new [title]  /switch [title]  /list  /delete [title]  /save [file]  "
            "/load [file]  /rename [old] [new]  /history  /ws [name]  /show  "
            "/clear [ui|stt|buffer|chat]  /copy  /paste  /del <i>  /move <i> <j>  "
            "/to_top [i]  /concat  /send  /export  /import  /stop  /help  /exit"
        )
        self._ui_msg(help_text)
