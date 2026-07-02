# Voice Client 擴展方向調查報告

> 調查日期：2026-07-02　分支：`refactor/data-tunnel`
> 性質：調查報告（investigation），未修改任何程式碼。

## 0. 調查基礎與範圍

本報告基於下列現況整理：

- 架構：Data Tunnel 已全部完成（`docs/architecture.md`），所有模組是掛在 topic 上的
  生產者／消費者，新增能力＝「新增一個 TunnelModule ＋ 一兩條 topic 路由」，
  擴展成本天然偏低。
- 已規劃／已落地（**本報告避開重複提案**）：
  - roadmap：TTS backend 抽象化、`mobile_server.py` 對齊 Data Tunnel。
  - ideas：桌面／手機共用 Data Tunnel 流程。
  - plans：`workspace_unification.md`（工作區統一）、`mobile_improve.md`（手機 UX 細項）。
  - 已落地：Kokoro TTS、GPU large-v3 STT、KDE Wayland `local_control.py`、多工作區與指令路由。
  - 已調查未實作：SenseVoice STT（`docs/sensevoice_investigation.md`）。
- 歷史願景（`ai_assist/roadmap.md`，舊文件）：輸入介面多樣化、沙盒執行、記憶演進、
  混合模型——部分想法在本報告以「符合現架構的形式」重新提出。

提案依「**價值高且成本低**」排序；量級定義：小＝1–2 天、中＝3–7 天、大＝1 週以上。

---

## 1. 全系統語音聽寫模式（把辨識文字打進任何應用程式）⭐ 最推薦

**動機**：目前 STT 文字只能進 Voice Client 自己的工作區。加一個「聽寫模式」，
把辨識文字直接以虛擬鍵盤輸出到當前聚焦的視窗（瀏覽器、編輯器、IDE…），
Voice Client 立刻從「AI 客戶端」升級成「全系統中文語音輸入法」——這是語音優先
定位最自然、也最日常高頻的延伸，且大部分基礎（熱鍵、錄音、GPU STT）都已就緒。

**架構接點**：
- 新 TunnelModule `TypeOutBridge`：消費新 topic `type_out`，呼叫 `wtype`（Wayland）／
  `xdotool type`（X11）輸出文字。
- `modules/stt_gate.py` 新增第三種模式 `dictation`：`stt_text` 進來時分流到
  `type_out` 而非 `raw_text`（現有 normal／command 分流結構直接擴充）。
- `modules/command_router.py`＋`gate_ctl`：新增 `/dict` 指令與熱鍵（KDE 端經
  `local_control.py` 白名單加一個 `DICT_TOGGLE` 命令）。

**量級**：小～中（模式分流與指令是現成模式的複製；主要工作在 wtype/ydotool 的平台差異）。

**風險／前置**：Wayland 下 `wtype` 需 compositor 支援 virtual-keyboard protocol
（KDE Plasma 支援）；`ydotool` 需 daemon 與權限。中文輸出走 `type` 文字而非鍵碼，
避免輸入法干擾。需在 `WAIT_USER.md` 排真人驗收（焦點視窗行為無法自動測試）。

---

## 2. LLM 串流回覆＋分句 TTS（大幅降低「開口延遲」）⭐ 最推薦

**動機**：`http_client.py` 目前是一次性 `chat()`，長回覆要等整段生成完才進 TTS，
體感延遲最痛。改為 streaming，邊生成邊按句切分送 TTS，首句朗讀延遲可從
「整段生成時間」降到 1–2 秒，是單點投入回報最高的體驗升級。

**架構接點**：
- `utils/llm_client.py`：加 `chat_stream()`（OpenAI 相容 API 的 `stream=True`，
  LM Studio／Ollama 都支援）。
- `http_client.py`：本地模式改走串流，按標點切句後逐句放入 `recv_queue`，
  payload 加 `partial: true`／最後一筆 `final: true`（topic 仍是 `inbound`，
  對 Exchange 零改動）。
- `modules/chat_flow.py`：`partial` 句直接 `emit("tts", …)` 與 `ui_event` 增量顯示；
  `final` 時才寫入 session 歷史、記錄 `last_full_response`、做摘要決策。

