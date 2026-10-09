# Roadmap

記錄「確定會做，但尚未排入實作」的項目。進入認真設計時移到 specs；開始施工前建立 plan。
括號內為來源編號（B／P＝2026-07 bug／架構改進健檢報告，已封存於 reports/archive/）。

## Open

- Recorder 收到 START 時先讀掉 stream 殘留再累積 frames，避免首句夾帶待機期間的舊音訊（B10；效果需真機聽）。
- `outbound` payload 由 `/send` 端附上 history，HttpClient 退化為純 I/O、不再持有 SessionManager（P9）。
- 補 `tui_renderer`、`keyboard_listener` 的單元測試（P10-2 殘留）。
