# Voice Client 全面 Bug 檢查報告

- 檢查日期：2026-07-02
- 分支：`refactor/data-tunnel`（工作樹乾淨）
- 測試基準：`.venv/bin/python -m pytest -q` → **353 passed, 5 subtests passed**（全綠；CLAUDE.md 記載的 339 已過時，見附註）
- 檢查範圍：`main.py`、`app.py`、`core/`、`modules/`（含 command_handlers）、`record.py`、`voice_to_text.py`、`text_to_voice.py`、`http_client.py`、`summary_generator.py`、`session_manager.py`、`workspace.py`、`keyboard_listener.py`、`local_control.py`、`terminal_input.py`、`tui_renderer.py`、`mobile_server.py`、`text_accumulator.py`、`workspace_controller.py`、`utils/`
- 本次僅調查與回報，未修改任何程式碼。

依嚴重程度排序如下。

---

## 1. 本地 LLM 模式：`content` 變數被歷史迴圈覆蓋，送給模型的「目前對話內容」是錯的

- **位置**：`http_client.py:104-125`（關鍵在 104、117、123 行）
- **問題描述**：`_call_local()` 先以 `content = payload.get("Content", "")` 取得使用者本次輸入（104 行），
  接著格式化歷史的 for 迴圈在 117 行重複使用同名變數 `content = msg[1] ...`。
  迴圈結束後，123 行組出的 `user_input = f"...目前的對話內容：{content}"` 用到的是
  **最後一筆歷史訊息的內容**，而不是使用者剛送出的文字。
- **觸發情境**：`SERVER.enabled = false`（目前 config.ini 即為此設定）且當前 session 歷史 ≥ 2 筆時，
  每次 `/send` 送給 LLM 的「目前的對話內容」都是 `history[-2]`（通常是上一輪 AI 回覆），
  使用者本次的問題完全沒送出去。只有歷史為空（首輪）時行為才正確。
- **確信度**：確認（純程式邏輯，可靜態驗證）。
- **建議修法**：迴圈內改用不同變數名（如 `hist_role` / `hist_content`），或在迴圈前把本次輸入
  另存 `current_content`，123/125 行改用它。建議補一個「有歷史時送出內容正確」的單元測試。

## 2. Kokoro TTS worker 死亡後播放器永久停擺（無存活偵測），任務與佇列無界累積

- **位置**：`text_to_voice.py:297-306`（`_play` kokoro 分支）、`332-335`（`_is_playing`）、`372-383`（`_drain_kokoro_results`）、`337-359`（`_start_kokoro_worker`）
- **問題描述**：kokoro 引擎下 `_is_playing()` 完全依賴 `_current_task_id`，只有收到 worker 回報的
  `done`/`error`/`startup_error` 才會清空。dispatcher 從不檢查 `self._kokoro_process.is_alive()`：
  - worker 匯入失敗（`startup_error`）後行程結束，但 dispatcher 之後仍會把下一個任務 `put` 進
    `_kokoro_tasks`（無人消費）並設 `_current_task_id`，此後永遠不會有結果回來 →
    `_is_playing()` 永遠為 True，之後所有 TTS 任務堆在 `self._heap` 無限成長，整個 TTS 靜默失效。
  - worker 中途崩潰（被 OOM/segfault 殺掉）同理：當前任務沒有 `done`，永久卡死。
  - `STOP_SPEECH` 只清 `_current_task_id`，會讓下一個任務再次投入死佇列，無法自救。
- **觸發情境**：config.ini 目前 `TTS.engine = kokoro`。任何一次 kokoro 子行程異常結束
  （依賴缺失、ONNX/CUDA 錯誤、被系統殺掉）之後，TTS 從此無聲且無任何 UI 提示，
  記憶體隨 TTS 任務累積緩慢成長。與 MEMORY「TTS 本機發不出聲」症狀可能相關，值得優先排查。