**量級**：中。

**風險／前置**：摘要決策需要完整回覆——可規定「SLM enabled 時退回非串流」或
「串流完再補摘要」。TTS 佇列已有 priority 與中斷語意，逐句 medium priority 天然排隊；
需確認 `/stop`（F10）能一次清掉整串待播句（`tts_ctl` 可能要加 `flush` 語意）。
測試面：`test_chat_flow*` 與接線測試要補 partial/final 案例。

---

## 3. `/model` 多模型設定檔切換（小成本、日常實用）

**動機**：`config.ini [LLM]` 只有一組模型；使用者實際會在本地小模型（快）與
雲端模型（強，手冊已有 Gemini 範例）間切換，目前得改檔重啟。

**架構接點**：
- `config.ini` 支援多組 `[LLM.profile_name]` 區段。
- `modules/command_router.py` 新增 `/model [名稱]` 指令（列出／切換），經新增的
  `llm_ctl` topic 通知 HttpClient 換 `LLMClient` 實例（HttpClient 已是 adapter 掛載，
  加一條 inbox 即可，或最低成本：直接同步呼叫，如 session_manager 慣例）。
- 語音指令表（`command_handlers/voice.py`）加「換模型」關鍵字。

**量級**：小。

**風險／前置**：幾乎無；注意切換瞬間 in-flight 請求的歸屬（回覆仍標注來源 model 即可，
`ChatReply` payload 已帶 `model` 欄位）。

---

## 4. 語音指令自然語言化（帶參數的語音指令）

**動機**：F7 語音指令目前是關鍵字對照表（說「發送」＝`/send`），無法帶參數——
「切到 stt 工作區」「刪掉第三筆」「開一個叫做週報的對話」都做不到。這是語音優先
客戶端「手不碰鍵盤」路上最明顯的缺口。

**架構接點**：
- 第一階段（規則式，成本極低）：`modules/command_handlers/voice.py` 的解析函式
  擴充為「關鍵字＋參數槽」的正則／模板比對（工作區名、數字、對話名）。
- 第二階段（可選）：接 `[SLM]` 既有的本地小模型做 intent parsing，輸出結構化
  `{cmd, args}` 進 `commands` topic——CommandRouter 完全不用改，因為指令流
  本來就是「生產者只產資料」。

**量級**：第一階段小；第二階段中。

**風險／前置**：SLM 解析有延遲與誤判，需保留規則式 fallback；破壞性指令
（delete／clear）建議先 `ui_event`＋TTS 覆誦確認。

---

## 5. 剪貼簿朗讀與桌面通知通道（小而美的新輸出／輸入口）

**動機**：已有 `utils/clipboard.py` 與完整 TTS 管線，補兩個小指令就多出兩個使用場景：
- `/speak`（或 `/speak clip`）：朗讀剪貼簿或當前工作區內容——「選取任何文章→複製→
  熱鍵朗讀」，等於全系統 read-aloud。
- 桌面通知：LLM 回覆到達時發 D-Bus notification（`notify-send`），視窗不在前景也知道。

**架構接點**：
- `/speak`：CommandRouter 新指令，讀 clipboard 後 `emit("tts", …)`，零新 topic。
- 通知：新的小消費者掛 `ui_event`（`ui_event` 目前單一消費者是 TuiRenderer，
  Exchange 是一 topic 一消費者——可在 TuiRenderer 側 fan-out，或新增 `notify` topic
  由 ChatFlow 同時 emit）。
- KDE 快捷鍵側：`local_control.py` 白名單加 `SPEAK_CLIPBOARD`。

**量級**：小。

**風險／前置**：`ui_event` 單消費者限制是主要設計點（建議走新 topic，不動 Exchange 語意）。

---

## 6. SenseVoice STT 落地（照既有調查施工）

**動機**：`docs/sensevoice_investigation.md` 已完成完整調查：中文準度普遍勝過
Whisper、模型更小（~900MB）、推論快 ~15×、走 `sherpa-onnx` 不引入 torch。
調查結論是「值得做」，只差實作。

