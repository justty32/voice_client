# 使用手冊：疑難排解

[使用手冊入口](../user_manual.md)

## 9. 疑難排解

### 熱鍵與控制

| 症狀 | 解法 |
|---|---|
| KDE Wayland 上 Alt+F8 沒反應 | 確認 Voice Client 正在執行、`/run/user/$UID/voice-client-control.sock` 存在，並查看 [KDE 快捷鍵文件](../kde_wayland_shortcuts.md) |
| 啟動說「全域熱鍵已停用」 | `pynput` 路徑不可用；KDE 使用者確認是否同時顯示「Wayland 本機控制已啟用」，其他環境改用斜線指令 |
| 同時開兩個 Voice Client | 不支援；兩個程序會爭用同一個控制 socket，只保留一個桌面程序 |
| 打字輸入沒反應 | 游標要在終端機輸入框，不是在其他地方 |

### 錄音與辨識

| 症狀 | 解法 |
|---|---|
| 錄音按了沒反應 | 確認麥克風權限，`pamixer --list-sources` 看看有沒有輸入裝置 |
| 辨識很慢 | `model_size = tiny`，`beam_size = 1` |
| pyaudio 裝不起來 | `sudo pacman -S portaudio python-pyaudio` 試試系統包 |
| 每段錄音後顯示「[STT 錯誤] STT 模型未載入」或「模型載入失敗：…」 | faster-whisper 模型沒有載入成功；檢查 `[STT] model_size`／`device`（GPU 改 `cpu` 試試）與網路（首次需下載模型），詳見 `output/system.log`，修正後重啟 |
| 顯示「[錄音錯誤] …」後一陣子又能錄 | 音訊裝置暫時不可用；錄音器會自動以 2、4、8…最多 30 秒間隔重試，裝置恢復即可再錄 |

### TTS 朗讀

| 症狀 | 解法 |
|---|---|
| Kokoro 完全沒聲音 | 確認 `models/kokoro/` 模型完整、系統有可用的 PortAudio 輸出裝置，並查看 `output/system.log` |
| Kokoro 播到一半停了，之後恢復 | Kokoro worker 意外結束，程式已自動重啟一次（log 有「已自動重啟」）；若再次結束會放棄 Kokoro（log 有「放棄」），之後的朗讀被丟棄，需重啟程式 |
| 顯示「[摘要失敗] …，改播原文」 | SLM 摘要服務失敗或回空摘要，已改播完整原文；確認 `[SLM] base_url`／`model` 與服務是否在跑 |
| pyttsx3 完全沒聲音 | Linux 確認已安裝 `espeak-ng` |
| TTS 講話很怪 | `pyttsx3` 的 rate 調慢，或換 `kokoro` 引擎 |

### LLM 與手機連線

| 症狀 | 解法 |
|---|---|
| LLM 沒有回應 | 確認 `[LLM] base_url` 對了，本地 Ollama 的話先確認 `ollama serve` 在跑 |
| LM Studio 沒有回應 | 確認 Local Server 已啟動、`/v1/models` 可連線，且 `model` ID 完全相同 |
| 接 LiteLLM proxy 後沒有回應 | 確認 proxy 在跑、`/v1/models` 可連線；`model` 要填 proxy 的 `model_name` 別名，`api_key` 等於 `master_key`，見 [LiteLLM proxy](litellm.md) |
| 手機連不上 | 確認同一個 WiFi；防火牆 `sudo ufw allow 8080`；網址用 `https://` |
| 手機錄音後出現「[錄音錯誤] …」 | 伺服器缺 `ffmpeg` 或音訊格式無法轉檔；安裝 ffmpeg 後重啟 `mobile_server.py` |

### 對話資料

| 症狀 | 解法 |
|---|---|
| 啟動後對話列表是空的，`output/` 多了 `.sessions.json.corrupt-<時間戳>` | sessions 檔損毀，程式已把原檔備份成 `.corrupt-*` 並以空集合啟動；可手動修復該備份的 JSON 後改回 `.sessions.json`（先關閉程式） |

日誌：`output/system.log`（等級在 `[LOGGING] level` 設定）。
