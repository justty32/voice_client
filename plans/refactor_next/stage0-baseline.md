# 階段 0：文件基準校正

[總覽](README.md)

## 目標

把已查證與程式不符的文件敘述改正，讓後續階段的「Done when」有正確的基準數字可比。零程式邏輯變動。

## 動到的檔案

- `CLAUDE.md`：「驗證要求」段的基準 `339 passed, 5 subtests passed` → `358 passed, 9 subtests passed`。
  （`CLAUDE.md` 在工作樹已有使用者修改；只改這一行，其餘保留。）
- `workflows/testing.md`：`335 tests + 5 subtests` → `358 passed, 9 subtests passed`。
- `docs/architecture/runtime.md`：「全部 daemon，`stop()` 以 `join(timeout)` 收尾」→ 改為事實：
  「原生 `TunnelModule.stop()` 與 `Exchange.stop()` 會 `join(timeout=2)`；legacy 模組目前只翻旗標不 join（階段 5 補齊）。」
  並註明停機時沒有 drain。
- `docs/architecture/topics.md`：`tts` 生產者「ChatFlow、SummaryGenerator、CommandRouter」→ 只有 `ChatFlow`
  （查證：`python workflows/common/code-map/codemap.py topics`，`tts ← modules.chat_flow.ChatFlow`）。
  同時補一行：`ui_event` 的 role 現有 `system／assistant／summary／voice／user／sending`；`error`、`buffer_peek` 只有 TuiRenderer 支援、桌面無生產者。
- `app_wiring/ui_events.py:6`：註解 `_FallbackUiEvent` → `_UiEventClass`（與第 14 行類名一致）。
- `INDEX.md`：依 D1 預設，在表格加一列 `ai_assist/`／`server_sample/`：「非產品內容：另一實驗專案文件與 `SERVER.enabled=true` 的測試對端；codemap 排除」。

## 步驟

1. `git status`，確認上列檔案的既有修改內容，只做本階段的行內更動。
2. 逐檔修改；`docs/architecture/topics.md` 的 `tts` 行先用 codemap 再次核對。
3. 跑驗證命令。

## behavior-preserving

是。只改文件與一行註解。

## 驗證命令

```bash
.venv/bin/python -m pytest -q          # 358 passed, 9 subtests passed（不變）
bash wf/tools/wf-lint.sh .             # TOTAL broken=0
python workflows/common/code-map/codemap.py topics | sed -n '/^tts$/,/^tts_ctl$/p'   # tts 生產者只有 ChatFlow
```

## 需同步的文件

本階段本身就是文件；CODE_MAP 不變。

## Done when

- `rg -n "358 passed, 9 subtests" CLAUDE.md workflows/testing.md` 各命中 1 行。
- `rg -n "SummaryGenerator、CommandRouter" docs/architecture/topics.md` 無命中。
- `rg -n "_FallbackUiEvent" app_wiring/ui_events.py` 無命中。
- `rg -n "ai_assist" INDEX.md` 命中 1 行。
- pytest 回傳 `358 passed, 9 subtests passed`；wf-lint `broken=0`。

建議 commit 訊息：`docs: 校正測試基準、tts 生產者與 legacy stop 停機敘述`
