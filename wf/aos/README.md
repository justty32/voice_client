voice_client 的 aos 設定：座位的 agent 定義、aos 問題回報檔。誰管什麼在 [wf/org](../org/README.md)，不在這裡。

# wf/aos

回 [wf](../README.md)｜組織 [wf/org](../org/README.md)

窗口 `main` 管這個夾（[lead 卡](../org/lead/README.md)）。本 repo 掛在子 daemon `repo-vc`（工作區＝repo 根）。

## 內容

| 路徑 | 用途 |
|---|---|
| [defs/dev/](defs/dev/README.md) | dev 座位的定義（腦 astra） |
| [defs/docs/](defs/docs/README.md) | docs 座位的定義（腦 sol） |
| [feedback.md](feedback.md) | aos 本身的問題，一件一筆 |

## 定義怎麼做的（CHOICE 9）

- 從 aos 範本 `templates/start-api/agents/ann` 的做法：四格程式（idle、think、wait、act）不放在這夾，`fsm.json` 寫 `{"$env": "AOS_HOME", "$path": "/templates/agent-fsm/idle.py"}` 這種，執行時才去 stock agent-fsm 拿；`interfaces.json` 的 `hooks` 也指 stock 的 `hooks.json`。aos 更新後下一格就用新的，不用重抄。
- 夾裡只剩設定：`_entry`、`body.json`、`loop.json`、`fsm.json`、`interfaces.json`、`hookeds.json`、`tools.json`、`llm.json`、`subagents.json`、`system.txt`、`_metainfo.json`、`README.md`。
- 工具：stock agent-fsm 那 11 包，再加 `subagent`、`def` 兩包（CHOICE 8 可開下屬）。
- 想改某一格的程式：照 ann 的 README，把那支和它 import 的共用檔一起靜態複製進來，再把 `fsm.json` 那格指過去；那格從此不跟 aos 更新。

## 檢查

改過定義就跑（只讀，問題清單空＝OK）：

```bash
echo '{"op":"check","root":"'"$PWD"'/wf/aos/defs"}' | "$AOS_HOME/lib/tools/aos/defs/_entry"
```

它不查 `model` 名字對不對；名字要對 llm kernel 的 endpoint 包（`~/aos-home/llm/kernel.json` 的 `endpoints`）。

## 掛載

掛載、停、移除只由窗口做（[lead 卡](../org/lead/README.md)）。有工作才掛；收工 stop、不 rm（CHOICE 2）。
