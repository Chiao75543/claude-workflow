---
name: workflow
description: 從一句需求到開好的 PR —— 規格撰寫(挑洞 + 隔離讀者偵測歧義 + 說明頁批准)、TDD 測試(審過才凍結)、實作、腳本關卡、smoke、付費審查、自動推 + PR 留言。人類批准說明頁、按 merge;中間只在 PR 上有「需要你決定」時才出現,沒有一次需要讀程式碼。
category: Workflow
tags: [workflow, pipeline, tdd, verification]
---

跑完整的 pipeline。

**輸入**(`/workflow` 後面的 `$ARGUMENTS`):一句功能描述,例如 `/workflow 新增收藏夾`

**動作**

立刻用 **Skill 工具**叫 `workflow-orchestrator`,把 `$ARGUMENTS` 當 args 傳進去。
不要用 Read 讀 skill 檔 —— 讓 Skill 工具去載。

```
Skill(skill="workflow-orchestrator", args="$ARGUMENTS")
```

**注意**

- `$ARGUMENTS` 空的話,先問一句功能描述再叫 skill。
- Skill 擁有 S0–S13 的完整流程。人類介入點(批說明頁、PR 上的「需要你決定」、按 merge)
  都在 skill 裡面,**不要在這裡多加確認**。
- `specs/pipeline.yaml` 不存在或 `config-check` 有缺 → skill 會先走 S0 問卷(`/workflow:init`)。
- 使用者提到要跳過(例如純樣式微調),照 skill 的 Skip rule,不要從這裡覆寫。
