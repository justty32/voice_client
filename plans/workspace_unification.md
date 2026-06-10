# 工作區統一抽象與指令重構規劃

## 0. 核心願景

把整個 Voice Client 重新理解成一件事：**對三個「工作區（Workspace）」做 CRUD**。

每個工作區都是同一種資料結構 —— `List[List[str]]`（一個有序清單，裡面每一筆 entry 又是一串字串）：

| 工作區 | 代號 | 每筆 entry 代表 | 目前對應元件 |
|--------|------|----------------|--------------|
| 原始語音文字 | `stt` | 一次語音辨識的逐段文字（segments） | （目前不存在，被 join 後丟進 buffer） |
| 暫存緩衝 | `buffer` | 一筆待送暫存（CLI 一行或一段語音） | `TextAccumulator._buffer`（扁平 `List[str]`） |
| 對話 | `chat` | 一則訊息 `[role, content, timestamp]` | `SessionManager` 的 `history`（`List[dict]`） |

所有斜線指令，本質上就是這三個工作區上的 CRUD（建立 / 讀取 / 更新 / 刪除 / 重排 / 匯出入 / 送出）。目前三者**資料形狀不同、指令各搞各的、且沒有共用抽象**，這份文件規劃如何收斂。

> 基礎程式已建立：`workspace.py`（`Workspace` 類別）+ `tests/test_workspace.py`（25 項單元測試，全綠）。

---

## 1. 現況與落差

| 工作區 | 現況 | 落差 |
|--------|------|------|
| `stt` | STT segments 在 `voice_to_text._transcribe()` 被 `"".join()` 併成單一字串，直接送進 buffer | **完全不存在為可操作的清單**，無 CRUD、無法回看原始逐段文字 |
| `buffer` | `TextAccumulator._buffer: list[str]`，CRUD 最完整（append/peek/clear/concat/to_top/export/import/flush） | 型別是扁平 `List[str]`，非 `List[List[str]]` |
| `chat` | `SessionManager.history: list[dict]`，CRUD 在 *session* 層（new/switch/delete/rename/save/load/history） | 型別是 `List[dict]`；指令命名與 buffer 那套完全不同 |

**根本問題**：三套資料形狀 + 三套指令語意，沒有共用抽象 —— 這正是「指令實作不夠完善」的來源。

---

## 2. `Workspace` 抽象（已實作）

`workspace.py` 提供統一 CRUD API：

| 類別 | 方法 | 說明 |
|------|------|------|
| Create | `append(entry) -> int`、`extend(entries) -> int` | 傳入 `str` 會正規化為單元素 entry `[str]` |
| Read | `read_all()`、`read(i)`、`count()`、`is_empty()` | 一律回傳複本 |
| Update | `replace(i, entry)`、`concat_all(seg_sep)`、`move(i, j)`、`move_to_top(i=-1)` | `concat_all` 對應舊 `/concat`；`move_to_top` 對應舊 `/to_top` |
| Delete | `delete(i)`、`clear() -> int` | |
| Serialize | `to_list()`、`from_list(name, data)`、`flatten(seg_sep, entry_sep)`、`lines(seg_sep)` | `from_list` 同時吃新 `List[List[str]]` 與舊 `List[str]` |
| Persist | `export(path, seg_sep)`、`import_file(path, append=True)` | 支援 `.json` / `.txt` |

**相容性已內建**：舊的扁平 `List[str]`（buffer 匯出檔、`_buffer_temp.json`）載入時自動升級為 `[[s], ...]`。

---

## 3. 三個工作區的 entry 語意與持久化

- **`stt`**：`VoiceToText` 改為回傳 segments 清單（`list[str]`），每次辨識 `append` 成一個 entry。下游若只要整句，用 `entry` 的 `" ".join`。記憶體保存即可（可選擇性 export），程式結束不必持久化。
- **`buffer`**：`TextAccumulator` 內部改持有一個 `Workspace`。CLI 一行 → `["..."]`；語音一段 → segments。`flush` = `flatten(seg_sep=" ", entry_sep=" ")`。對外指令輸出格式維持不變。
- **`chat`**：每筆訊息存成 `[role, content, timestamp]`（皆字串）。`SessionManager` 的 `history` 由 `List[dict]` 改為 `List[List[str]]`（即 `Workspace.to_list()` 格式）。
  - **遷移**：`_load()` 偵測舊格式（history 內為 dict）時，逐筆轉成 `[role, content, timestamp]`。
  - **下游更新**：`http_client._call_local()` 的 `msg["role"]/msg["content"]` 改為 `msg[0]/msg[1]`；`get_history()` 同步調整。

---

## 4. 指令統一設計

### 4.1 當前工作區（current workspace）

新增一個「當前作用工作區」指標，預設 `buffer`。統一 CRUD 指令一律作用在它身上。

