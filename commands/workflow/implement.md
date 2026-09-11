---
name: "workflow:implement"
description: "從已凍結的規格與測試實作到全綠。只能動產品程式碼,碰規格測試或規格檔會被擋。"
category: Workflow
tags: [workflow, implement]
---

跑 S8:實作到測試全綠。

**動作**

派 `green-writer`(opus);它會讀專案自備的 `rd-implementer` skill 與 `rules_files`。

**注意**

- **能動**:產品程式碼、`impl/` 命名空間的測試。
- **不能動**:`spec/` 命名空間的測試、`spec.yaml`。兩個都靠 hash 在 S9 擋。
- 實作時發現規格對環境的假設是錯的 → 那是**明確事件**:
  改規格 → 還原成 stub → 重新擷取那條的 RED → 再實作。不是偷偷改測試。
- **做到哪算夠 = 批准的 examples。** 例子外的情況不做、不防;它回報的「例子外的觀察」
  留到審查變成 `ask_user`,不要叫它做。多出來的公開介面會被 `overbuilt` 擋。
