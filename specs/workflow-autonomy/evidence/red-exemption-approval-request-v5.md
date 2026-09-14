# workflow-autonomy RED 豁免核准請求

- 時間：2026-09-14T20:42:56+08:00
- Direct run：59 Scenario／85 examples；83 assertion RED、2 GREEN、0 helper error、0 traceback。
- GREEN：SC-035 example 1、SC-046 example 1。

兩條 GREEN 都是既有相容性要求：

1. SC-035 要求現有 test-review、traceability、freeze-check 維持通過。
2. SC-046 要求 autonomy version 0 與 approval-source baseline 的九項正式 CLI 完全相同。

刻意破壞現行行為再修回，會製造假的 RED。建議在兩條 Scenario 加入具體 `red_exempt_reason`，
其餘 83 examples 維持 assertion RED。`spec-diff` 已正確判定新增 RED 豁免是契約鬆綁，必須退回 S5
取得 Owner 明確核准；在核准前 direct evidence 維持 `rejected`，不得 freeze 或實作。

## Owner 決定

- 時間：2026-09-14T23:56:42+08:00
- 決定：同意只為 SC-035、SC-046 新增上述 `red_exempt_reason`；兩條保留回歸測試，其餘 83 個
  examples 維持 assertion RED。此核准不授權刪測試或降低其他 gates。
