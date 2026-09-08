---
name: "workflow:verify"
description: "跑十二道驗證關卡 —— 八道腳本(規格/凍結/lint/測試/RED 對帳/追溯/範例/可達性)全綠,才啟動四道付費(變異/獨立讀者/對抗審查/UI 截圖)。"
category: Workflow
tags: [workflow, verify, gates]
---

跑 S9 的十二道關卡。

**動作**

依序跑 `scripts/gates/` 的腳本;八道全綠才派 fable agent。

**注意**

- **順序就是花錢的順序。** 絕不花錢請 AI 去審一個腳本本來就會擋掉的東西。
- G10 獨立讀者失敗時,裁判是規格的 `examples`:
  與例子矛盾 → 判它錯;一致但實作沒過 → 擋;落在例子之外 → 記缺口但不擋。
- G11 的每條主張都要附**可執行的重現**;跑不出來自動作廢,不需要人裁決。
- 成立的重現測試直接進 `regression/` 命名空間。
