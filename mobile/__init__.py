"""mobile — mobile_server.py 的拆分子模組（手機 Web 後端）。

手機與桌面共用 `app_wiring.assembly.build_core()` 的 Data Tunnel，只替換邊緣裝置。

- state.py：`MobileState`（持 CoreParts）與 `build_mobile_state()` 組裝工廠（匯入無副作用）
- edge.py：EdgeSink（Exchange 投遞 → WS 事件）與 BrowserClipboard
- audio.py：ffmpeg 檢查與 MediaRecorder 音訊 → WAV 轉換
- push.py：邊緣直接推送 WS 事件的 helper
- inputs.py：前端輸入（音訊、文字、指令、訊號、剪貼簿）轉送進 Data Tunnel
- outputs.py：WebSocket 輸出推送迴圈
- net.py：LAN IP 偵測
- ssl_cert.py：自簽 SSL 憑證生成

對外入口仍是 `mobile_server`：`python mobile_server.py`（內部 `create_app(build_mobile_state(...))`）。
各函式第一個參數皆為 `state: MobileState`。
"""
