# KDE Plasma Wayland 全域快捷鍵

更新日期：2026-06-22

## 背景

Wayland 不允許一般程式像 X11 一樣監聽所有鍵盤輸入，因此
`keyboard_listener.py` 使用的 `pynput` 在 Wayland 下會停用。KDE/KWin 本身可以
安全地捕捉全域快捷鍵，所以 Voice Client 採用以下路徑：

```text
KDE Global Shortcuts
  → 啟動短命 local_control.py helper
  → $XDG_RUNTIME_DIR/voice-client-control.sock
  → key_signal_queue
  → commands topic
  → CommandRouter
  → Recorder START / STOP
```

錄音、STT 和 CommandRouter 沒有 KDE 專用分支；KDE 只替代最前端的按鍵捕捉。

## 程式端

`app.py` 啟動 `LocalControl` 後會建立：

```text
/run/user/<UID>/voice-client-control.sock
```

實際位置以 `$XDG_RUNTIME_DIR/voice-client-control.sock` 為準。socket 權限為
`0600`，只有目前使用者能操作。允許的命令固定為：

- `RECORD_TOGGLE`
- `RECORD_COMMAND_TOGGLE`
- `QUICK_SEND`
- `FORCE_STOP_TTS`
- `PLAY_LAST_ORIGINAL`

未知命令會被拒絕，不會執行 shell。相同命令在 0.5 秒內重複抵達時會被去抖，
避免桌面啟動動作造成一次按鍵切換兩次。

## 目前這台電腦的 Alt+F8／Alt+F9 設定

KDE 動作檔位於 repo 外：

```text
~/.local/share/applications/voice-client-record-toggle.desktop
~/.local/share/applications/voice-client-quick-send.desktop
```

內容的核心設定是：

```ini
[Desktop Entry]
Type=Application
Name=Voice Client Record Toggle
Exec=/home/lorkhan/repo/voice_client/.venv/bin/python /home/lorkhan/repo/voice_client/local_control.py RECORD_TOGGLE
NoDisplay=true
X-KDE-Shortcuts=Alt+F8
```

這個檔案含絕對路徑。如果專案移動、使用者名稱改變或 `.venv` 被刪除，必須更新
`Exec`。修改後執行：

```bash
kbuildsycoca6 --noincremental
```

目前已註冊：

- **Alt+F8** → `RECORD_TOGGLE`
- **Alt+F9** → `QUICK_SEND`

`config.ini [CONTROL]` 的鍵位設定屬於 `pynput` 路徑，不會自動同步到 KDE。

## 使用

Voice Client 可用下列任一方式啟動：

```bash
cd ~/repo/voice_client
uv run app.py

# 或
.venv/bin/python main.py
```

啟動訊息出現「Wayland 本機控制已啟用」後：

1. 按 Alt+F8 開始錄音。
2. 再按 Alt+F8 停止錄音並送入 faster-whisper。
3. 確認辨識文字後按 Alt+F9，將目前 buffer 送到 LLM。

不要同時啟動兩個桌面 Voice Client；兩個程序會爭用同一個 socket。

## 增加其他快捷鍵

可以複製既有 `.desktop` 檔，為每個動作使用不同檔名、按鍵和命令。例如 F10：

```ini
Name=Voice Client Stop Speech
Exec=/home/lorkhan/repo/voice_client/.venv/bin/python /home/lorkhan/repo/voice_client/local_control.py FORCE_STOP_TTS
NoDisplay=true
X-KDE-Shortcuts=F10
```

新增後執行 `kbuildsycoca6 --noincremental`。應先在 KDE 系統設定的快捷鍵頁面確認
按鍵沒有被其他動作占用。

## 驗證與故障排除

確認 Voice Client socket：

```bash
ls -l "$XDG_RUNTIME_DIR/voice-client-control.sock"
```

不經 KDE，直接測試切換：

```bash
.venv/bin/python local_control.py RECORD_TOGGLE
```

查看日誌：

```bash
tail -f output/system.log
```

正常觸發會看到：

```text
local_control: 收到本機控制命令：RECORD_TOGGLE
```

確認 KDE 已註冊動作：

```bash
qdbus6 --literal org.kde.kglobalaccel \
  /component/voice_client_record_toggle_desktop \
  org.kde.kglobalaccel.Component.allShortcutInfos
```

常見問題：

| 症狀 | 原因／處理 |
|---|---|
| helper 顯示 `Voice Client is not running` | 主程式未啟動，或 socket 尚未建立 |
| Alt+F8 無反應，但直接執行 helper 有效 | KDE 動作未載入、快捷鍵衝突，或 `.desktop` 的 `Exec` 路徑失效 |
| 按一次立刻開始又停止 | 應由 0.5 秒去抖攔截；確認執行的是目前版本 |
| socket 存在但無回應 | 確認只有一個 Voice Client，停止所有實例後重新啟動 |
| 修改 `.desktop` 後沒生效 | 執行 `kbuildsycoca6 --noincremental`，必要時到 KDE 快捷鍵頁重新指定 |

相關測試：

```bash
.venv/bin/python -m pytest tests/test_local_control.py -q
```
