---
name: "workflow:test"
description: "從已批准的規格寫測試並擷取 RED 證據 —— stub-first、格式化、跑一次、六類判定與三方對帳、凍結測試檔。"
category: Workflow
tags: [workflow, test, tdd]
---

跑 S7:寫測試並留下 RED 證據。

**動作**

叫專案自備的 `test-writer` skill(它知道這個 stack 的測試慣例與 stub 寫法),
然後跑 `scripts/gates/red-capture`。

**注意**

- **stub 必須回傳「沒有任何 Scenario 預期的東西」** —— 回 `[]` 或靜默成功
  會讓對應的測試在實作前就綠,那就是空測試。
- 順序是「寫測試 → **格式化** → 跑 → 擷取證據 → 凍結」。
  先格式化,否則之後修 lint 會讓凍結指紋失效。
- 測試要斷言**具體錯誤訊息**,不只斷言型別。
