# 資料隧道階段③：指令流 實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 指令流上隧道——熱鍵／終端斜線指令／語音指令一律作為 `commands` 生產者，由 CommandRouter（唯一消費者）統一處理；語音指令模式由 SttGate 分流實現。

**Architecture:**
- **SttGate**（新模組）：STT 轉接器改發 `stt_text`；SttGate 依模式分流——
  normal → `raw_text`（進當前工作區）、command → `commands`（`{"cmd":"voice","args":[text]}`）。
  模式由 CommandRouter 經 `gate_ctl` 切換。這實現了舊 main.py 的 `is_command_mode`，
  同時保住「raw_text 唯一消費者＝WorkspaceManager」的設計決策。
- **CommandRouter**（新模組）：消費 `commands`；持有 WorkspaceManager 與 SessionManager
  參照（同步呼叫）；對外生產 `recorder_ctl`、`tts_ctl`、`gate_ctl`、`outbound`、
  `ui_event`、`app_ctl`。熱鍵的舊字串訊號（"RECORD_TOGGLE"…）在 handle() 內正規化為
  指令 dict，keyboard_listener.py 零修改。
- 既有模組（terminal_input.py、keyboard_listener.py）零修改：其輸出 queue 日後（階段⑤）
  經 OutboxAdapter 掛上 `commands`；本階段以測試模擬。
- `main.py` 本階段不動。

**新增 topics:** `stt_text`（STT→SttGate）、`gate_ctl`（Router→SttGate）、`app_ctl`（/exit 等程式級控制，消費者在階段⑤接上）。

**Tech Stack:** core/ 框架、`workspace.Workspace`、`session_manager.SessionManager`、`utils.clipboard`、unittest。

**Port 來源（行為相容基準）:**
- `main.py:120-141`（熱鍵訊號）、`main.py:260-343`（`_route_cli_cmd`）、`main.py:392-483`（`_handle_voice_command`）
- `workspace_controller.py`（工作區指令語意）
- `text_accumulator.py`（/send 的 payload 組裝格式）＋ `main.py:186-204`（payload 補欄位）
- `http_client.py`（outbound payload 必須符合其消費格式）

---

## 檔案結構

```
modules/
  stt_gate.py          SttGate：stt_text 依模式分流 raw_text / commands
  command_router.py    CommandRouter：commands 唯一消費者
tests/
  test_stt_gate.py
  test_command_router_hotkeys.py
  test_command_router_workspace.py
  test_command_router_session.py
  test_command_router_voice.py
  test_command_flow_integration.py
```

**訊息格式（統一規格，所有任務必須遵守）：**

| topic | payload 格式 |
|---|---|
| `stt_text` | `str`（辨識文字） |
| `gate_ctl` | `{"mode": "normal"}` 或 `{"mode": "command"}` |
| `commands` | `{"cmd": "/xxx", "args": [...]}`；熱鍵舊字串（如 `"RECORD_TOGGLE"`）由 Router 正規化；語音指令為 `{"cmd": "voice", "args": [原始文字]}` |
| `recorder_ctl` | `"START"` / `"STOP"`（沿用 record.py 既有協定） |
| `tts_ctl` | `"STOP_SPEECH"`（沿用 text_to_voice.py 既有協定） |
| `ui_event` | `{"type": "message", "role": ..., "text": ...}`、`{"type": "status", "text": ...}`、`{"type": "clear"}` |
| `outbound` | 與 http_client.py 既有消費格式一致（含 `Content`、`Title`、`Metadata.ClientTime` 等，port 自 text_accumulator＋main.py 段落 F） |
| `app_ctl` | `"EXIT"` |

**工作區範圍註記：** 本階段 WorkspaceManager 僅有 buffer／stt；`/ws`、`/clear` 等指令
針對 chat 的分支回覆「chat 工作區於階段④接入」訊息，不報錯。

---

### Task 1: SttGate（語音指令模式分流）

**Files:** Create `modules/stt_gate.py`、`tests/test_stt_gate.py`

TDD。SttGate(TunnelModule)：`name="stt_gate"`、`consumes=("stt_text", "gate_ctl")`、初始 mode="normal"。

`handle()` 行為：
- `gate_ctl` 訊息 → 更新 mode（非法值忽略並 log warning，不拋例外）
- `stt_text` 訊息且 mode=normal → `emit("raw_text", text)`
- `stt_text` 訊息且 mode=command → `emit("commands", {"cmd": "voice", "args": [text]})`；
  **模式維持 command**（與舊 main.py 一致：直到下一次 record_toggle 才回 normal）
