# 6. 卡住了怎麼辦

[入門手冊目錄](../README.md)｜上一章：[用手機](05-mobile.md)｜下一章：[它裡面怎麼運作](07-inside.md)

小幫手遇到問題時，會盡量在畫面上說出來，不會悶不吭聲。先看畫面上的訊息，再對照下面。

## 按 F8 沒反應

- **KDE Wayland**：改按 Alt+F8。F 鍵在 Wayland 上聽不到，要靠 KDE 快捷鍵轉告。
- **其他 Wayland、SSH 遠端**：熱鍵沒辦法用，但打字和斜線指令照常。
- 畫面出現「錄音錯誤」：麥克風被別的程式占用或沒插好。小幫手會每隔一陣子自己重試，
  等待時間會越拉越長，最多 30 秒。

## 說了話卻沒有字

- 畫面出現「`[STT 錯誤]`」：速記員出問題了，常見原因是語音辨識模型沒載入成功。
  檢查 `config.ini` 的 `[STT]`，例如沒有 NVIDIA 顯卡就把 `device = cuda` 改成 `cpu`。
- 什麼都沒出現、狀態列回到「待機」：多半是太小聲，被當成沒說話。
  可以調低 `[AUDIO] silence_threshold`。

## 沒有聲音

- 確認喇叭和音量。
- 用 Kokoro 時，模型檔要放在 `models/kokoro`。Kokoro 意外停掉時，小幫手會自動重開一次。
- 換成 `[TTS] engine = pyttsx3` 試試看，需要先裝好 `espeak-ng`。

## AI 沒回

- 確認 `[LLM] base_url` 的 AI 服務真的有開著（例如 LM Studio 有按下啟動）。

## 對話筆記本不見了

小幫手讀不懂存檔時（例如檔案壞掉），**不會刪掉它**。它會把壞檔改名成
`output/.sessions.json.corrupt-時間` 備份起來，再從空白開始。你可以拿那個備份去救資料。

更多狀況見[使用手冊的疑難排解](../../user_manual/troubleshooting.md)。

下一章：[它裡面怎麼運作](07-inside.md)
