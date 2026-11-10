---
name: "workflow:dashboard"
description: "產出證據表(HTML + dashboard.json)：pre-commit 只驗候選樹可提交，delivery 才判定能不能自動推。"
category: Workflow
tags: [workflow, evidence, dashboard]
---

產出證據表。commit 前與 commit 後是兩個不同裁決：

**動作**

```bash
scripts/gates/dashboard specs/{name}/spec.yaml --pre-commit --trigger <原因> # 候選樹可否 commit；絕不自動推
scripts/gates/dashboard specs/{name}/spec.yaml --trigger <原因>  # commit 後 delivery；最後一行:自動推:可以 / 不行(原因)
scripts/gates/pr-comment specs/{name}/spec.yaml     # PR 留言的 markdown
scripts/gates/pr-comment specs/{name}/spec.yaml --check   # 退出碼 1 = 有事要人決定
```

**注意**

- **沒有一行需要你讀程式碼。** 留言頂端只有兩種:「✅ 全乾淨」或「⏸ 需要你決定」+ 選擇題。
- `--pre-commit` 的 staged 快照只是 `pending_commit`，不是 owner 批准證據；這個模式絕不會 auto-push。
- 預設 delivery 模式只接受已存在 `HEAD` 且工作樹乾淨的批准快照。
- 可達性排在最前面,和嚴重度分開排;smoke 證據要新鮮(工作樹指紋對得上),過期就是沒跑。
- G9/G10 派遣後工作樹變了就判「審查過期」;例外是修 finding 的小 diff(≤ 1 檔、≤ 40 行、無二進位檔,且派遣後有 `loop fix`)
  —— 依規則不重派,備註寫出檔數行數,「未重審」列出沒重審的檔,不擋推。
- 表上會顯示**審查活動量**(提出 N → 作廢 M → 證實 K)。一張只有綠勾的表會訓練人變成橡皮圖章。
- `auto_push: false` 的專案,dashboard 一律回「不行」,推之前把留言印給人看。
- `--trigger` = 這次為什麼又跑:`first` / `fix` / `merge-main` / `ci-red`,同一輪的 pre-commit 與 delivery 傳同一個;
  不知道就不傳(記 `unknown`)。寫進 `_yield.jsonl`,`runs --yield` 會統計。