- 空白文字（`text.strip()` 為空）→ 不發任何訊息（port main.py:163 的過濾）

必要測試（≥6）：normal 分流、command 分流、模式切換、非法 gate_ctl 忽略、空白文字過濾、command 模式連續多筆仍走 commands。

Commit: `feat(階段③): SttGate — 語音指令模式分流（raw_text / commands）`

---

### Task 2: CommandRouter 骨架＋熱鍵指令

**Files:** Create `modules/command_router.py`、`tests/test_command_router_hotkeys.py`

TDD。CommandRouter(TunnelModule)：`name="command_router"`、`consumes=("commands",)`。
建構子：`CommandRouter(workspace_manager, session_manager, export_dir=".")`。
內部狀態：`_is_recording: bool = False`。

`handle()` 第一層：payload 為 `str`（舊熱鍵訊號）→ 正規化：
`"RECORD_TOGGLE"→{"cmd":"record_toggle"}`、`"RECORD_COMMAND_TOGGLE"→{"cmd":"record_command_toggle"}`、
`"QUICK_SEND"→{"cmd":"quick_send"}`、`"FORCE_STOP_TTS"→{"cmd":"force_stop_tts"}`、
`"PLAY_LAST_ORIGINAL"→{"cmd":"play_last"}`；未知字串 → ui_event 未知指令訊息。

熱鍵指令行為（port main.py:120-141）：
- `record_toggle`：翻轉 `_is_recording`；emit `recorder_ctl` "START"/"STOP"；
  開始錄音時 emit `gate_ctl` {"mode":"normal"}
- `record_command_toggle`：翻轉 `_is_recording`；emit `recorder_ctl` "START"/"STOP"；
  開始錄音時 emit `gate_ctl` {"mode":"command"}
- `quick_send`：等同 `/send`（本任務先 emit ui_event「buffer 為空」之類的訊息即可，
  /send 完整邏輯在 Task 3 落地後 quick_send 直接重用同一私有方法）
- `force_stop_tts`：emit `tts_ctl` "STOP_SPEECH"＋ui_event status "待機"
- `play_last`：本階段回 ui_event 訊息「重播功能於階段④接入」（last_response 屬聊天流狀態）

必要測試（≥6）：字串正規化、toggle 狀態機（兩次 toggle START→STOP）、F7 設 command 模式、F8 設 normal 模式、force_stop_tts 雙重輸出、未知指令 ui_event。

Commit: `feat(階段③): CommandRouter 骨架＋熱鍵指令（訊號正規化與錄音狀態機）`

---

### Task 3: CommandRouter 工作區指令

**Files:** Modify `modules/command_router.py`、Create `tests/test_command_router_workspace.py`

TDD。Port 自 `workspace_controller.py` 與 `main.py` 對應分支，語意必須相容：

- `/ws`（無參數）：列出工作區與筆數＋標示當前（buffer、stt；chat 顯示「（階段④接入）」）
- `/ws <name>`：`wm.switch()`；成功/失敗各自 ui_event 訊息
- `/show`：當前工作區 `lines()` 帶編號輸出；空工作區有對應訊息
- `/clear`：清當前工作區；`/clear ui` → ui_event {"type":"clear"}＋status 待機；
  `/clear buffer|stt` → 清指定；`/clear chat` → 「階段④接入」訊息
- `/del <i>`、`/move <i> <j>`、`/to_top [i]`、`/concat`：對當前工作區呼叫對應
  Workspace 方法；參數驗證訊息 port 自 workspace_controller（「用法: /del <編號>」等）
- `/copy`：`utils.clipboard.copy(當前工作區 flatten)`；`/paste`：`clipboard.paste()` 逐非空行
  append 至當前工作區（用 mock 測試，不碰真剪貼簿）
- `/export [file]`、`/import [file]`：當前工作區 `export()`／`import_file()`，
  檔名經 `workspace.resolve_filename(filename, export_dir)`
- `/send` 與 `quick_send`：僅 `wm.current == "buffer"` 有效（否則 ui_event 提示，
  port workspace_controller.handle_send 語意）；buffer 非空時：
  組 payload（port text_accumulator 的 flush 格式＋main.py 段落 F 的
  `Title`＝session 當前標題、`Metadata.ClientTime`＝UTC ISO 時間），
  `session_manager.add_message("user", content)`，emit `outbound` payload，
  emit ui_event sending 訊息＋status "傳送中"，最後清空 buffer；
  buffer 空時 ui_event 提示不發送

