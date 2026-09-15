# Profile 使用方式

## 1. 定方向

先盤點 worktree、分支與未提交修改，避免碰撞。以既有 `specs/{name}/spec.yaml` schema 描述可見行為與 examples，執行：

```bash
scripts/gates/scan-siblings specs/{name}/spec.yaml
scripts/gates/spec-lint specs/{name}/spec.yaml
```

把核准時的規格存成 `specs/{name}/evidence/spec.approved.yaml`。這不是完整 freeze：後續用 `spec-diff` 保護 given/when/then、examples、mode 與覆蓋不被縮減；why、design、tasks、impact 與檔案安排仍可由 Codex自主修正。

從 [assessment.yaml](../assets/assessment.yaml) 複製一份 assessment。每個布林值都要依 repository 現況填寫並在 `basis` 留下可核對理由；缺欄、未知欄、未知風險或未決項都會 fail closed。

`risks.permissions` 表示功能碰到權限邊界，會啟用 oracle；`new_permission` 只表示這次要新增權限，才會在工作前要求使用者決定。兩者不可混用。

分流規則：

- `quick`：complexity=quick、無 spec 歧義、無外部依賴、無高風險。
- `complex`：complexity=complex、有 spec 歧義、外部依賴或任一高風險。
- spec-reader：只有 spec 有歧義或 complexity=complex 時才使用一位。
- spec-oracle：只有權限、隱私、金流、不可逆資料操作／遷移、關鍵資安或核心入口任一為 true 時才使用。

若 Codex 的 reader 仍有一般工具可用，必須如實註記，不能宣稱它等同 Claude `tools: []` 的結構性隔離。

## 2. Codex 完成工作

Codex 原生完成規劃、實作、修正與自我審查，不拆成額外 stage。核准後只依 SKILL.md 所列中斷條件詢問使用者。相同問題最多修兩次；第三次仍失敗或修好後復發就停。

## 3. 自動驗證

依序執行便宜且必要的檢查，失敗就修正並重跑受影響範圍：

```bash
scripts/gates/spec-lint specs/{name}/spec.yaml
scripts/gates/spec-diff specs/{name}/spec.yaml
<project-test-command>
<project-lint-command>
scripts/gates/smoke specs/{name}/spec.yaml
```

測試與 lint 指令讀取專案既有 `specs/pipeline.yaml` 或 AGENTS.md 綁定，不猜測。smoke 必須走真實入口；UI 截圖放在 smoke evidence。高風險路徑在上述機械檢查通過後才跑 spec-oracle。

目前 profile 不呼叫 sibling worktree 尚未整合的 `autonomy`、`evidence-check` 或 static-command RED。等共用核心合併後應加 adapter，而不是在這個 profile 複製實作。

## 4. 使用者按 merge

交付實際執行結果、剩餘限制與碰撞／待接點。停下讓使用者決定 merge；不自動 push、開 PR 或 merge。
