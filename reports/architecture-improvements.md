# Voice Client 架構改進報告

- 調查日期：2026-07-02
- 分支：`refactor/data-tunnel`
- 範圍：`main.py`、`app.py`、`core/`、`modules/`、`mobile_server.py`、歷史相容路徑、
  生命週期／執行緒模型、測試結構
- 性質：純調查報告，未修改任何程式碼

---

## 0. 總體評估

Data Tunnel 重構的核心目標已達成，且品質良好：

- **`core/` 完全乾淨**：五個檔案只 import 標準庫與彼此，零業務依賴，符合
  「core/ 不依賴 Voice Client 業務模組」的鐵律。
- **`app.py` 基本上是純接線**：`wire()` 不含業務決策；`main()` 是建構＋啟停腳本。
- **單執行緒交換語意落實**：佇列間搬移只發生在 Exchange 執行緒，round-robin
  防餓死、錯誤隔離、無路由丟棄告警，皆有對應單元測試。
- **測試結構支撐重構**：框架單元測試（`test_core_*`）、模組測試、四支整合測試、
  `test_app_wiring.py` 端到端路由驗證，層次分明。

以下改進建議依優先順序排列。P1–P3 是結構性問題（建議納入下一階段主線），
P4–P6 是健壯性補強，P7–P10 是清理與可觀測性。

---

## P1. mobile_server.py 對齊 Data Tunnel（消除雙實作漂移）

### 現況問題

`mobile_server.py`（624 行）是一條**平行宇宙**：它繞過 Exchange，自建 10 個裸
queue，用 `_output_pusher()` 每 50ms 輪詢所有 output queue——這正是舊 `main.py`
中央路由器的翻版。具體重複：

| mobile_server 內的邏輯 | 桌面主線的對應模組 | 漂移風險 |
|---|---|---|
| `_handle_response()`（388–414 行） | `ChatFlow._handle_inbound` | 摘要門檻／TTS 決策已是兩份拷貝 |
| `_route_cmd()` 的 `/new /switch /list...`（292–344 行） | `SessionCommandMixin` | 訊息格式已有微妙差異（如 `/list` 尾行文字不同） |
| `_output_pusher` 第 2 段的 payload 組裝（431–442 行） | `WorkspaceCommandMixin._handle_send` | 兩處各自補 `Title`/`Metadata` |
| `_output_pusher` 第 3 段摘要呈現（450–457 行） | `ChatFlow._handle_summary_out` | 同上 |
| STT 輸出分流（423–428 行） | `SttGate` | mobile 無 command 模式，功能已分岔 |

此外 `mobile_server.py` 在 **import 時**就 `load_config()` 並建構
`VoiceToText`（會載入 Whisper 模型的物件）等所有元件（91–119 行），
導致無法被測試 import、也無法注入替身——`tests/` 裡完全沒有 mobile 測試。

### 改進方案

讓 mobile 與桌面共用同一組 Exchange＋原生模組，只替換「邊緣裝置」：

1. 抽出共用組裝函式（例如 `app.build_core(config)`）：建立
   SessionManager、WorkspaceManager、SttGate、CommandRouter、ChatFlow、
   HttpClient、SummaryGenerator 並完成 wire()——桌面與 mobile 都呼叫它。
2. mobile 特有的邊緣替換：
   - Recorder → WebSocket binary frame → `_to_wav()` → 以 `OutboxAdapter`
     掛上 `audio` topic（VoiceToText 照舊消費）。
   - TuiRenderer → 一個 `WsPusher` 消費者：消費 `ui_event`（不做 dict→UiEvent
     轉換，直接推 JSON 給前端）。
   - AudioPriorityPlayer → 前端 SpeechSynthesis：`tts` 與 `tts_ctl` topic 的
     消費者改為 WebSocket 推送。