- **確信度**：確認（邏輯上必然；實際觸發需 worker 死亡）。
- **建議修法**：dispatcher 每輪檢查 `_kokoro_process.is_alive()`，死亡時清 `_current_task_id`、
  丟棄/回報待播任務並發 ui_event 錯誤（或自動重啟 worker 一次）；`_play` 前也應檢查行程存活。

## 3. Workspace 跨執行緒競態：`/send`、`/concat` 與 raw_text 寫入同時發生會遺失語音文字

- **位置**：`modules/command_handlers/workspace.py:187-188`（`flatten()` 之後 `clear()`）、
  `workspace.py:90-99`（`concat_all` 整份替換 `_entries`）、`modules/workspace_manager.py:50-51`（WM 執行緒 append）
- **問題描述**：`Workspace` 無任何鎖。桌面架構下 **WorkspaceManager 執行緒**負責把 raw_text
  append 進當前工作區，而 **CommandRouter 執行緒**執行 `/send`（`flatten()` → `clear()`）、
  `/concat`（讀取後整份替換 `_entries`）、`/del`、`/move` 等複合操作。兩段操作之間若有新
  entry 被 append：
  - `/send`：`flatten` 之後、`clear` 之前 append 的文字會被清掉且從未送出（靜默遺失）；
  - `/concat`：讀 `flat` 之後 append 的 entry 會在 `self._entries = [[...]]` 賦值時被覆蓋遺失。
- **觸發情境**：邊講話邊按 F9/QUICK_SEND 或下 `/send`、`/concat`——STT 結果剛好在指令執行
  窗口內送達時，該句語音消失。窗口小但此 App 的典型用法（語音持續輸入＋熱鍵送出）會反覆碰到。
- **確信度**：確認（競態確實存在；發生機率取決於時序）。
- **建議修法**：在 `Workspace` 加一把 `threading.Lock` 保護所有讀寫，或提供原子的
  `drain()`（flatten+clear 一次完成）給 `/send` 使用；`concat_all` 同樣需在鎖內完成。

## 4. SessionManager 非執行緒安全且寫檔非原子：sessions 檔可能損毀

- **位置**：`session_manager.py:79-85`（`_save_sessions`）、`125-133`（`add_message`）
- **問題描述**：`SessionManager` 被三條執行緒同步呼叫：CommandRouter（`/send` 的
  `add_message("user", ...)`、`/clear chat`、session 指令）、ChatFlow（回覆到達時
  `add_message("assistant", ...)`）、HttpClient（讀 history）。`_save_sessions()` 直接以
  `open(path, "w")` 覆寫且無鎖、無 temp-file+rename：
  - 兩執行緒同時 `_save_sessions()` 時寫入互相交錯，可能產生壞掉的 JSON；
  - 程式在寫入途中崩潰/斷電，檔案半截；`_load()` 解析失敗時直接 `self._sessions = {}`——
    **所有對話歷史一次歸零**。
- **觸發情境**：上一輪回覆抵達（ChatFlow 寫檔）與使用者同時 `/send`（CommandRouter 寫檔）重疊；
  或任何寫檔瞬間行程被殺。
- **確信度**：確認（競態與非原子寫入皆為事實；毀檔需時序配合）。
- **建議修法**：`_save_sessions` 改為寫 temp 檔後 `os.replace()`；並以一把鎖序列化所有
  mutate＋save。`_load` 失敗時應先備份壞檔再重置，避免直接吞掉。

## 5. `new_session` 同名直接覆蓋既有對話，歷史靜默遺失（含自動編號碰撞）

- **位置**：`session_manager.py:89-98`（`new_session`）、`modules/command_handlers/session.py:7-11`（`_handle_new`）、`mobile_server.py:293-297`
- **問題描述**：`new_session(title)` 不檢查 `title in self._sessions`，直接
  `self._sessions[title] = {..., "history": []}` 覆蓋並存檔——舊對話的完整歷史無備份消失。
  另外 `_handle_new` 的預設標題 `session_{len(sessions)+1}` 會碰撞：例如現存
  `["session_2"]`（len=1）→ 新標題 `session_2` → 覆蓋既有對話。
