voice_client 遇到的 aos 本身的問題：一件一筆，攢著一起交給 aos 的窗口 `repo-aos`（經窗口 `main` 轉）。

# aos 問題回報

回 [wf/aos](README.md)｜規則見 [org 的「aos 本身的問題」](../org/README.md#aos-本身的問題)

**誰寫**：任何座位或單工遇到都可以追加一筆；交出去由窗口 `main` 做。**只追加**，交出去之後在那筆後面註明日期與去向，不刪。

**一筆寫什麼**：日期、誰遇到、發生什麼（附證據路徑：stack 的 `stderr.txt`、指令輸出存檔）、花了什麼代價（卡多久、重跑幾次）、有建議就寫。只有工具壞到工作停擺才立刻講；其他的一起、簡短、附路徑。

## 待交

- 2026-11-23，docs：aos `knowledge/wf/source.md` 引用 `source/block-3.json`、`block-4.json`，實檔是 `.md`。
- 2026-11-23，main：root daemon（pid 7763）環境裡的 `AOS_LLM_KERNEL=/home/lorkhan/aos-home/.stack/proc/llm`（少一個 s），實際 llm kernel stack 是 `.stack/procs/llm`；`root/.env` 寫的是對的 `${AOS_STACK}/procs/llm`，推測起根時殼裡已 export 了錯值（.env 不蓋殼值）。後果：整棵樹裡所有 agent-fsm 問腦都 `LlmKernelMissing`（dev、docs 第一次掛上就卡在 cooldown）。暫解：座位掛載時 `envs` 帶正確的 `AOS_LLM_KERNEL`。證據：`tr '\0' '\n' < /proc/262645/environ | grep LLM`。建議：重起根前 unset 該變數，或讓 aos-llm 報錯時提示相近的路徑。
