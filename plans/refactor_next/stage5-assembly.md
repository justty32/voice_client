# 階段 5：組裝與生命週期

[總覽](README.md)｜痛點 5；P6；`wf/architecture/layering.md` §3、`dataflow.md` §6

## 目標

把 `app.py:main()` 裡三份手寫清單（建構 99-118、start 151-167、stop 204-218）與散在 `app.py`／`mobile/state.py` 的設定解讀，
收成可測試、可被手機重用的組裝函式；legacy 模組 `stop()` 補 join。`app.py` 回到「接線層」。全程 behavior-preserving（啟停順序不變）。

## 動到的檔案

新增：

- `app_wiring/settings.py`（純函式，無副作用以外的 I/O）：
  - `ensure_default_session(sm)`：`app.py:89-91` 與 `mobile/state.py:33-35` 的共同邏輯。
  - `export_dir_from(config) -> str`：`app.py:93-96`／`mobile/state.py:42`。
  - `slm_settings(config) -> tuple[int, bool]`：`(summary_threshold, enabled)`，`app.py:115-116`／`mobile/state.py:45-46`。
- `app_wiring/assembly.py`：
  - `@dataclass CoreParts`：`queues: dict[str, queue.Queue]`（鍵名＝`wire()` 的 `legacy_queues` 鍵，含階段 4 的 `stt_event`）、`native: dict`（`wm/stt_gate/command_router/chat_flow/cli_text_bridge`）、`exchange`、`app_ctl`、`session_manager`、`export_dir`。
  - `build_core(config, *, session_manager=None, exchange=None) -> CoreParts`：建 queue → SessionManager（未傳入時）＋`ensure_default_session` → 原生模組 → `Exchange()` → `wire()`。**不匯入任何硬體／網路模組**，所以在 `.venv` 無 pyaudio 也能呼叫。
  - `class Lifecycle`：`add(name, obj)` 依序登記、`start_all()` 依序 `start()`、`stop_all()` **倒序** `stop()`，每個 `stop()` 例外只 log 不中斷；`started` 清單可查。
- `tests/test_app_assembly.py`、`tests/test_lifecycle.py`。

修改：

- `app.py:main()`：改為 `parts = build_core(config)`；legacy 元件以 `parts.queues[...]` 建構；用一個 `Lifecycle`，登記順序＝現行 start 順序
  （9 個 legacy → 5 個原生 → exchange）；停機 `tts_cmd_queue.put(TTS_TERMINATE)` 後 `lifecycle.stop_all()`。
  **注意**：現行 stop 順序是「建構順序」而非倒序（`app.py:204-218`）；改成倒序＝先停 exchange？不行——倒序會先停 Exchange 再停模組，outbox 殘留更多。
  為保持行為，`Lifecycle.stop_all()` 預設**正序**（與現行一致），提供 `reverse=True` 選項但本階段不用；是否改倒序留給日後 drain 設計。
- 啟動提示（`app.py:172-185`）保留在 `main()`（它是呈現文字且要讀 `keyboard_listener.is_active()`），但改經 `parts.queues["ui_event_q"]`。
- legacy `stop()` 補 join（`timeout=1`）：`record.py:50-51`、`voice_to_text.py:39-40`、`http_client.py:57-58`、`summary_generator.py:41-42`、`tui_renderer.py:32-33`、
  `text_to_voice.py:97-100`（dispatcher thread）。`terminal_input.py:24-25` **不 join**（阻塞在 `input()`），加註解說明。
- `mobile/state.py:32-35,42,45-46`：改呼叫 `app_wiring.settings` 三個函式（7a 會再整個重構，這裡只去重複）。
- `tests/test_app_wiring.py`／`tests/_wiring_helpers.py`：改用 `build_core(config, session_manager=…)` 取得接線，刪掉手寫 15 個 queue（行為不變、測試更短）。

## 新增測試

- `tests/test_app_assembly.py`：
  - `build_core(tmp config)`：`set(parts.exchange.routes()) == protocol.topics.ALL`；`parts.queues` 鍵集合 == `wire()` docstring 列的鍵（含 `stt_event`）；不需要 `pyaudio`／`requests` 以外的模組（用 `sys.modules` 斷言未匯入 `record`、`http_client`）。
  - 傳入自建 `session_manager` 時 `parts.session_manager is sm`。
  - `settings`：三個函式對 `app.py` 原邏輯的等價案例（無 default → 建立；`export_file` 無目錄 → `"."`；`SLM` 缺節 → `(20, True)`）。
- `tests/test_lifecycle.py`：fake 物件記錄呼叫順序；`start_all` 正序、`stop_all` 預設正序、某個 `stop()` 拋例外時其餘仍被停、`reverse=True` 倒序。
- legacy join：`tests/test_http_client.py`／`test_summary_generator.py`（階段 2）加「`start()` 後 `stop()` 返回時執行緒已不存活」各 1 案。

## 步驟

1. `settings.py`＋測試 → 綠；`app.py`、`mobile/state.py` 改用。
2. `assembly.py`＋測試 → 綠；`test_app_wiring` 改用 `build_core`。
3. `Lifecycle`＋測試 → 綠；`main()` 改寫，逐行對照舊順序。
4. legacy join＋測試。
5. 文件同步。手動煙霧測試（不需硬體）：`.venv/bin/python -c "from app_wiring.assembly import build_core; from config import load_config; p=build_core(load_config()); print(sorted(p.queues))"`。

## behavior-preserving

是。啟停順序、提示文字、`TERMINATE` 時機不變；join 只讓停機多等最多 1 秒／模組。

## 驗證命令

```bash
.venv/bin/python -m pytest -q                                   # 全綠；≥ 上階段 + 至少 10
.venv/bin/python -m pytest -q tests/test_app_assembly.py tests/test_lifecycle.py tests/test_app_wiring.py
python workflows/common/code-map/codemap.py big | head -5        # app.py 行數應明顯下降（目前 223）
```

## 需同步的文件

- CODE_MAP「框架與接線」：加 `app_wiring/assembly.py`、`app_wiring/settings.py`；`app.py` 描述改「`main()` 呼叫 `build_core`、建 legacy、Lifecycle 啟停」。
- `docs/architecture/runtime.md` §7：啟停改為「Lifecycle 單一清單；legacy `stop()` 已 join（TerminalInput 除外）」。
- `docs/architecture/migration.md` §5：`app.py` 一列更新。

## Done when

- `app_wiring/assembly.py`、`app_wiring/settings.py`、`tests/test_app_assembly.py`、`tests/test_lifecycle.py` 存在。
- `rg -n "\.start\(\)" app.py` 命中 ≤ 2 行（只剩 `lifecycle.start_all()` 與可能的註解）。
- `rg -n "join\(" record.py voice_to_text.py http_client.py summary_generator.py tui_renderer.py text_to_voice.py` 每檔 ≥ 1 行。
- `rg -n "switch_session\(\"default\"\)" app.py mobile/state.py` 無命中（已移到 settings）。
- pytest 全綠且測試數 ≥ 414。

建議 commit：`refactor(app): 抽出 build_core／settings／Lifecycle；legacy stop 補 join`