- `/ws` — 列出所有工作區、目前作用中者、各自筆數。
- `/ws <name>` — 切換當前工作區（初期 name ∈ `stt|buffer|chat`；未來透過 registry 擴充，見 §7）。

### 4.2 對當前工作區的統一 CRUD

| 指令 | 動作 | 對應 Workspace 方法 |
|------|------|---------------------|
| `/show`（別名 `/peek`） | 列出內容（含 1-based 編號） | `lines()` |
| `/clear` | 清空當前工作區（`/clear <名稱>` 清指定、`/clear ui` 清畫面） | `clear()` |
| `/del <i>` | 刪除第 i 筆 | `delete(i-1)` |
| `/move <i> <j>` | 把第 i 筆移到第 j 位 | `move(i-1, j-1)` |
| `/totop [i]` | 把第 i 筆（預設最後一筆）移到最前 | `move_to_top()` |
| `/concat` | 壓縮為單一筆 | `concat_all()` |
| `/export <file>` / `/import <file>` | 匯出入檔案 | `export()` / `import_file()` |
| `/copy` / `/paste` | 與系統剪貼簿交換（見 §4.6） | `flatten()` / `append()` |
| `/send` | flush 送出（**僅當前為 `buffer` 時有效**，見 §4.3） | `flatten()` |

### 4.3 待定案：與舊指令的衝突

重構會碰到三個既有指令的語意衝突，**需先定案**（文件先列出建議）：

1. **`/clear`**：舊行為 `/clear` = 清 UI 畫面、`/clear buffer` = 清暫存。
   - **定案**：`/clear` = 清**當前工作區**。
     - `/clear` → 清當前工作區。
     - `/clear <stt|buffer|chat>` → 清指定工作區（`/clear buffer` 行為與舊版相同，仍有效）。
     - `/clear ui` → 清 UI 畫面（原 `/clear` 的清畫面功能改為明確指令）。
   - 影響：原本「無參數 `/clear` 清畫面」的行為改變，需同步更新 `/help`、語音指令（「清除畫面」→ `/clear ui`）、手機端與 `app.js`。
2. **`/delete <title>`**：舊行為 = 刪除 session（屬 chat 工作區集合的操作）。
   - 建議：session 層維持 `/delete <title>`；工作區內單筆刪除用新指令 `/del <i>`，避免撞名。
3. **`/send`**：目前只對 buffer 有意義。
   - **定案**：`/send` **僅在當前工作區為 `buffer` 時有效**，行為與現在相同（flush buffer 送出）。
   - 當前為 `stt` 或 `chat` 時 → 不執行，提示「`/send` 僅適用於 buffer 工作區」。
   - （`stt → buffer` 的搬移交給 §4.2 的 `/move`/匯出入或未來的 promote 指令，不綁在 `/send`。）

### 4.4 Session = chat 工作區的集合

釐清層級：**chat 其實是「多個 chat 工作區」**，每個 session 是一個 chat 工作區。Session 層指令是「工作區集合」上的 CRUD，維持既有命名：

- `/new`、`/switch`、`/list`、`/rename`、`/save`、`/load`、`/history`、`/delete <title>`。

### 4.6 剪貼簿支援

統一指令 `/copy`、`/paste` 作用在**當前工作區**，與系統剪貼簿交換文字：

- `/copy`：把當前工作區內容（每筆一行，以換行串接）複製到系統剪貼簿。
  - buffer → 透過 acc 佇列在其執行緒內複製；stt/chat → 控制器直接複製（chat 複製對話歷史文字）。
- `/paste`：把剪貼簿文字貼到當前工作區（每個非空行為一筆，追加至末尾）。
  - buffer / stt 支援；chat 不支援貼上（提示切換工作區）。
- 跨平台後端（`utils/clipboard.py`）：優先 `pyperclip`，否則退回 `pbcopy/pbpaste`（mac）、
  `clip`/`Get-Clipboard`（Win）、`wl-copy/wl-paste` 或 `xclip` 或 `xsel`（Linux）。
  全不可用時**優雅降級**：提示安裝方式，不崩潰。
- 手機端（mobile）的剪貼簿改用瀏覽器 `navigator.clipboard`，於 ④c 處理（與桌面後端不同機制）。

### 4.5 相容性原則

- 舊指令全部保留為別名，行為在「當前工作區 = buffer」時與現在完全一致。
- 統一新指令（`/ws`、`/del`、`/move`、`/totop`）以**新增**方式加入，不移除舊指令。
- 桌面（`main.py`）、手機（`mobile_server.py` + `static/app.js`）、語音指令（`_handle_voice_command`）三處的指令表同步更新。

---

## 5. 分階段遷移計畫

