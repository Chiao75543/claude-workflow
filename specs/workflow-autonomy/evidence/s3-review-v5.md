# workflow-autonomy v5 S3 規格審查

- 時間：2026-09-14T16:50:29+08:00
- 範圍：`specs/workflow-autonomy/spec.yaml` draft version 5
- 結論：`PASS_WITH_OWNER_DECISIONS`
- 性質：既有 reviewer agent 的唯讀程序性預審；不是具平台簽章的身分驗證。

三個 reviewer 先後檢查 CLI、schema、CAS/idempotency、approval anchor、frozen-test、
evidence self-reference、status、static-command、finding identity/loop、v0 oracle 與 temp-Git E2E。
最後一輪確認以下 mechanical blockers 已關閉：

1. autonomy 先固定並驗證 approval source tree，再做 idempotent replay 與 generation CAS；status 不做 replay。
2. repair 保存完整 `baseline_entries`，可辨識 pre-existing dirty path 在 plan 後的再次變動。
3. completion evidence 只接受該 spec evidence 目錄內的 canonical regular paths。
4. evidence token 排除 manifest/status 自我參照，但 final checker 仍驗證它們位於指定 snapshot。
5. finding identity 納入 kind、check、location 與完整 semantic repro。
6. v0 使用核准 source tree 的九項 paired baseline oracle；v1 E2E 明列 stage/commit/amend 指令。

仍需 Owner 決定的只有兩項 authenticity gap：

1. repository 腳本能驗 approval artifact 的 Git 完整性與 `source_ref` 一致性，不能證明該 reference
   真由 Owner 的平台身分產生。
2. core 能驗 writer/reviewer task ref 與 token 相異且一致，不能證明平台身分本身未被偽造。