3. 協定缺口需先補（詳見 P3/P4）：
   - mobile 多出的事件型別 `sessions_refresh`、`tts_control`、
     `clipboard_read/write` 需納入 `ui_event`／新 topic 協定。
   - `/copy`、`/paste` 在桌面用 `utils.clipboard`（本機剪貼簿）、mobile 用
     瀏覽器剪貼簿往返——建議把剪貼簿做成 CommandRouter 的注入 port
     （建構子傳入 clipboard provider），或新增 `clipboard_ctl` topic。
   - Exchange 目前一 topic 一消費者；mobile 若要同時保留桌面 TUI 呈現則需要
     fan-out（見 P4）。單獨跑 mobile 則不需要。
4. 對齊完成後刪除 `text_accumulator.py`、`workspace_controller.py`（見 P7）。

### 影響範圍

`mobile_server.py`、`app.py`（抽 `build_core()`）、`static/` 前端事件協定、
新增 `tests/test_mobile_wiring.py`；`docs/architecture.md` §5 的
「mobile_server.py 另案對齊」項目收斂。

### 建議執行順序

作為「階段⑥／mobile 對齊案」的主體，但**前置依賴 P3（協定集中定義）與
P4（Exchange fan-out／解除註冊）**，建議排在其後。

---

## P2. 跨執行緒共享狀態無鎖（Workspace／SessionManager）

### 現況問題

隧道解決了「佇列搬移」的競態，但**同步共享物件仍在多執行緒間裸奔**：

- `Workspace`（`workspace.py`）是純 list 操作、無鎖。同一個 buffer 工作區：
  - WorkspaceManager 執行緒經 `handle()` `append()`（raw_text 消費）；
  - CommandRouter 執行緒直接呼叫 `ws.clear()`、`concat_all()`、`move()`、
    `flatten()`（`modules/command_handlers/workspace.py`）。
  `concat_all`＝讀全部→清空→append 的複合操作，與並發 `append` 交錯會**丟失
  剛辨識完的語音文字**（例：長句 STT 完成瞬間使用者按 F9 quick_send，
  `_handle_send` 的 `flatten()`→`clear()` 之間插入的 append 會被 clear 吃掉）。
- `SessionManager` 無鎖，卻被三條執行緒同步呼叫：CommandRouter
  （`/new /delete /rename`…）、ChatFlow（`add_message`）、HttpClient
  （`_call_local` 讀 `get_current_session()`）。`add_message` →
  `_save_sessions()` 的檔案寫入若與 `delete_session` 交錯，可能寫出不一致的
  `.sessions.json`。
- `WorkspaceManager.switch()` 的註解已自我辯護「GIL 下單一屬性指派無需加鎖」
  ——這對 `switch` 成立，但掩蓋了上述複合操作問題。

### 改進方案

二選一（建議前者，改動小且不動訊息協定）：

1. **加鎖**：`Workspace` 內建 `threading.RLock`，所有公開方法加鎖；
   `SessionManager` 同樣以一把 RLock 保護「記憶體變更＋落盤」的複合區段。
   風險低、行為不變，測試可加「並發 append + concat/clear」的壓力測試。
2. **回歸隧道哲學**：工作區的**變更**操作全部經 topic（如 `workspace_ctl`）
   由 WorkspaceManager 自己的執行緒執行，CommandRouter 只保留讀取。
   更乾淨但需要 request/reply 模式（`/show` 要拿結果回覆），工程量大，
   可留待日後。

### 影響範圍

`workspace.py`、`session_manager.py`（＋各自測試補並發案例）；不動協定與接線。

### 建議執行順序

**立即可做**，獨立於 mobile 案，屬低風險 bug 預防。建議排最前面。

---

## P3. topic／payload 協定集中定義（單一事實來源）

### 現況問題

topic 名稱與 payload 形狀目前是**散落在各檔案的魔法字串**：

- 同一個 payload 形狀由生產者、消費者、測試三方各自手寫：
  `{"cmd": ..., "args": [...]}`（terminal_input、SttGate、CommandRouter）、
  `{"type":"message","role":...,"text":...}`（幾乎每個模組都在拼這個 dict）、
  `{"event": ...}`（Recorder／CommandRouter）。打錯一個 key 不會有任何
  靜態或執行期檢查，只會靜默走 `payload.get(..., fallback)`。
