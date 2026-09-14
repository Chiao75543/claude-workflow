# workflow-autonomy v5 核准後 design 修正

- 時間：2026-09-14
- 分類：design／安全性收緊；未修改任何 Scenario、example、`then` 或 `mode`。
- 原因：同步 `origin/main` 後，現行 workflow 明定 staged approval 只能是 `pending_commit`；此外，
  approval artifact 若記錄包含自身的 tree/commit OID 會形成不可解的自我參照。

修正如下：

1. autonomy plan 只接受 HEAD 中已 commit 的 `spec.approved.yaml`、`spec.hash`、`approval.json`；
   index-only candidate fail closed 為 `pending_commit`。
2. approval artifact 不保存自己的 storage/tree/commit；gate 從 Git 現場推導並在裁決前重驗 HEAD。
3. delivery manifest 可記錄既有 approval anchor 的 commit/tree，因該 anchor 先於 manifest，沒有自我參照。
4. static-command runner 採 direct assertion RED → 最小 runner → 正式 red-capture self-hosted RED；兩份
   證據都保留，解決 runner 無法在尚不存在時用自己擷取 RED 的 bootstrap，不接受 parser error 冒充 RED。

此變更收緊核准證據，不改 Owner 已核准的 examples；依 `spec-diff` 規則不需重新 S5。