- **觸發情境**：`/new default`（default 幾乎必然存在）、`/new 既有名稱`、或刪除過中間編號後
  連續使用無參數 `/new`。語音指令「新建…」也走同一路徑。桌面與 mobile 兩條入口皆中。
- **確信度**：確認。
- **建議修法**：`new_session` 遇同名回傳失敗（或自動改名 `title_2`）；`_handle_new` 的自動
  編號改為找第一個未使用的編號。

## 6. mobile_server：多個（或殘留半死）WebSocket 連線會互搶共享事件佇列

- **位置**：`mobile_server.py:187-212`（`websocket_handler` 每連線建立一個 pusher）、`418-476`（`_output_pusher` 直接消費模組層級共享 queue）
- **問題描述**：所有佇列（`_stt_output_queue`、`_recv_queue`、`_ui_event_queue`…）是模組層級
  單例，但每個 WebSocket 連線都會啟一個 `_output_pusher` 消費它們。兩個連線並存時事件被
  隨機瓜分（每則訊息只會送到其中一個客戶端）；更常見的是手機斷網重連而舊連線尚未觸發
  `WebSocketDisconnect`：舊 pusher 仍在偷取事件並往死連線送（`send_json` 例外 → 事件直接
  丟失，只記 log），新連線收不到 STT 結果與回覆。此外兩個 pusher 併發呼叫
  `_handle_response`/`add_message` 也放大第 4 點的競態。
- **觸發情境**：手機瀏覽器切背景後重連、或兩台裝置同時開啟頁面。
- **確信度**：確認（架構性問題；文件註明 single-user，但程式未強制單連線）。
- **建議修法**：維持全域唯一 pusher（連線註冊/替換目標 WebSocket），或新連線建立時主動關閉
  舊連線；`send_json` 失敗的事件應退回佇列。

## 7. STT 模型載入失敗後靜默吞掉所有音訊；Recorder 錯誤後執行緒死亡無法恢復

- **位置**：`voice_to_text.py:87-100`（`_load_model` 失敗只記 log）、`102-104`（`_model is None` 時回空字串）、`record.py:55-78`（`_worker` 任何例外後執行緒結束）
- **問題描述**：
  - `VoiceToText._load_model()` 失敗（模型未下載、CUDA/cuBLAS 問題——config 目前用
    `cuda + float16`）後，迴圈照常從 `audio_queue` 取出音訊、`_transcribe` 回 `""`、
    **每段錄音被無聲丟棄**，UI 沒有任何錯誤提示（僅啟動早期的一行 log）。
  - `Recorder._worker` 發生任何例外（開啟裝置失敗、錄音中裝置拔除）會發一次 error 事件後
    執行緒永久結束；之後 `recorder_ctl` 的 START/STOP 在 `recorder_cmd_queue` 無限堆積，
    無自動重啟，只能重啟整個程式。CommandRouter 的 `_is_recording` 也會因此與實際狀態脫鉤。
- **觸發情境**：GPU 環境異常、whisper 模型缺失、麥克風被占用/拔除。
- **確信度**：確認（例外處理路徑可靜態驗證）。
- **建議修法**：模型載入失敗時發 `ui_event` 告知並讓後續音訊觸發一次性錯誤提示（或重試載入）；
  Recorder `_worker` 外層加重啟迴圈（帶退避），或至少在死亡後持續回報錯誤事件。

## 8. 錄音後若整段無語音，狀態列永久卡在「處理中」（桌面與 mobile 皆有）

- **位置**：`record.py:102-109`（STOP 時 `had_speech=False` 不 flush）、`modules/command_router.py:201-203`（recording_stopped → 顯示「處理中」）、`mobile_server.py:217-227`（`_handle_audio` 成功路徑不復位）
- **問題描述**：桌面：F8 停止錄音時 CommandRouter 顯示「處理中」，之後只有 ChatFlow 收到回覆
  等事件才會發「待機」。若該段錄音從頭到尾靜音（`had_speech=False`），Recorder 不 flush、
  STT 無輸出，**沒有任何人把狀態切回「待機」**。STT 輸出空字串被 SttGate 丟棄時同樣卡住。
  mobile 的 `_handle_audio` 成功把音訊入佇列後也一樣：STT 若輸出空白，狀態停在「處理中」。
