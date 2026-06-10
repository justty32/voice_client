# 資料隧道（Data Tunnel）重構設計

日期：2026-06-10
分支：`refactor/data-tunnel`
狀態：設計定案，待實作計畫

## 背景與動機

目前 `main.py`（487 行）是一個中央路由器，輪詢所有佇列並混雜大量業務邏輯
（指令處理、回應路由、語音指令解析）。模組之間的佇列接線分散且難以追蹤。

重構目標：把整個系統改建為「生產者／消費者＋佇列」的資料隧道架構。
**先建框架本體（不含任何業務邏輯），再把各工作流逐一掛上去。**

## 核心設計決策（已與使用者確認）

1. **多佇列、多生產者、多消費者**：不是單一中央佇列，而是多條具名通道（Channel），
   每條通道可掛多個生產者；消費端採工作佇列語意——每筆資料只被一個消費者取走。
2. **框架優先**：第一步先完成框架本體＋測試，之後的工作流都建立在框架之上。
3. **資料交換是單執行緒的**：框架核心是一個單執行緒交換迴圈（Exchange），
   每次 tick 只做一個動作——「從某佇列取出一筆」或「放入某佇列一筆」，一次交換一筆資料。
   所有佇列之間的搬移只由這一個執行緒執行，沒有競態問題，且資料流向可在單點完整記錄。
4. **生產者／消費者可以是長駐執行緒**：錄音器、STT、TTS 等模組在自己的執行緒持續工作；
   它們只透過自己的 outbox（生產）與 inbox（消費）跟交換核心介接。
5. **模組可同時身兼生產者與消費者**：例如 STT 消費 `audio`、生產 `raw_text`；
   CommandRouter 消費 `commands`、生產控制與 UI 訊息。
6. **raw_text 只有一個消費者**：當前作用中的 buffer 工作區。多個工作區並存，
   但只有被指令選中的「當前工作區」會收到新的原始辨識文字。
   不再自動寫入 stt 工作區、不自動轉發——後續動作一律靠明確指令。
7. **熱鍵與斜線指令也是生產者**：KeyboardListener、終端輸入、語音指令辨識
   都只負責把「指令資料」生產進 `commands` 通道，由 CommandRouter 統一消費處理；
   熱鍵不再直接操控錄音器或 TTS。
8. **範圍為桌面 TUI 全管線**；`mobile_server.py` 暫不重構（非目標），日後再對齊新框架。

## 框架本體（core/）

```
core/
  message.py    Message：topic、payload、source、時間戳
  endpoint.py   Outbox / Inbox：模組與交換核心的唯一介接點
  exchange.py   Exchange：單執行緒交換迴圈＋路由表（topic → 消費者 inbox）
                ※「通道」即路由表中的 topic 註冊，不需獨立的 channel 類別
  module.py     TunnelModule 基底類別：宣告 consumes，管理自身執行緒
```

### 交換核心（Exchange）語意

- 路由表：`topic → 目標 inbox`（每個 topic 一個消費者；消費者內部可再細分，
  例如 WorkspaceManager 收 `raw_text` 後塞進「當前」工作區）。
- 主迴圈每次 tick：輪詢各生產者 outbox，**一次只搬一筆**到對應 inbox；
  無資料時短暫休眠。
- 每筆搬移可記錄 log（topic、來源、摘要），整個系統的資料流在單點可觀測。
- 消費者處理中拋出例外不得影響交換迴圈；模組執行緒自行 try/except 並把錯誤
  生產為 `ui_event` 訊息。

## 通道（topic）規劃

| topic | 生產者 | 消費者 |
|---|---|---|
| `audio` | Recorder | STT |
| `raw_text` | STT、終端文字輸入 | WorkspaceManager（塞進當前工作區） |
| `commands` | 終端斜線指令、語音指令辨識、熱鍵 | CommandRouter |
| `recorder_ctl` | CommandRouter | Recorder |
| `tts_ctl` | CommandRouter | AudioPriorityPlayer |
| `outbound` | CommandRouter（/send） | HttpClient |
| `inbound` | HttpClient | ChatFlow |
| `summary_req` | ChatFlow | SummaryGenerator |
| `tts` | ChatFlow、SummaryGenerator、CommandRouter | AudioPriorityPlayer |
| `ui_event` | 所有模組 | TuiRenderer |

## 工作流（掛在框架上）

1. **語音資料流**：Recorder →`audio`→ STT →`raw_text`→ 當前工作區。
2. **指令流**：熱鍵／終端／語音指令 →`commands`→ CommandRouter
   →（`recorder_ctl`、`tts_ctl`、`ui_event`、`outbound`…）。
   現有 main.py 的 `_route_cli_cmd`、`_handle_voice_command` 邏輯全部搬進 CommandRouter。
3. **聊天流**：CommandRouter 的 /send 把當前 buffer 內容組 payload →`outbound`→
   HttpClient →`inbound`→ ChatFlow（寫入 SessionManager 歷史、依摘要門檻決定
   直接 `tts` 或發 `summary_req`）。
4. **呈現**：`ui_event`→ TuiRenderer；`tts`→ AudioPriorityPlayer。

業務邏輯落點：

- **WorkspaceManager**：持有多個 workspace 與「當前」指標（吸收現有
  WorkspaceController 與 TextAccumulator 的職責）。
- **CommandRouter**：所有斜線指令、語音指令、熱鍵指令的唯一處理者。
- **ChatFlow**：對話歷史與摘要決策（吸收 main.py 的 `_route_response`）。

## 錯誤處理

- 交換迴圈永不因單筆資料失敗而停止；搬移失敗記 log 後丟棄該筆。
- 模組執行緒包 try/except，錯誤轉為 `ui_event`（沿用現行「[錄音錯誤] …」風格）。
- 關機：Exchange 提供 stop()；app.py 統一停模組、停交換迴圈。

## 測試策略

- **框架單元測試**：Channel 進出、Exchange 路由正確性、一次一筆語意、
  停止／例外不中斷、模組基底類別生命週期。
- **消費者測試**：以假 inbox/outbox 餵資料，驗證各消費者行為（沿用現有 tests/ 風格）。
- **整合測試**：模擬「文字進 raw_text → 當前工作區收到」「指令進 commands →
  ctl 訊息產出」等端到端流。

## 遷移階段（每階段可獨立運作、有測試）

- **階段①**：core/ 框架本體＋單元測試（不接任何業務模組）。
- **階段②**：語音資料流遷移——Recorder、STT、WorkspaceManager 掛上框架。
- **階段③**：指令流遷移——終端、熱鍵、語音指令改為生產者；CommandRouter 上線。
- **階段④**：聊天流遷移——HttpClient、ChatFlow、SummaryGenerator。
- **階段⑤**：呈現層收尾——TuiRenderer、TTS 控制；刪除舊 main.py 路由，
  `app.py` 成為唯一入口（或 main.py 縮減為純接線）。

## 非目標

- `mobile_server.py` 的重構（日後另案對齊新框架）。
- 跨行程通道（佇列僅在本行程內；「送往其他行程」未來可作為一個消費者模組實作）。
- 新功能——本次純重構，對使用者可見行為除「raw_text 不再自動寫入 stt 工作區」外不變。