**架構接點**：
- `voice_to_text.py` 抽出 STT engine 介面（與 roadmap 的「TTS backend 抽象化」
  同一設計語彙），`config.ini [STT]` 加 `engine = faster_whisper|sensevoice`。
- topic 面零變動（仍是 `audio` → `stt_text`）。

**量級**：中。

**風險／前置**：sherpa-onnx 依賴與模型下載；SenseVoice 輸出含情緒／事件 token 需清洗；
繁體輸出需驗證（Whisper 靠 initial_prompt，SenseVoice 行為不同）。需真人中文驗收
（記入 `WAIT_USER.md`）。

---

## 7. 喚醒詞（wake word）免熱鍵啟動錄音

**動機**：Wayland／SSH／headless 環境熱鍵不可用是文件明載的痛點（CLAUDE.md 特別注意
第 3 條）；喚醒詞（「小助手」）讓錄音啟動完全免鍵盤，也解放手機以外的遠場使用。

**架構接點**：
- 新純生產者模組 `WakeWordListener`（openWakeWord 或 porcupine，均可 CPU 常駐、
  低功耗）：偵測到喚醒詞→ `emit("commands", {cmd: "record_toggle"})`——與熱鍵
  完全同一條指令流，CommandRouter 零修改。
- 麥克風佔用需與 `record.py` 協調：喚醒偵測期間持續開 mic，觸發後把控制權交給
  Recorder（或共用同一條 PyAudio stream，由新模組分流 frame）。

**量級**：中（模型接入小，麥克風共用協調是主要工作）。

**風險／前置**：誤觸發率需實測調閾值；中文自訂喚醒詞在 openWakeWord 需自行訓練
（可先用英文內建詞驗證管線）；與 Recorder 的裝置爭用是真正的設計工作。
硬體驗收必須真人（`WAIT_USER.md`）。

---

## 8. 對話長期記憶（本地 embedding 檢索）

**動機**：`http_client._call_local()` 目前只帶最近 6 筆訊息當上下文；跨對話、
跨天的內容完全失憶。本地 embedding（如 sentence-transformers ONNX 或
Ollama embedding API）對 `session_manager` 全部歷史建索引，送 LLM 前檢索相關片段
注入 context——舊 roadmap「記憶與知識演進」的現代化落法。

**架構接點**：
- 新模組 `MemoryStore`：訂閱 `inbound`（見第 5 點的單消費者議題，建議由 ChatFlow
  emit 新 topic `memory_write`）；HttpClient 組 payload 前查詢（同步呼叫即可，
  比照 session_manager 慣例）。
- 儲存：SQLite＋向量欄位（sqlite-vec）或純 JSON＋numpy，維持零重依賴風格。

**量級**：中～大。

**風險／前置**：embedding 模型選型（中文品質）；context 注入格式影響 LLM 行為需迭代；
先做 `/recall <關鍵字>` 手動檢索版可把量級降到中。

---

## 9. 外掛（plugin）機制：第三方 TunnelModule 自動掛載

**動機**：Data Tunnel 架構本質上就是 plugin bus——模組只認識 topic，不認識彼此。
補一個發現／掛載機制，第三方就能用一個檔案加入新能力（新輸入源、新指令、
新輸出通道），而不用改 `app.py`。

**架構接點**：
- 約定 `plugins/` 目錄或 entry-points：每個外掛提供
  `create(config) -> TunnelModule`，宣告 `consumes`／產出 topic。
- `app.py` 接線階段掃描並統一 `attach()`＋`start()`（現有「先 attach 再 start」
  慣例直接沿用）。
- 需要一份 topic 協定文件版本化（`docs/architecture.md` 的 topic 表升格為 contract）。

**量級**：中。

**風險／前置**：topic 命名衝突與「一 topic 一消費者」限制要有明確錯誤訊息；
壞外掛的錯誤隔離框架已內建（`handle()` 例外不斷迴圈）。建議等 1–2 個內部功能
（如本報告的 TypeOutBridge、通知）先以「準外掛」形式寫，再定介面。

