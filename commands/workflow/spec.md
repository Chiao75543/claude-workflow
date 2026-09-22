---
name: "workflow:spec"
description: "只寫規格 —— scope audit、挑洞、兩個隔離讀者偵測歧義、產說明頁給你批准、定稿凍結。停在 S6,不寫測試也不實作。"
category: Workflow
tags: [workflow, spec]
---

只跑規格階段(S1–S6)。

**輸入**:一句功能描述。空的話先問。

**動作**

```
Skill(skill="workflow-orchestrator", args="--only-spec $ARGUMENTS")
```

**注意**

- 產出:`specs/{name}/spec.yaml`(通過 `spec-lint`、hash 凍結)+ 一頁說明給你批准。
- S1 會問六個風險旗標(`meta.risk_flags`);全 false 走 lite 車道(跳過 S4 隔離讀者)。沒填 = full。
- **不會**寫測試、不會實作。要繼續就跑 `/workflow:test`。
- S3 會跑 `scan-siblings`,把跟其他在飛分支撞到的檔案列出來。
