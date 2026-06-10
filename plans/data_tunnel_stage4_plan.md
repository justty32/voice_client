# 資料隧道階段④：聊天流 實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 聊天流上隧道——`outbound`→HttpClient→`inbound`→ChatFlow（歷史、摘要決策、重播）→`tts`／`ui_event`；SummaryGenerator 經轉接器掛上；chat 工作區指令接入 CommandRouter。

**Architecture:**
- **ChatFlow**（新原生模組）：消費 `inbound`、`summary_out`、`chat_ctl`；
  port main.py `_route_response`（寫歷史、摘要門檻決策、TTS 派發、狀態列）與
  段落 F1（摘要輸出呈現）；持有 `last_full_response` 供重播。
- **HttpClient／SummaryGenerator 零修改**：經 `core/adapter.py` 轉接器掛上
  （`outbound`→send_queue、recv_queue→`inbound`、`summary_req`→summary_queue、
  summary_output_queue→`summary_out`）。本階段以「同介面形態的假模組」做整合測試，
  真實接線在階段⑤。
- **CommandRouter 增量**：`play_last` 改 emit `chat_ctl` {"cmd":"play_last"}；
  `/clear chat` 接 `sm.clear_history()`（port workspace_controller:104-106）；
  `/ws` 列表的 chat 行顯示真實歷史筆數。
- **設計註記**：chat 不可成為「當前工作區」（raw_text 永不流入 chat）；
  chat 僅能以明確指令操作（/history /clear chat …）。`/ws chat` 回提示訊息。

**新增 topics:** `inbound`（HTTP 回應→ChatFlow）、`summary_out`（摘要器輸出→ChatFlow）、`chat_ctl`（Router→ChatFlow）。`outbound`、`summary_req`、`tts` 沿用既定。

**Port 來源:** `main.py:346-389`（`_route_response`）、`main.py:208-218`（F1 摘要輸出）、`main.py:138-141`（PLAY_LAST）、`workspace_controller.py:104-106`（chat 清空）、`summary_generator.py`（輸入/輸出格式）、`http_client.py`（recv 格式）。

**訊息格式:**

| topic | payload |
|---|---|
| `inbound` | http_client 回應 dict：`{"type": "ChatReply"/"StatusUpdate"/"Error", ...}` |
| `summary_req` | `{"cmd": "summary", "text": ..., "title": ...}`（summary_generator 既有輸入格式） |
| `summary_out` | `{"type": "status"/"summary", "text": ...}`（summary_generator 既有輸出格式） |
| `chat_ctl` | `{"cmd": "play_last"}` |
| `tts` | `{"text": ..., "priority": "low"/"medium"/"high"}` |

---

### Task 1: ChatFlow 模組

**Files:** Create `modules/chat_flow.py`、`tests/test_chat_flow.py`

ChatFlow(TunnelModule)：`name="chat_flow"`、`consumes=("inbound","summary_out","chat_ctl")`。
建構子 `ChatFlow(session_manager, summary_threshold=20, slm_enabled=True)`
（呼叫端從 config 讀值，模組不碰 configparser）。

`handle()` 依 topic／type 分派，port main.py 語意：

- `inbound` type=ChatReply：full_response = Content.full_response；非空時
  `sm.add_message("assistant", full_response)`、ui_event assistant 訊息、
  記錄 `last_full_response`；若 `not slm_enabled or len < threshold` → emit tts
  {"text": full_response, "priority": "medium"}；否則 emit `summary_req`
  {"cmd":"summary","text":full_response,"title":sm.current_title}；最後 ui_event status 待機
  （含空回應時也要 status 待機，見 main.py:375-377）
