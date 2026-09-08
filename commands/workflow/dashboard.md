---
name: "workflow:dashboard"
description: "產出推送前的證據表 —— 可達性排最前面(和嚴重度分開)、需注意事項、十二道關卡、審查活動量、UI 截圖。你按推之前唯一要看的東西。"
category: Workflow
tags: [workflow, evidence, dashboard]
---

產出 S11 的證據表。

**動作**

```bash
scripts/gates/dashboard specs/{name}/spec.yaml
```

**注意**

- **沒有一行需要你讀程式碼。**
- **可達性排在最前面,和嚴重度分開排。** 「必須附可執行重現」那條規則會系統性
  低估缺席類問題(沒接進導航、沒有呼叫點)—— 東西不存在時寫不出失敗測試。
- 表上會顯示**審查活動量**(提出 N → 作廢 M → 證實 K)。
  一張只有綠勾的表會訓練人變成橡皮圖章;活動量才分得出「乾淨」和「沒認真查」。
