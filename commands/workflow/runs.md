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
scripts/gates/runs --set <spec> --expect-generation 0 --pipeline-state running --stage S8 --next-step run_tests --delivery-state local
scripts/gates/runs --set <spec> --expect-generation 1 --delivery-state committed --committed-evidence-token <token>
```

**注意**

- 已落地(在整合分支上)的規格會被濾掉,不算在飛。
- 等你的排在最前面。
- 想知道會不會撞到別的分支,用 `scripts/gates/scan-siblings <spec>`。
- version 1 每次更新都要帶 generation CAS；`committed`／`pr_open` 只接受同一 HEAD 的
  `evidence-check --commit` token。回報被平台拒絕時保存 `report.state=denied` 與 reason，不換管道重試。