- `inbound` type=StatusUpdate：ui_event status＋tts low（main.py:379-382）
- `inbound` type=Error：ui_event「[錯誤] {message}」＋tts {"發生錯誤：{message}", high}（main.py:384-387）
- `summary_out` type=status：ui_event status
- `summary_out` type=summary：display=f"回覆摘要：{text}"；ui_event summary 訊息＋tts medium（main.py:213-218）
- `chat_ctl` cmd=play_last：有 last_full_response → ui_event「播放最後一次回覆原文」＋
  tts medium 原文（main.py:138-141）；沒有 → 不動作（與舊版一致）

測試 ≥10：ChatReply 短回覆直接 TTS、長回覆走 summary_req、slm_enabled=False 永遠直接 TTS、
歷史寫入、last_full_response 記錄、空 full_response 只發 status、StatusUpdate、Error、
summary_out 兩型、play_last 有/無內容。用 tempfile SessionManager。

Commit: `feat(階段④): ChatFlow — 聊天回應處理、摘要決策與重播`

---

### Task 2: CommandRouter 接入 chat 工作區與重播

**Files:** Modify `modules/command_router.py`、Modify `tests/test_command_router_workspace.py`（chat 相關案例）、`tests/test_command_router_hotkeys.py`（play_last 案例）

- `play_last`：placeholder 改為 emit `chat_ctl` {"cmd":"play_last"}
- `/clear chat`：`n = self._sm.clear_history()` → 「[系統] chat 工作區（對話歷史）已清空（原含 {n} 筆）。」
  （_sm None 防禦沿用既有模式）
- `/ws` 無參數：chat 行改為顯示真實筆數（len(sm history)；SessionManager 取法 port 自
  workspace_controller handle_ws，_sm None 時顯示 0 或省略）
- `/ws chat`：回「chat 為唯讀檢視：請用 /history 檢視、/clear chat 清空（raw_text 不流入 chat）」
  ——設計決議：chat 不可成為當前工作區
- 更新對應測試（原「階段④接入」佔位斷言改為新行為）

Commit: `feat(階段④): CommandRouter 接入 chat 工作區操作與 play_last 重播`

---

### Task 3: 聊天流整合測試

**Files:** Create `tests/test_chat_flow_integration.py`

全鏈在 Exchange 上（真 ChatFlow＋CommandRouter＋假外設）：

1. /send → outbound → 假 HTTP（裸 queue 形態：收 payload、回 ChatReply dict）→
   inbound → ChatFlow → 歷史含 user+assistant、短回覆 tts 收到 medium
2. 長回覆 → summary_req →（InboxAdapter 進假摘要器輸入 queue）假摘要器
   （裸 queue＋執行緒，輸出 {"type":"summary","text":"摘"}）→ OutboxAdapter →
   summary_out → ChatFlow → tts 收到「回覆摘要：摘」
3. play_last 全鏈：ChatReply 後發 commands "PLAY_LAST_ORIGINAL" →
   CommandRouter → chat_ctl → ChatFlow → tts 收到原文
4. Error 回應 → ui_event 與 tts high（以 InboxAdapter 收 tts/ui_event 驗證）

跑全套件兩次。

Commit: `test(階段④): 聊天流整合測試（HTTP 往返／摘要／重播全鏈）`

---

### Task 4: 文件同步

- `plans/data_tunnel_design.md`：通道表補 `summary_out`、`chat_ctl`、修訂 `inbound` 消費鏈；
  業務邏輯落點補 ChatFlow 細節；設計決議補「chat 不可為當前工作區」
- `docs/architecture.md`：版本標頭階段④；通道表同步；對照表（http_client、
  summary_generator、session_manager 列）；路線圖打勾；測試清單

Commit: `docs(階段④): 設計文件與架構文檔同步聊天流設計`

---

## 完成定義（Definition of Done）

- [ ] ChatFlow 就位；http_client.py、summary_generator.py、session_manager.py 零修改
- [ ] `python3 -m unittest discover -s tests` 全綠（跑兩次）
- [ ] main.py 零修改
- [ ] 文件同步

完成後進入階段⑤（呈現層與 app.py 接線收尾），另寫 `plans/data_tunnel_stage5_plan.md`。