- **風格不一致**：控制 topic 有的用裸字串（`recorder_ctl` 的 `"START"`、
  `tts_ctl` 的 `"STOP_SPEECH"`、`app_ctl` 的 `"EXIT"`），有的用 dict
  （`gate_ctl` 的 `{"mode":...}`、`chat_ctl` 的 `{"cmd":...}`）；
  HTTP payload 用大寫 key（`Content`/`Title`/`Metadata`），內部訊息用小寫。
- 指令集重複定義：`terminal_input.py` 的 `_SLASH_COMMANDS` 集合與
  CommandRouter `_dispatch` 的 if/elif 鏈、`_handle_help` 文字三處平行維護，
  新增一個指令要改三個地方（mobile 對齊後是四個）。
- `docs/architecture.md` §3 的 topic 表是唯一的「協定文件」，但與程式碼
  沒有機械性連結，漂移只能靠人眼。

### 改進方案

新增一個**零依賴的協定模組**（建議 `core/topics.py` 或 `modules/protocol.py`；
若放 `core/` 只放 topic 常數，payload 形狀屬業務可放 `modules/`）：

1. topic 名稱常數：`TOPIC_AUDIO = "audio"` 等，全部生產／消費／接線／測試改用常數。
2. payload 形狀以 `TypedDict` 或輕量 dataclass＋建構函式定義：
   `ui_message(role, text)`、`ui_status(text)`、`command(cmd, args)`、
   `recorder_event(event, **kw)`……取代到處手拼 dict。
3. 控制 topic 統一形狀（建議一律 dict `{"cmd": ...}`，字串型維持相容期）。
4. `_SLASH_COMMANDS` 改由 CommandRouter 的 dispatch 表匯出（見 P8），
   terminal_input import 之，單一事實來源。
5. 加一支**協定契約測試**：驗證 architecture.md §3 表列 topic 與
   `wire()` 實際註冊的路由一致（可解析常數表比對），防文件漂移。

### 影響範圍

全部模組的 emit／handle 呼叫點（機械性替換）、tests、`docs/architecture.md`。
行為不變，屬 behavior-preserving 重構。

### 建議執行順序

**mobile 對齊（P1）的前置**：對齊時要新增／擴充事件型別，先有單一協定
定義處才不會把漂移複製到 mobile。排在 P2 之後。

---

## P4. Exchange 能力缺口：fan-out、解除註冊、背壓

### 現況問題

1. **一 topic 一消費者**是目前的硬限制（`register_consumer` 重複即拋
   `ValueError`）。這對「工作佇列」語意正確，但 `ui_event` 本質是**廣播**：
   mobile 對齊後若想「桌面 TUI＋WebSocket 同時呈現」、或想加一個
   `ui_event` 落盤記錄器，都做不到。
2. **無法解除註冊**：`Exchange` 只有 register 沒有 unregister；mobile 的
   WebSocket 消費者隨連線建立／斷開，生命週期比行程短，現有 API 撐不住。
3. **無背壓**：所有 `queue.Queue()` 無上限。`audio` topic 風險最高——
   CPU 慢速 STT 時 Recorder 持續切片，記憶體與延遲都會無限成長；
   `ui_event` 在 TUI 卡住時同理。
4. 小項：`register_producer` 允許重名不告警；`Message.created_at` 從未被
   讀取，無法量測通道延遲。

### 改進方案

1. 新增**廣播型註冊** `register_subscriber(topic, inbox)`：同一 topic 允許
   多個 subscriber（每人收到複本引用），與既有單一 consumer 語意並存
   （一個 topic 只能二選一，混用拋錯）。`ui_event`、未來的 `tts` 皆改為
   broadcast 型。
2. 新增 `unregister_consumer/subscriber(topic, inbox)`，並讓註冊表操作
   改在 Exchange 執行緒安全（現在「先 attach 再 start」的慣例在動態
   接線下不夠，最簡做法是註冊表加一把鎖，tick 內短暫持鎖）。
3. 佇列上限與策略：`Inbox(maxsize=..., overflow="block"|"drop_oldest")`；
   `audio` 用 `drop_oldest`（丟最舊片段並記 warning），控制型 topic 維持
   無上限。Exchange `put_nowait` 滿時依策略處理並 log。