- **觸發情境**：按下錄音但沒說話就停止；或環境音量低於 `silence_threshold`。
- **確信度**：確認。
- **建議修法**：Recorder 在 STOP 且未 flush 任何片段時附帶事件（如 `{"event":"recording_stopped","flushed":false}`）讓 router 直接回「待機」；或 STT 對空白結果發一則狀態復位訊息。

## 9. LocalControl 關機競態：`assert self._socket is not None` 可能在 stop() 後爆 AssertionError

- **位置**：`local_control.py:86-94`（`_loop`）、`73-81`（`stop()`）
- **問題描述**：`stop()` 依序 `self._running = False` → `close()` → `self._socket = None`，
  而 `_loop` 執行緒可能剛通過 `while self._running` 檢查、尚未進 `recv`；此時 `_socket`
  已被設為 `None`，`assert` 失敗拋出 AssertionError——它不在 `except socket.timeout/OSError`
  的攔截範圍內，執行緒以未處理例外結束並在關機時印 traceback。另外若以 `python -O` 執行，
  assert 被移除後會變成 `None.recv` 的 AttributeError。
- **觸發情境**：每次正常關機都有小機率；視窗極窄，多數時候看不到。
- **確信度**：確認（競態存在；發生率低、僅影響關機觀感）。
- **建議修法**：`_loop` 先把 `self._socket` 讀進區域變數並判 `None` 即 break，不要用 assert；
  或 `stop()` 先 join 再清空引用。

## 10. Recorder 待機期間不讀取音訊流：START 後首段可能夾帶按鍵前的舊緩衝音訊

- **位置**：`record.py:113-118`（未錄音時只 `sleep(0.02)`，stream 持續開啟）
- **問題描述**：PyAudio stream 在執行緒啟動時就打開且從不關閉；`not recording` 期間完全不
  `read`，驅動端輸入緩衝持續累積直到 overflow。按下 START 後的前幾次 `read`
  （`exception_on_overflow=False`）可能先吐出按鍵之前殘留的舊音訊，混入辨識，或因 overflow
  遺失起頭。實際行為依 ALSA/PortAudio 緩衝策略而異。
- **觸發情境**：程式閒置一段時間後開始錄音，首句辨識異常（多出舊聲音或掉頭）。
- **確信度**：疑似（機制成立，但實際影響量取決於平台緩衝行為，未實機驗證）。
- **建議修法**：收到 START 時先把 stream 內殘留資料讀掉丟棄（或 stop_stream/start_stream
  重置），再開始累積 frames。

## 11. SttGate 模式切換與在途 STT 結果的順序競態：語音指令可能被當成一般文字

- **位置**：`modules/stt_gate.py:40-64`、`modules/command_router.py:163-181`
- **問題描述**：`gate_ctl`（來自 CommandRouter）與 `stt_text`（來自 STT 轉接器）是不同生產者，
  Exchange round-robin 搬移，兩者相對順序無保證。F7 錄語音指令、辨識尚在進行時按 F8
  （會立即發 `gate_ctl normal`），稍後才抵達的 `stt_text` 會走 normal 分支——本應是指令的
  語音被寫進工作區；反向情境亦然。
- **觸發情境**：快速連續操作熱鍵＋STT 延遲（GPU 忙碌時數百 ms 以上）。舊版 main.py 用旗標
  同樣有此問題，屬 legacy 語意的固有競態。
- **確信度**：疑似（競態確實存在；是否視為 bug 取決於產品語意）。
- **建議修法**：若要根治，需在 audio/stt_text 訊息上攜帶「錄音當下的模式」標記，
  由 Recorder→STT 透傳，而非事後以全域模式分流。

## 12. 桌面與 mobile 指令行為不一致（Data Tunnel vs mobile_server 對齊債）

