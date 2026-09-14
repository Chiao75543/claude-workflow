# workflow-autonomy S0 設定核准

- 日期：2026-09-14（Asia/Taipei）
- 來源：Owner 在協調對話逐項確認後回覆「同意」。

核准設定：

- runner：`static-command`
- test：`scripts/gates/tests/run`
- smoke：`scripts/gates/tests/run`，包含真實 temp-Git E2E
- lint：`git diff --check --`
- integration branch：`main`
- auto-push：`true`
- CI：`none`，本次不新增 CI
- rules：`AGENTS.md`

此核准不授權 merge、不新增 CI，也不擴張 workflow-autonomy v5 examples 以外的產品行為。