4. 順手：producer 重名告警；`tick()` 搬移時記 `time.time()-created_at`
   為 debug 級延遲 log（見 P10）。

### 影響範圍

`core/exchange.py`、`core/endpoint.py`、`tests/test_core_*`；`app.py` 的
`ui_event` 註冊方式。核心框架改動需完整單元測試護航。

### 建議執行順序

排在 P3 之後、P1（mobile 對齊）之前——是 mobile 案的技術前置。

---

## P5. 錯誤傳遞策略過於單薄

### 現況問題

- `TunnelModule._run` 捕捉 `handle()` 例外後只發固定文字
  `"[{name} 錯誤] 處理 {topic} 失敗"`——**例外訊息本身被丟掉**（只進 log），
  使用者端無法分辨是什麼錯。
- legacy 模組各自為政：VoiceToText 轉譯失敗只記 log（使用者停留在
  「處理中」狀態，因為 `recording_stopped` 已把狀態設為處理中，沒有
  後續事件把它復原成「待機」——**狀態卡死路徑**）；SummaryGenerator 失敗
  只記 warning；HttpClient 失敗會回 `{"type":"Error"}`（唯一有閉環的）。
- 無 dead-letter／`error` topic：錯誤不可路由、不可統計，mobile 對齊後
  前端也拿不到結構化錯誤。
- `Exchange` 無路由丟棄只記 warning——開發期新增 topic 打錯字時，
  唯一線索埋在 log 裡。

### 改進方案

1. 定義 `error` topic（或擴充 `ui_event` payload 帶 `error` 欄位）：
   `{"module": name, "topic": topic, "message": str(exc)}`；
   `TunnelModule._run` 改發結構化錯誤，呈現層決定顯示格式。
2. STT 失敗補閉環：VoiceToText 轉譯失敗時往輸出 queue 放一筆錯誤標記
   （或經 adapter 發 `recorder_event` 型錯誤），讓 CommandRouter 把狀態
   復原為「待機」——修掉狀態卡死。
3. Exchange 丟棄計數器：同一 unknown topic 首次 warning、之後降頻，
   並在 `stop()` 時輸出總計，測試可斷言為零。

### 影響範圍

`core/module.py`、`voice_to_text.py`（或其 adapter）、CommandRouter、
`docs/architecture.md` §7 錯誤策略一節、對應測試。

### 建議執行順序

P2 之後即可獨立進行；其中「STT 失敗狀態卡死」屬 bug 性質，可先單獨修。

---

## P6. 生命週期：legacy 模組 stop() 不 join、啟停清單三處重複

### 現況問題

1. **legacy 模組的 `stop()` 只翻旗標、不 `join()`**：Recorder、VoiceToText、
   HttpClient、SummaryGenerator、TerminalInput、TuiRenderer 皆是
   `self._running = False` 就返回（對照 `TunnelModule.stop()` 有
   `join(timeout=2)`）。行程靠 daemon 執行緒被強殺收尾——Recorder 的
   PyAudio stream／`pa.terminate()` 清理有機率跑不完，偶發 ALSA 噪音或
   資源洩漏警告。`docs/architecture.md` §7 宣稱「全部 daemon，`stop()` 以
   `join(timeout)` 收尾」與現況不符。
2. **啟停清單在 `app.py` 手寫三份**：建構（292–311 行）、start
   （344–360 行）、stop（396–411 行）各列一次，順序靠人維護。新增模組
   漏寫其中一份不會有任何錯誤。
3. **關機無 drain**：模組先停、Exchange 後停，停機瞬間仍在 outbox 的訊息
   會被 Exchange 投遞到「已停止模組」的 inbox 而靜默消失。對本專案多為
   ui_event 無傷大雅，但 `outbound`（未送出的聊天）值得在 stop 時記 log。
4. 小項：`app.py` 兩處繞過隧道直接操作裸 queue——啟動訊息直塞
   `ui_event_queue`（有註解說明，可接受）、停機直塞 `tts_cmd_queue.put("TERMINATE")`
   （建議改經 `tts_ctl` 語意，或至少集中到一個 shutdown 函式）。

