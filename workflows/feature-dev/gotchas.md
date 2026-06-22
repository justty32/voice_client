# feature-dev — 踩坑

- queue payload 改動若只改一端，通常不會在 import 時失敗，而會在背景執行緒靜默卡住；必須補整合測試。
- `pyttsx3` driver 與可用 voice 依平台不同；單元測試不要假設 Linux、Windows、macOS 的 voice id 相同。
- Whisper 模型載入昂貴；測試應 mock 模型，不要讓每個 case 重載。
