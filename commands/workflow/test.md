---
name: "workflow:test"
description: "從已批准的規格寫測試並擷取 RED 證據 —— stub-first、格式化、跑一次、六類判定與三方對帳、審過(test-review + test-reviewer)才凍結。"
category: Workflow
tags: [workflow, test, tdd]
---

跑 S7:寫測試並留下 RED 證據。

**動作**

派 `red-writer`(opus;它會讀專案自備的 `test-writer` skill),跑 `scripts/gates/red-capture`,
然後 **S7½**:`scripts/gates/test-review --mechanical-only` → 派 `test-reviewer`(opus)→
`test-review` 全過 → 才凍結。

**注意**

- **stub 必須回傳「沒有任何 Scenario 預期的東西」** —— 回 `[]` 或靜默成功
  會讓對應的測試在實作前就綠,那就是空測試。
- 順序是「寫測試 → **格式化** → 跑 → 擷取證據 → 凍結」。
  先格式化,否則之後修 lint 會讓凍結指紋失效。
- 測試要斷言**具體錯誤訊息**,不只斷言型別。
- 每條測試至少引用它那條 Scenario 某組 example 的具體值;case 名稱讀得出 given/when/then。
- mode 6a/6b 在這裡交 RED 與凍結證據；6c 明列延後到 S9b,不寫假的 `@Test`；6d 只列人工理由。
- 未知或缺少 mode 一律擋,不能因為不屬於目前階段就靜默略過。
- **凍結錯的測試比沒凍結更糟** —— 審出問題退回改測試,而且要重新擷取 RED。
