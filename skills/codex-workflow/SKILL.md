---
name: codex-workflow
description: 在軟體專案中以四個使用者可見 stage 完成需求、依歧義與風險條件式加強驗證，並停在使用者 merge；適用於要求 Codex 自主實作與可執行證據的開發工作。
---

# Codex 精簡 Workflow

把規劃、實作、修正與自我審查留在 Codex 原生工作迴圈內。對使用者只呈現：

1. 定方向
2. Codex 完成工作
3. 自動驗證
4. 使用者按 merge

先讀 [profile.md](references/profile.md)，再依其中的評估格式建立 assessment。把這份 `SKILL.md`
所在位置往上兩層視為 workflow repository root，並執行：

```bash
<workflow-repository-root>/scripts/codex/route <assessment.yaml> --json
```

`route` 不是建議器：退出碼非 0、`status: blocked` 或任何未決欄位都必須留在「定方向」。不要自行補預設值。

## 執行邊界

- 快速路徑由 Codex 完成規劃、實作、修正、審查，然後跑必要測試、lint、行為契約 diff 與真實入口 smoke。
- 只有 `spec_ambiguity: true` 或 `complexity: complex` 才在「定方向」增加一位 spec-reader。
- 只有任一高風險旗標為 true 才在「自動驗證」增加 spec-oracle。高風險類別不可刪減。
- UI 改動的截圖是 smoke 證據，不是另一個 stage。
- 不宣稱 G8／mutation 已通過；只有未來接上真實 executor 並取得實跑證據後才可啟用。
- 不要求 RED/GREEN、完整 freeze、test-reviewer 或 code-adversary 成為固定 stage。若專案本身因風險需要其中一項，只能作為既有四個 stage 裡的內部檢查。

規格核准後自主執行。只有以下情況中斷使用者：核准行為必須改變；新增權限、外部依賴或不可逆操作；規格未定義的重大資安、隱私、金流或資料遺失風險；同一問題修兩次仍失敗；修好後再次出現；最後 merge。why、design、tasks、檔案安排與內部實作方式不因低風險細節要求再次批准。

禁止 push、開 PR 或 merge，除非當次使用者明確要求。不得把 projectless 任務描述成沒有工具的隔離環境。