### 改進方案

1. 給 legacy 模組補 `join(timeout)`（TerminalInput 因阻塞在 `input()` 無法
   join，明確註記例外）；或引入統一 `Lifecycle` 協定
   （`start()/stop(timeout)`），adapter 層補齊。
2. `app.py` 引入**模組註冊表**：`modules: list = [...]` 一份清單，
   `for m in modules: m.start()`／`for m in reversed(modules): m.stop()`，
   啟停順序單一來源，倒序停機順帶更合理（先停生產端、後停消費端、最後
   Exchange）。
3. `Exchange.stop()` 前選擇性 drain：tick 直到所有 outbox 空或逾時，
   並 log 殘留訊息數。

### 影響範圍

`app.py`、六個 legacy 模組的 `stop()`、`docs/architecture.md` §7。

### 建議執行順序

與 P5 同批；改動小、風險低。

---

## P7. 歷史相容路徑的移除條件與現況

### 現況

`rg` 引用清點（2026-07-02）：

- `text_accumulator.py`（268 行）：僅 `mobile_server.py` 與
  `tests/test_text_accumulator.py` 引用。
- `workspace_controller.py`（244 行）：僅 `mobile_server.py`、
  `tests/test_workspace_controller.py`、`tests/test_clipboard_commands.py` 引用。
- 桌面主線（`app.py`／`modules/`）**已零引用**，CODE_MAP 描述正確。

### 移除條件（建議寫成 P1 驗收項）

1. mobile 對齊完成：buffer 工作區改由 WorkspaceManager 承載、工作區指令
   改走 CommandRouter。
2. 刪除兩個模組＋`tests/test_text_accumulator.py`、
   `tests/test_workspace_controller.py`；`tests/test_clipboard_commands.py`
   中依賴 WorkspaceController 的案例遷移為 CommandRouter 版
   （桌面剪貼簿邏輯已在 `WorkspaceCommandMixin`，多數案例應已有等價覆蓋，
   遷移前先比對）。
3. 同步更新 CODE_MAP「設定、工具與歷史相容」節與 `docs/architecture.md` §5/§6。

### 建議執行順序

P1 的收尾子任務，不單獨排程。

---

## P8. CommandRouter 派發鏈與 mixin 隱式耦合

### 現況問題

- `_dispatch()` 是 60 行的 if/elif 鏈（`modules/command_router.py:80-159`），
  每加一個指令改一處鏈、一處 `_SLASH_COMMANDS`、一處 `/help` 文字。
- 三個 mixin（Workspace/Session/Voice）依賴宿主提供 `self._wm`、`self._sm`、
  `self._ui_msg`、`self._dispatch`，這種「隱式協定」沒有型別或測試保證，
  mixin 單獨看不出依賴什麼。
- SessionManager 未接入時的防禦（120–123 行）用一長串 tuple 硬編碼指令名，
  與下方 elif 鏈重複。

### 改進方案

1. 改為**派發表**：`self._handlers: dict[str, Callable[[list], None]]`，
   由各 mixin 在 `__init__`（或類屬性表）註冊；`_SLASH_COMMANDS` 與
   `/help` 清單從表自動生成——與 P3 第 4 點合併實作。
2. mixin 若要保留，補一個 Protocol（`_ui_msg`/`_wm`/`_sm` 介面）讓依賴顯式化；
   或降級為「函式群＋明確參數」的 helper 模組。

### 影響範圍

`modules/command_router.py`、`modules/command_handlers/*`、
`terminal_input.py`、既有 `test_command_router_*` 全數應維持綠燈
（行為不變）。

### 建議執行順序

可與 P3 合併為一個「協定＋派發整併」PR；優先度中。

---

## P9. HttpClient 與業務狀態耦合（I/O 層讀對話歷史）

### 現況問題

`http_client.py` 建構子持有 `SessionManager`，`_call_local()` 直接讀
`get_current_session()["history"]` 組上下文（109–125 行）。這讓「網路 I/O
模組」依賴業務持久層，違反隧道「模組經訊息協作」的方向，也造成：

