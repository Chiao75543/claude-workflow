---
name: workflow
description: 從一句需求到可推送的分支 —— 規格撰寫(挑洞 + 隔離讀者偵測歧義 + 說明頁批准)、TDD 測試、實作、十二道驗證關卡、證據表、commit、推送。人類只出現三次,而且沒有一次需要讀程式碼。
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
- Skill 擁有 S1–S13 的完整流程。人類介入點(批說明頁、看證據表按推、按 merge)
  都在 skill 裡面,**不要在這裡多加確認**。
- 使用者提到要跳過(例如純樣式微調),照 skill 的 Skip rule,不要從這裡覆寫。
