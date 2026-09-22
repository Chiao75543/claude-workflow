---
name: "workflow:verify"
description: "跑 S9:腳本關卡 G0–G7 全綠 → smoke(真的入口跑一次)→ 才派付費審查 G9/G10;審查結果四類分流,迴圈由 loop 腳本數。"
category: Workflow
tags: [workflow, verify, gates]
---

跑 S9 的三段:腳本 → smoke → 付費。

**動作**

1. `scripts/gates/` 的 G0–G7 依序跑;沒過退回 S8
2. `scripts/gates/smoke specs/{name}/spec.yaml`;**沒過就停,不派審查**
3. 派 `spec-oracle` 與 `code-adversary`(不傳 `model`),派完立刻 `scripts/gates/findings dispatched --gate G9|G10 --model <實際模型>`;
   Fable 額度用完 → 用 opus 重派一次並加 `--degraded`;不准退到 sonnet
   每條 finding 用 `findings add` 收,實跑重現 → `set confirmed` / `set void`(停在 proposed 算沒處理完)
4. `must_fix` / `overbuilt` → `scripts/gates/loop fix F-n` → 修 → 重跑 G0–G7 + 重現 → `loop resolved`
5. `ask_user` **不修**,留給 PR 留言問人;`style` 記下不動
6. `scripts/gates/findings check` 乾淨(或只剩 ask_user)後，stage 這次 commit 的完整內容（含
   `evidence/spec.approved.yaml`），再跑 `scripts/gates/dashboard specs/{name}/spec.yaml --pre-commit`
7. pre-commit 全綠才進 S10；它只允許 commit，絕不允許 auto-push。commit 後立即重跑不帶
   `--pre-commit` 的 delivery dashboard，只有已 commit 且乾淨的批准快照才可推送

**注意**

- **順序就是花錢的順序。** 功能不對其他免談:smoke 沒過連審都不審。
- 有 mode 6c 時,smoke 指令必須寫 `$SMOKE_RESULTS`:逐 Scenario 列 `ok:true`、完整 example 編號,
  並指向本輪 `$SMOKE_SCREENSHOTS`／`$SMOKE_ARTIFACTS` 的非空實際證據；checklist 不能當通過。
- 沒附重現的 `must_fix` / `ask_user` / `overbuilt`,`findings add` 會拒收 —— 那是證據規則,不是格式挑剔。
- `loop` 第 3 次 `fix` 會拒絕(parked)、解過又出現會拒絕(flipflop)、G10 重派第 2 次會拒絕。
  被拒絕就停,交給 PR 留言的「需要你決定」;人答了用 `loop decided F-n ship|hold|respec` 記,那是唯一的解除方式。
  換 id 再修會被 `findings add`(同 repro)與 `loop`(幽靈 id)雙雙拒收。
- 做到哪算夠 = 批准的 examples。審查者發現例子外的 bug 是 `ask_user`,不是叫實作者修。
- staged 的批准快照只是 `pending_commit`，不能當成 owner 批准證據。
