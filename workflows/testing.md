# Testing

## 完整自動測試

```bash
.venv/bin/python -m pytest -q
```

目前基準為 335 tests + 5 subtests。

## 標準庫 runner

```bash
.venv/bin/python -m unittest discover -s tests
```

## 語法檢查

```bash
python -m compileall -q -x '/(\.venv|\.git)/' .
```

## 驗證層級

1. 單元測試：純函式與單一模組。
2. 隧道整合：producer → Exchange → consumer。
3. 接線測試：`app.wire()` topic 與 queue 對應。
4. 系統整合：模型、網路服務、音訊裝置可見。
5. 真人驗收：實際錄音辨識、播放中斷、音質與手機瀏覽器行為。

第 4、5 層若本機條件不足，記到 `WAIT_USER.md`，不可用「未測」冒充「失敗」。
