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
3. 派 `spec-oracle` 與 `code-adversary`(fable);每條 finding 用 `scripts/gates/findings add` 收,
   實跑重現 → `set confirmed` / `set void`
4. `must_fix` / `overbuilt` → `scripts/gates/loop fix F-n` → 修 → 重跑 G0–G7 + 重現 → `loop resolved`
5. `ask_user` **不修**,留給 PR 留言問人;`style` 記下不動
6. `scripts/gates/findings check` 乾淨(或只剩 ask_user)→ 進 S10

**注意**

- **順序就是花錢的順序。** 功能不對其他免談:smoke 沒過連審都不審。
- 沒附重現的 `must_fix` / `ask_user` / `overbuilt`,`findings add` 會拒收 —— 那是證據規則,不是格式挑剔。
- `loop` 第 3 次 `fix` 會拒絕(parked)、解過又出現會拒絕(flipflop)、G10 重派第 2 次會拒絕。
  被拒絕就停,交給 PR 留言的「需要你決定」,不要換個 id 再修。
- 做到哪算夠 = 批准的 examples。審查者發現例子外的 bug 是 `ask_user`,不是叫實作者修。