| 階段 | 內容 | 風險 | 驗證 |
|------|------|------|------|
| ① ✅ | `workspace.py` + 單元測試 | 無（純新增） | `python3 -m unittest tests.test_workspace` |
| ② | `TextAccumulator` 改用 `Workspace` 承載 buffer，對外行為不變 | 低 | 新增 `tests/test_text_accumulator.py`（flush/concat/to_top/export/import 行為對照舊版） |
| ③ | `SessionManager` history → `List[List[str]]`，加舊格式遷移；更新 `http_client._call_local`、`get_history` | 中（動到核心 chat/LLM） | 新增 `tests/test_session_manager.py`（含舊 `.sessions.json` 遷移、`add_message`/`get_history` 對照） |
| ④a ✅ | `stt` 工作區 + 「當前工作區」+ `/ws` + ws 感知 `/show`/`/clear`/`/send`（TUI）；含剪貼簿 `/copy`/`/paste` | 中 | `tests/test_workspace_controller.py`、`test_clipboard_commands.py` |
| ④b ✅ | `/del`/`/move`/`/to_top`/`/concat`/`/export`/`/import` 改為當前工作區感知（buffer/stt/chat）（TUI） | 中 | 控制器 + accumulator + session 訊息編輯測試 |
| ④c | 把 ④a/④b + 剪貼簿全部對齊到手機端（`mobile_server.py` + `app.js`，剪貼簿走 `navigator.clipboard`），語音指令一致 | 中 | 手動煙霧測試 |

每階段獨立 commit、可獨立回退。目前全測試 116 綠（`python3 -m unittest discover -s tests`）。

---

## 6. STT 引擎遷移（未來）

> 背景：規劃將現用的 `faster-whisper` STT 引擎遷移至其它實作。

`stt` 工作區正好提供**乾淨的接縫（seam）**讓引擎與下游解耦：

- 下游（buffer / 顯示 / 送出）只依賴「`stt` 工作區裡的 `list[str]` entry」，不依賴任何具體 STT 引擎。
- 遷移時**只需替換 `voice_to_text.py` 的實作**，對外契約不變：吃 WAV `BytesIO` → 產出 `list[str]` segments → `append` 進 `stt` 工作區。
- 建議把引擎選擇做成設定（`[STT] engine = faster-whisper | ...`），`VoiceToText` 內以 strategy 模式切換，介面統一回傳 segments。
- 遷移檢核點：辨識延遲、segment 切分行為、語言/標點、資源佔用（CPU/GPU/記憶體）、模型載入時間。

---

## 7. 未來方向：可擴展的工作區數量與型別

> 現在**不實作**，只在設計上預留，避免把「正好三個」寫死。

目前先以三個固定工作區（`stt` / `buffer` / `chat`）落地，但抽象層要能自然長大：

- **數量可變（N 個工作區）**：`Workspace` 本身已用 `name` 識別、彼此獨立，天生支援任意多個。未來引入一個 **`WorkspaceRegistry`**（名稱 → `Workspace` 的對照表）統一管理註冊、查詢、列舉、切換「當前工作區」，指令層一律對 registry 操作，不寫死三個。
- **型別可變（多種工作區型別）**：未來可能有不同「種類」的工作區（例如唯讀的 STT、可送出的 buffer、有 role 結構的 chat、或全新型別如「待辦」「片段庫」「檔案草稿」）。預留作法：
  - 在 `Workspace` 上加一個 `kind`/`policy` 屬性，描述其能力（可否 `send`、是否唯讀、entry 是否有固定欄位語意如 `[role, content, ts]`）。
  - 統一 CRUD 指令依 `policy` 決定可用動作（例如 chat 不允許 `/send`、stt 的 `/send` 為 promote）。
  - 需要特化行為時用子類別（如 `ChatWorkspace`）覆寫，但對外維持同一套 CRUD 介面。
- **動態建立/銷毀**：未來可允許使用者動態 `/ws new <name> [kind]`、`/ws drop <name>`，session 即是「動態建立的 chat 型別工作區」的特例。

設計守則：第 4 節的統一指令層**一律透過 registry + 當前工作區指標運作**，這樣從「3 個固定」擴張到「N 個、多型別、可動態增減」時，指令層不需重寫，只需擴充 registry 與 policy。

---

## 8. 維護注意事項

- **相容性**：舊 `.sessions.json`、舊 buffer 匯出檔、`_buffer_temp.json` 都必須能載入（已在 `Workspace.from_list` / `import_file` 處理扁平格式）。
- **測試**：資料層（Workspace / TextAccumulator / SessionManager）可在無音訊/無 LLM 環境下用 `unittest` 驗證；CI/SessionStart hook 可掛 `python3 -m unittest discover tests`。
- **不破壞既有 UX**：所有變更以「新增 + 別名」為主，舊操作習慣不變。
- **單一使用者假設**：mobile server 為單使用者；「當前工作區」為全域狀態，與此一致。
