---
name: "workflow:runs"
description: "跨 worktree 列出所有在飛的功能卡在哪一關、誰在等你。一個功能一個 session 的模式下,用這支代替開四個終端問。"
category: Workflow
tags: [workflow, status]
---

列出所有在飛的功能。

**動作**

```bash
scripts/gates/runs                      # 列出全部
scripts/gates/runs --set <spec> S9 "驗證關"
scripts/gates/runs --set <spec> S5 "等你批說明頁" --blocked-on human
scripts/gates/runs --yield              # 哪道關擋過東西(讀 origin 上的 _yield.jsonl);同一關 30 天內被豁免 ≥3 次會點名
scripts/gates/cleanup --landed          # 已經 merge、沒有沒存改動的 worktree(只列;加 --yes 才刪)
```

**注意**

- `dashboard` 每跑一次就會自己寫狀態(卡在哪一關 / 幾條等你決定 / 可推),不用手動 `--set`。
  `--set` 留給 dashboard 之外的階段(等批說明頁、hold)。

- 在飛只算每個 worktree 自己改過、還沒落地的規格;別張卡的規格副本不算。判定前先 `git fetch` 整合分支,
  抓不到會印 ⚠(那次用的是可能過期的 ref)。
- 等你的排在最前面。
- 想知道會不會撞到別的分支,用 `scripts/gates/scan-siblings <spec>`。
