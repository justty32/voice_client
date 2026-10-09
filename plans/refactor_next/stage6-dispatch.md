# 階段 6：指令集單一來源、派發表、小型死碼

[總覽](README.md)｜痛點 4（指令集三份）、10；P3-4、P8

## 目標

斜線指令集目前有三份（`terminal_input.py:7`、`command_router.py:80-159`、`command_handlers/session.py:72-77`），熱鍵訊號也有三份
（`keyboard_listener.py:74-82`、`local_control.py:22-30`、`command_router.py:24-30`）。本階段讓它們都從 `protocol/commands.py` 取得，
`CommandRouter._dispatch` 改派發表，並以契約測試鎖住「指令集 == 派發表鍵 == /help 內容」。附帶移除無生產者的 `MUTE/UNMUTE`。

## 動到的檔案

新增：

- `protocol/commands.py`：
  - `SLASH_COMMANDS: frozenset`（現 `terminal_input._SLASH_COMMANDS` 的 23 個）；
  - `SESSION_COMMANDS: frozenset`（`/new /switch /list /delete /rename /history /save /load`，對應 `command_router.py:120-121` 的防禦 tuple）；
  - `HOTKEY_SIGNALS: frozenset`（5 個大寫字串）；`HOTKEY_TO_CMD: dict`（現 `_STR_TO_CMD`）。
- `tests/test_protocol_commands.py`。

修改（behavior-preserving）：

- `terminal_input.py:7`：`_SLASH_COMMANDS = SLASH_COMMANDS`（保留舊名給可能的匯入者）。
- `local_control.py:22-30`：`ALLOWED_COMMANDS = HOTKEY_SIGNALS`。
- `keyboard_listener.py:74-82`：改用常數（`pynput` 匯入位置不變）。
- `modules/command_router.py`：
  - `_STR_TO_CMD = HOTKEY_TO_CMD`；
  - `_dispatch` 改為查 `self._handlers`：`dict[str, Callable[[dict], None]]`，於 `__init__` 由 `_build_handlers()` 建立，鍵含熱鍵 cmd、斜線指令、`voice`、`unknown`；
    `_sm is None` 的防禦改成：`cmd in SESSION_COMMANDS and self._sm is None` → 友善訊息（語意同現行 120-123 行）；
    找不到鍵 → 同現行「未知指令」訊息（153-159）。各 handler 的簽章不改，用 lambda／partial 包 `args`。
  - `_handle_exit` 抽出（現 144-145 行內嵌 emit）。
- `modules/command_handlers/workspace.py:103-114`【改行為，小】：`/to_top 0` 現被當「無參數」（`if idx else -1`）；改為 `idx is not None and idx < 1` → 回「用法: /to_top [編號]（編號需 ≥ 1）」。
- `text_to_voice.py:238-243` 與 `_muted` 旗標（`_drain_input` 內 `if self._muted`）：刪除 `MUTE`／`UNMUTE` 分支與旗標（`rg '"MUTE"'` 全 repo 無生產者）。
- `/help` 文字（`session.py:72-77`）**不改**：由契約測試保證涵蓋。

手機的 `mobile/inputs.py:95-186` if/elif 與 `/help` 清單在 7b 整個消失，本階段不碰。

## 新增測試

- `tests/test_protocol_commands.py`：
  - `set(router._handlers) ⊇ SLASH_COMMANDS ∪ set(HOTKEY_TO_CMD.values()) ∪ {"voice","unknown"}`；
  - `/help` 輸出文字包含每個 `SLASH_COMMANDS` 成員；
  - `terminal_input._SLASH_COMMANDS is SLASH_COMMANDS`；`local_control.ALLOWED_COMMANDS == HOTKEY_SIGNALS`；
  - `HOTKEY_TO_CMD` 鍵集合 == `HOTKEY_SIGNALS`。
- `tests/test_command_router_workspace_edit.py`：`/to_top 0` → 用法訊息、工作區不變。
- `tests/test_text_to_voice.py`：若有 MUTE 相關案例則刪除（目前 `rg -n MUTE tests` 應無命中，先確認）。
- 既有 121 個 `test_command_router_*` 全部不改即須綠（派發表等價的證據）。

## 步驟

1. `protocol/commands.py`＋契約測試（先紅：`_handlers` 不存在）。
2. `terminal_input`、`local_control`、`keyboard_listener` 改用常數 → 綠。
3. `CommandRouter` 派發表 → 121 個既有測試綠；契約測試綠。
4. `/to_top 0`＋測試；MUTE 刪除。
5. 文件同步。

## behavior-preserving

派發表、常數集中、MUTE 刪除：是。`/to_top 0`：**否**（原：移動最後一筆；新：回報用法），已列測試。

## 驗證命令

```bash
.venv/bin/python -m pytest -q                                   # 全綠；≥ 上階段 + 至少 6
.venv/bin/python -m pytest -q tests/test_command_router_hotkeys.py tests/test_protocol_commands.py tests/test_local_control.py
rg -n "elif cmd ==" modules/command_router.py                    # 無命中
rg -n '"MUTE"|"UNMUTE"|_muted' text_to_voice.py                  # 無命中
```

## 需同步的文件

- CODE_MAP：`protocol/commands.py`；`modules/command_router.py` 描述改「派發表」。
- `docs/user_manual/commands.md`：`/to_top` 參數需 ≥ 1。
- `docs/architecture/topics.md`：`commands` payload 的 cmd 集合指向 `protocol/commands.py`。
- `docs/kde_wayland_shortcuts.md`：若列出白名單命令，改為指向 `protocol/commands.py`（內容不變）。
- `WAIT_USER.md`：熱鍵五訊號真機驗證（X11 與 KDE Wayland 各一次）。

## Done when

- `protocol/commands.py`、`tests/test_protocol_commands.py` 存在。
- `rg -n "elif cmd ==" modules/command_router.py` 無命中；`rg -n "_SLASH_COMMANDS = \{" terminal_input.py` 無命中。
- pytest 全綠且測試數 ≥ 420。

建議 commit：`refactor(指令): 指令集集中到 protocol/commands.py，CommandRouter 改派發表`