---

## 10. 手機＝桌面遙控器（跨裝置同一會話）

**動機**：目前 `mobile_server.py` 是獨立入口、獨立流程，手機和桌面是兩個世界。
roadmap 已排定「mobile 對齊 Data Tunnel」；對齊完成後再往前一步：手機 WebSocket
變成桌面 Exchange 的一對遠端 producer/consumer——手機錄音進桌面 GPU STT、
手機看桌面 TUI 同步的對話、手機按鈕＝桌面熱鍵，真正的跨裝置單一會話。

**架構接點**：
- FastAPI WebSocket handler ↔ `core/adapter.py` 式橋接：手機上行→
  `commands`／`raw_text`／`audio`，下行訂閱 `ui_event`（同樣受單消費者議題約束，
  需 fan-out 設計）。
- `static/app.js` 已有 WebSocket 基礎，改造成本集中在後端。

**量級**：大。

**風險／前置**：**硬前置＝roadmap 的 mobile 對齊案**；`ui_event` fan-out、
斷線重連與多客戶端語意是主要設計工作；完成後可一併移除
`text_accumulator.py`／`workspace_controller.py`（架構文件已排定的清理）。

---

## 11. LLM 工具呼叫／代理能力（長線）

**動機**：舊 `ai_assist/roadmap.md` 的核心願景（沙盒執行、動態提權）。讓 LLM 回覆
不只被朗讀，還能觸發動作：查檔、開網頁、控制 Voice Client 自身
（「幫我把這段存到 stt 工作區」）。

**架構接點**：
- `utils/llm_client.py` 加 OpenAI tools 參數；`http_client.py` 處理 tool_call 迴圈。
- 最安全的第一步：**工具只映射到既有 `commands` topic 指令集**——LLM 產生的動作
  走與熱鍵完全相同的受控通道，天然白名單；再考慮外部工具與沙盒。

**量級**：大（限指令集版可降為中）。

**風險／前置**：本地小模型 tool-calling 可靠度參差；任何檔案／系統級工具都需要
確認機制（TTS 覆誦＋語音確認可以是特色而非負擔）；沙盒執行是獨立大案。

---

## 12. 其他小型改善（挑著做）

| 項目 | 動機 | 接點 | 量級 |
|---|---|---|---|
| 錄音裝置選擇＋TUI 音量表 | 多麥克風機器選錯裝置難排查 | `record.py`（device index）、`recorder_event`→TUI | 小 |
| `/export md`（Markdown／Obsidian 匯出） | 對話沉澱為筆記 | `command_handlers/session.py` | 小 |
| TTS 合成快取 | 重複片語（狀態語、摘要開頭）免重算 | `text_to_voice.py` worker 前加 LRU | 小 |
| 串流 STT 增量顯示 | 邊講邊出字的即時感 | `record.py` 已有切片；STT 分段 emit `stt_text` partial | 中～大 |
| 每日對話自動歸檔＋統計 | 使用量回顧 | `session_manager.py` | 小 |

---

## 13. 建議優先順序（價值／成本綜合）

1. **全系統語音聽寫模式**（§1）——高頻日常價值、架構現成、量級小～中。
2. **LLM 串流回覆＋分句 TTS**（§2）——最痛的延遲問題、單點高回報、量級中。
3. **`/model` 多模型切換**（§3）——量級小、立即實用。
4. **語音指令帶參數（規則式第一階段）**（§4）——量級小、補齊語音優先體驗缺口。
5. **剪貼簿朗讀＋通知**（§5）——量級小、開出兩個新使用場景。
6. **SenseVoice STT 落地**（§6）——調查已完成、中文準度直接受益。
7. 中長線依序：喚醒詞（§7）→ 長期記憶（§8）→ plugin 機制（§9）→
   手機遙控（§10，前置 mobile 對齊）→ 工具呼叫（§11）。

若要進入正式規劃管線，建議把 1–2 先送 `workflows/roadmap/README.md`，
其餘留在 `workflows/idea/ideas.md` 醞釀。