必要測試（≥12，涵蓋上述每個指令至少一例＋ /send 的 payload 欄位驗證＋非 buffer /send 拒絕）。

Commit: `feat(階段③): CommandRouter 工作區指令（/ws /show /clear /del /move /to_top /concat /copy /paste /export /import /send）`

---

### Task 4: CommandRouter 對話與其他指令

**Files:** Modify `modules/command_router.py`、Create `tests/test_command_router_session.py`

TDD。Port 自 `main.py:264-343`，語意相容：

- `/new [title]`、`/switch [title]`（default 不存在則建立）、`/list`（含當前標示）、
  `/delete <title>`、`/rename <old> <new>`、`/history`、`/save [file]`、`/load <file>`
  ——全部呼叫 session_manager 對應方法，ui_event 訊息文字與 main.py 相同
- `/stop`：emit `tts_ctl` "STOP_SPEECH"＋status 待機
- `/help`：port main.py 的 help_text
- `/exit`：emit `app_ctl` "EXIT"
- `unknown`：ui_event 未知指令訊息
- 測試用真 SessionManager＋tempfile（沿用 tests/test_clipboard_commands.py 的 make_sm 模式）

必要測試（≥8）。

Commit: `feat(階段③): CommandRouter 對話管理與雜項指令`

---

### Task 5: 語音指令解析

**Files:** Modify `modules/command_router.py`、Create `tests/test_command_router_voice.py`

TDD。`{"cmd": "voice", "args": [text]}` → 關鍵字解析後**內部重派發**到既有指令處理
（同一私有派發方法，不重複實作）。關鍵字表 port 自 `main.py:392-483`
（new/新建、switch/切換、list/列表、delete/刪除、save/保存、send/發送、
clear/清除（buffer/畫面變體）、show/顯示、stop/停止、history/歷史、help/幫助、
工作區/workspace、copy/複製、paste/貼上、concat/壓縮、to top/置頂、
export/匯出、import/匯入），無法識別 → ui_event「無法識別的語音指令」＋原文。
先 ui_event 顯示 `[語音指令] {text}`（port main.py:165）。

必要測試（≥6：中文關鍵字、英文關鍵字、帶參數擷取（如「匯出 測試」）、
clear 變體、無法識別、ui_event 順序）。

Commit: `feat(階段③): 語音指令關鍵字解析（內部重派發）`

---

### Task 6: 指令流整合測試

**Files:** Create `tests/test_command_flow_integration.py`

全鏈在 Exchange 上跑（真模組、假外設）：

1. 熱鍵流：OutboxAdapter(假 key_signal_queue, topic="commands") → Router →
   InboxAdapter(假 recorder_cmd_queue) 收到 "START"
2. 語音指令模式全鏈：commands `record_command_toggle` → gate_ctl 切 command →
   stt_text "send" → SttGate → commands voice → Router 執行 /send 路徑
   （buffer 預先放一筆，驗證 outbound 收到 payload）
3. normal 模式全鏈：stt_text → raw_text → WorkspaceManager 當前工作區
4. 終端指令流：OutboxAdapter(假 cli_cmd_queue) → `/ws stt` → wm.current 變更

跑全套件兩次驗證無 flaky。

Commit: `test(階段③): 指令流整合測試（熱鍵／語音指令／終端全鏈）`

---

### Task 7: 文件同步

- `plans/data_tunnel_design.md`：通道表加 `stt_text`、`gate_ctl`、`app_ctl`；
  「工作流」第 2 點補 SttGate 說明；業務邏輯落點加 SttGate
- `docs/architecture.md`：版本標頭改階段③完成；第 3 節通道表同步；
  第 5 節對照表（terminal_input/keyboard_listener 列）；第 6 節階段③打勾；
  第 8 節測試清單補新測試檔

Commit: `docs(階段③): 設計文件與架構文檔同步指令流設計`

---

## 完成定義（Definition of Done）

- [ ] SttGate＋CommandRouter 就位；keyboard_listener.py、terminal_input.py、main.py 零修改
- [ ] 全部斜線指令／熱鍵／語音指令行為與 main.py 語意相容（chat 相關除外，標註階段④）
- [ ] `python3 -m unittest discover -s tests` 全綠（跑兩次）
- [ ] 文件同步

完成後進入階段④（聊天流），另寫 `plans/data_tunnel_stage4_plan.md`。
