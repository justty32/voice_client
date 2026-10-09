> 封存 2026-10-09，已全部落地（見 workflows/feature-dev/landed/README.md）
# 階段 3：共享狀態加鎖、原子落盤、同名對話不覆蓋

[總覽](README.md)｜痛點 2；B3、B4、B5、P2

## 目標

`Workspace` 與 `SessionManager` 被多條執行緒直接呼叫（`wf/architecture/layering.md` §4）。本階段不改協定、不改接線，
以 `RLock` 保護複合操作、以 temp＋`os.replace` 原子寫檔、壞檔先備份再重置，並把 `/send` 的「讀＋清」做成單一原子操作。
附帶處理 B5（同名覆蓋），依 D5 預設。

## 動到的檔案

- `workspace.py`：
  - `__init__` 建 `self._lock = threading.RLock()`；所有公開方法（append／extend／read_all／read／count／is_empty／replace／concat_all／move／move_to_top／delete／clear／to_list／flatten／lines／export／import_file／`__len__`）以 `with self._lock:` 包住。
  - 新增 `drain(seg_sep=" ", entry_sep=" ") -> str`：鎖內 `flatten` 後 `clear`，回傳字串（空工作區回 `""`）。
- `modules/command_handlers/workspace.py:187-188`：`_handle_send` 改用 `ws.drain(seg_sep=" ", entry_sep=" ")`；其餘判斷不變（空字串仍回「緩衝區是空的」）。
- `session_manager.py`：
  - `self._lock = threading.RLock()`；`new_session／switch_session／list_sessions／get_current_session／add_message／message_count／clear_history／_apply_history_op／delete_session／save_session_to_file／load_session_from_file／rename_session／get_history／current_title` 鎖內執行（`RLock` 允許內部互呼）。
  - `_save_sessions`（79-85）：寫到 `f"{path}.tmp"` 後 `os.replace(tmp, path)`。
  - `_load`（40-42）：解析失敗時先 `os.replace(path, f"{path}.corrupt-{YYYYmmdd_HHMMSS}")` 並 `log.error`，再以空集合啟動；**不刪任何檔**。檔案目前沒有 logger，加 `log = logging.getLogger(__name__)`。
  - `new_session`（89-98）【改行為 B5，D5】：`title in self._sessions` → 回 `None`、不改任何狀態；否則同現行。
- `modules/command_handlers/session.py:7-11`【改行為 B5】：
  - 無參數時標題改為第一個未用的 `session_N`（N 從 1 起）；
  - `new_session` 回 `None` → `_ui_msg(f"對話已存在: {title}（未覆蓋，請用 /switch）")`。
- `mobile/inputs.py:96-100`【改行為 B5】：同樣處理回 `None` 的情形與自動編號（手機在 7b 前仍是獨立實作，先對齊這一點避免手機覆蓋資料）。
- `http_client.py:109`：`get_current_session()` 回傳的是內部 dict 參照；鎖只保護呼叫本身，迭代 `history[-6:-1]` 仍可能與 `add_message` 交錯。
  最小修法：`SessionManager.get_current_session()` 改回 **深複本**（`copy.deepcopy`）。先 `rg -n "get_current_session" --type py` 確認所有呼叫者都只讀（`mobile/`、`http_client.py`、`session_manager.py` 內部），內部寫入改用私有 `_current()`。

## 新增測試

- `tests/test_workspace_concurrency.py`：
  - 4 條執行緒各 `append` 500 筆、主執行緒反覆 `drain()` 收集；結束後「收集到的 entry 數＋殘留數」== 2000（修前會丟）。
  - 併發 `append` 與 `concat_all`：所有字串片段總數不變。
  - `drain()` 單元：空 → `""`；非空 → 回傳攤平字串且 `count()==0`。
  - 執行時間 < 3 秒。
- `tests/test_session_manager.py` 追加：
  - 4 執行緒各 `add_message` 50 次 → 檔案可 `json.load`、`message_count()==200`，且目錄中沒有殘留 `.tmp`。
  - 寫入壞 JSON 後初始化 → 出現 `.sessions.json.corrupt-*`、`list_sessions()==[]`。
  - `new_session("default")` 兩次 → 第二次回 `None`、歷史不變。
  - `get_current_session()` 回傳的 dict 修改不影響內部。
- `tests/test_command_router_session_manage.py` 追加：`/new`（無參數）在已有 `session_1` 時建立 `session_2`；`/new default` 回「已存在」且 default 歷史不變。
- `tests/test_command_router_workspace_transfer.py`：既有 `/send` 案例應不需改；若有 mock `flatten/clear` 的案例改為 `drain`。

## 步驟

1. 先加 `Workspace` 鎖與 `drain()`＋測試 → 綠。
2. `_handle_send` 改 `drain` → 既有 router 測試綠。
3. `SessionManager` 鎖＋原子寫＋壞檔備份＋深複本 → 測試綠。
4. B5：`new_session`、桌面 handler、手機 handler → 測試綠。
5. CODE_MAP、`docs/architecture/runtime.md` 補「共享物件以 RLock 保護；sessions 檔原子寫入」。

## behavior-preserving

鎖、原子寫、`drain`、深複本：是（對單執行緒呼叫者語意不變）。
壞檔備份：**否**——以前壞檔被覆蓋，現在留下 `.corrupt-*`（只多不少）。
B5：**否**——`/new 既有名稱` 不再清空歷史；自動編號不再碰撞。

## 驗證命令

```bash
.venv/bin/python -m pytest -q                               # 全綠；≥ 上階段 + 至少 9
.venv/bin/python -m pytest -q tests/test_workspace_concurrency.py tests/test_session_manager.py
rg -n "Lock" workspace.py session_manager.py                # 各至少 1 行
```

## 需同步的文件

- CODE_MAP：`workspace.py`、`session_manager.py` 描述加「執行緒安全」；測試清單加新檔。
- `docs/architecture/runtime.md` §7：新增「共享物件」一段。
- `docs/user_manual/commands.md`：`/new` 同名時的訊息、自動編號規則。
- `docs/user_manual/troubleshooting.md`：sessions 檔損毀時會備份成 `.corrupt-*`。

## Done when

- `tests/test_workspace_concurrency.py` 存在；pytest 全綠且測試數 ≥ 390。
- `rg -n "os.replace" session_manager.py` ≥ 2 行（原子寫、壞檔備份）。
- `rg -n "\.drain\(" modules/command_handlers/workspace.py` 命中 1 行。
- 手動：`printf 'garbage' > /tmp/x/.sessions.json` 後以該路徑建 `SessionManager` → 目錄出現 `.corrupt-*`。

建議 commit：`fix(狀態): Workspace／SessionManager 加鎖與原子落盤；/new 同名不覆蓋`
