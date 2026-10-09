# 使用手冊：啟動、熱鍵與工作區

[使用手冊入口](../user_manual.md)

## 3. 啟動

```bash
# 桌面 TUI 模式（一般使用）
python main.py

# 使用現有 .venv 啟動
uv run app.py

# 手機 Web 模式
python mobile_server.py
```

啟動後狀態列顯示「待機」就代表就緒了。在 KDE Wayland 上看到
「Wayland 本機控制已啟用」代表程式端的快捷鍵控制 socket 已建立。

---

## 4. 熱鍵

| 鍵 | 功能 |
|---|---|
| **Alt+F8**（KDE）／**F8**（X11） | 錄音開關：按一下開始、再按一下停止並辨識，文字進**當前工作區** |
| **F7** | 語音指令模式：說的話被解析成指令（說「發送」就等於 `/send`） |
| **Alt+F9**（KDE）／**F9**（X11） | 快速發送：等同 `/send`，當前工作區須為 buffer |
| **F10** | 強制停止 TTS：中斷正在朗讀的回覆 |
| **F6** | 重播：用 TTS 朗讀最後一次 LLM 回覆的原文 |

錄音期間每次停頓（預設靜音 1.5 秒）就會切出一段即時辨識並寫入工作區，不必等按停止；
停止時只處理最後一段。辨識完成後狀態列回「待機」，失敗會顯示 `[STT 錯誤] …`。

鍵位可以在 `config.ini` 的 `[CONTROL]` 區自訂，例如：

```ini
[CONTROL]
key_record_toggle = f8
key_command_toggle = f7
key_quick_send = f9
key_force_stop_tts = f10
key_play_last_original = f6
```

> **注意**：`key_command_toggle` 預設值是 f7，但 `config.ini` 預設沒有這行。
> 如果你要改 F7 的鍵位，手動加這行再改。

> **KDE Wayland 注意**：`config.ini` 只影響 `pynput` 路徑，不會自動修改 KDE
> 的快捷鍵。目前 KDE 已註冊 Alt+F8／Alt+F9；要增加 F7/F10，需建立對應的 KDE
> 快捷鍵動作，詳見 [KDE Wayland 全域快捷鍵](../kde_wayland_shortcuts.md)。

---

## 5. 工作區

系統有三個工作區，操作都作用在「**當前工作區**」：

| 工作區 | 用途 | 特性 |
|---|---|---|
| `buffer` | 待發送的訊息暫存 | 預設當前；只有它能 `/send` |
| `stt` | 第二個文字暫存 | 可自由讀寫、匯出 |
| `chat` | 對話歷史唯讀 | 只能 `/history` 看、`/clear chat` 清 |

切換工作區：

```
/ws          ← 列出所有工作區（標示當前）
/ws stt      ← 切換到 stt
/ws buffer   ← 切回 buffer
```

> **重要**：語音辨識出的文字**只進當前工作區**。想把語音收進 stt，先 `/ws stt`，
> 再按 Alt+F8（KDE）或 F8（X11）錄音。