- **位置**：`mobile_server.py:299-305` vs `modules/command_handlers/session.py:13-22`；`mobile_server.py:292-383` vs `modules/command_router.py:80-159`
- **問題描述**：兩條入口對同一使用者指令的行為有落差：
  - `/switch`（無參數）：桌面在 default 不存在時會自動建立並切換；mobile 只回「找不到對話」。
  - 桌面工作區集合是 `buffer/stt`（`WorkspaceManager.DEFAULT_NAMES`）＋chat 唯讀檢視；
    mobile 是 `stt/buffer/chat` 且 chat 可 `/del`、`/move`、`/to_top`（桌面 CommandRouter
    對 chat 無這些操作）。`/ws chat` 桌面拒絕切換、mobile 允許。
  - mobile 無 `/exit`、無語音指令解析（`VoiceCommandMixin` 僅桌面接入）。
  文件已標注 mobile_server 待對齊，此處列出實際差異供對齊時參考。
- **觸發情境**：同一使用者在兩端操作時得到不同結果。
- **確信度**：確認（行為差異可靜態比對）；是否算 bug 屬產品決策。
- **建議修法**：mobile 對齊 `_handle_switch` 的 default 自動建立；其餘差異在 mobile 對齊
  Data Tunnel 專案時統一。

## 13. `_setup_logging`：`log_file` 不含目錄時 `os.makedirs("")` 直接崩潰

- **位置**：`app.py:53-54`、`mobile_server.py:42-43`
- **問題描述**：`os.makedirs(os.path.dirname(log_file), exist_ok=True)`——若使用者把
  `WORKSPACE.log_file` 設成純檔名（如 `system.log`），`dirname` 為空字串，
  `os.makedirs("")` 拋 `FileNotFoundError`，程式啟動即死。
- **觸發情境**：修改 config.ini 的 log_file 為不含路徑的檔名。
- **確信度**：確認（邊界條件）。
- **建議修法**：`d = os.path.dirname(log_file); if d: os.makedirs(d, exist_ok=True)`（
  專案內 `workspace.py:160-162`、`text_accumulator.py:44-46` 都已正確處理，僅此兩處遺漏）。

## 14. 摘要失敗或輸出空白時，長回覆完全不朗讀且無提示

- **位置**：`summary_generator.py:54-67`、`modules/chat_flow.py:75-82`
- **問題描述**：長回覆（≥ threshold）走 `summary_req` 後，若 SLM 呼叫失敗或回空字串，
  SummaryGenerator 只記 warning、發「待機」，不會回任何 summary，ChatFlow 也沒有 fallback
  ——這輪回覆對語音優先的使用者而言等於無聲，且 UI 無錯誤訊息。另外若 `SLM.enabled`
  在 ChatFlow 與 SummaryGenerator 讀到不同來源（目前相同，僅防未來 drift），任務會被
  `_loop` 靜默吞掉。
- **觸發情境**：SLM（本例 gemma3:1b @ localhost）未啟動或逾時。目前 config `SLM.enabled=false`
  所以暫不會走到，但開啟 SLM 後必現。
- **確信度**：確認（錯誤路徑可靜態驗證）。
- **建議修法**：摘要失敗時輸出 `{"type":"summary_failed"}` 之類訊息，ChatFlow fallback 直接
  TTS 原文（或至少 ui_event 告知摘要失敗）。

## 附註（非 bug，維護提醒）

- `CLAUDE.md` 記載的測試基準「339 passed」已過時，實際為 **353 passed, 5 subtests passed**，建議更新。
- `text_accumulator.py:67-83` 主迴圈每輪固定 `sleep(0.01)` 且每輪只處理一筆，批量貼上/匯入大量行時吞吐上限 ~100 筆/秒（mobile 貼上大量文字會有可感延遲），非正確性問題。
- `text_to_voice.py` 的 `MUTE`/`UNMUTE` 指令目前沒有任何生產者，屬死碼。
- `/to_top 0` 會因 `if idx else -1` 的 falsy 判斷被當成「無參數＝最後一筆」（`modules/command_handlers/workspace.py:109`、`text_accumulator.py:201`），語意上宜回報「編號需 ≥1」。
