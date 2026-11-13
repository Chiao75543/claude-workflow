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
- S1 依描述推定六個風險旗標(`meta.risk_flags`,不問你);S3 再拿 `impact.files` 對 `risk_paths` 複核,取較嚴的。
  全 false 且沒命中才走 lite 車道(跳過 S4 隔離讀者)。推定和命中的路徑列在說明頁,你批准時確認或推翻旗標。
- **不會**寫測試、不會實作。要繼續就跑 `/workflow:test`。
- S3 會跑 `scan-siblings`,把跟其他在飛分支撞到的檔案列出來。