- P2 所述的跨執行緒無鎖讀取；
- 歷史組裝策略（取最後 5 筆、排除剛加入的一筆——依賴「呼叫前已 add_message」
  的隱式時序）藏在 I/O 層，ChatFlow/CommandRouter 看不到；
- mobile 與桌面共用 HttpClient 時，上下文策略無法按入口客製。

### 改進方案

`outbound` payload 由生產者（`WorkspaceCommandMixin._handle_send`）附上
`history` 欄位（它本來就持有 `self._sm`），HttpClient 退化為純 I/O：
有啥送啥。`_call_local` 的格式化邏輯移到 payload 組裝處或 ChatFlow。

### 影響範圍

`http_client.py`、`modules/command_handlers/workspace.py`、
`modules/chat_flow.py`（如採 ChatFlow 組裝）、`mobile_server.py`（對齊後自動受益）、
相關測試與 `docs/architecture.md` topic 表（`outbound` payload 形狀）。

### 建議執行順序

中優先；適合在 P3 定義 `outbound` payload 形狀時一併處理。

---

## P10. 可觀測性與測試缺口

### 現況問題

1. **可觀測性**：架構文件標榜「單點交換、資料流可在一處完整記 log」，但
   目前只有 `log.debug("%s --[%s]--> consumer")`。`Message.created_at`
   無人使用；無每-topic 計數、無佇列深度、無通道延遲，現場診斷
   （「為什麼 TTS 沒播」）仍要靠散落各模組的 log。
2. **測試缺口**（`tests/` 清點）：
   - 無 `mobile_server` 任何測試（P1 時必補）；
   - 無 `terminal_input`、`http_client`、`summary_generator`、
     `tui_renderer`、`keyboard_listener` 的單元測試——前三者是純邏輯
     （斜線指令解析、retry／failed-payload 備份、摘要流程），可測性高；
   - 無「協定契約測試」（見 P3 第 5 點）；
   - 無並發壓力測試（見 P2）。
3. 測試執行方式文件不一致：`docs/architecture.md` §8 寫
   「unittest，非 pytest」，`CLAUDE.md` 基準是 `pytest -q`（339 passed）。
   實際兩者皆可跑，建議文件統一以 pytest 為準。

### 改進方案

1. Exchange 增加輕量統計：`stats()` 回傳 per-topic 搬移數／丟棄數／
   目前佇列深度，`stop()` 時 log 一次；搬移延遲（`now - created_at`）超過
   閾值記 warning。成本極低，對語音管線延遲診斷價值高。
2. 依上列清單補測試，優先序：terminal_input（協定入口）→ http_client
   （retry/備份行為）→ summary_generator。
3. 修正 `docs/architecture.md` §8 測試執行說明。

### 建議執行順序

低優先、可穿插進行；契約測試部分隨 P3 落地。

---

## 建議執行路線圖（對應下一階段）

| 批次 | 項目 | 理由 |
|---|---|---|
| ① 立即（低風險補強） | **P2** 共享狀態加鎖、**P5** STT 錯誤閉環＋結構化錯誤、**P6** stop join／模組註冊表 | 都是 bug 預防／修復性質，不動協定，測試好寫 |
| ② 協定整併 | **P3** topic／payload 集中定義＋契約測試、**P8** 派發表化、**P9** outbound 攜帶 history | 一次把「魔法字串」清乾淨，為 mobile 鋪路 |
| ③ 框架擴充 | **P4** Exchange fan-out／unregister／背壓 | mobile 對齊的技術前置，核心改動需獨立護航 |
| ④ mobile 對齊案 | **P1** 共用 build_core、邊緣替換、**P7** 移除 text_accumulator／workspace_controller | 收斂雙實作，兌現 architecture.md §6 的「後續清理另案」 |
| ⑤ 持續 | **P10** 可觀測性與測試補洞 | 穿插於各批次 |

每一批完成時同步維護鏈：CODE_MAP → `docs/architecture.md` → README，
並維持 `.venv/bin/python -m pytest -q` 全綠。
