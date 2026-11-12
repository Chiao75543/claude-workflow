---
name: "workflow:escape"
description: "上線後才發現的 bug 用一句話登記成漏網紀錄:追查是哪張卡、本該哪一關擋到、為何沒擋到,寫進 specs/_escapes.jsonl,開一個小 PR。"
category: Workflow
tags: [workflow, escape, metrics]
---

人只講一句話(例:「iOS 背景回來後通話畫面卡住」)。其餘欄位你追查後填,**填完給人確認才開 PR**。

**1. 記下那句話與發現日期**(人沒說日期就用今天)。

**2. 追查(唯讀,不動任何在飛的卡)**

- 找出 bug 落在哪些檔案,用 `git log -S` / `git log -G` / `git blame` 找到引入它的 commit
- 那個 commit 是哪個 merge 帶進整合分支的;同一個 merge 帶進來的 `specs/<卡>/` 就是所屬卡
  - 不是 pipeline 的卡造成(手改、第三方、後端)→ `--card none --why outside`
  - 追查不出來 → `--card unknown`、`--why unknown`;不要猜
- 對照那張卡的 `spec.yaml`(有沒有寫到這個情境)、`evidence/findings.json`(審查有沒有提過、被判成什麼)、
  `evidence/dashboard.json`(當時哪些關過了、哪些被豁免)
- 判「本該由哪一關擋到」與「為何沒擋到」。選項與嚴重度的定義見 `scripts/gates/escape` 的說明

**3. 把要寫的欄位列成一張小表給人確認。** 人說好才往下;人改了就照人的。

**4. 開小 PR**(從整合分支開臨時 worktree,在那裡登記 —— 所屬卡要在整合分支的樹裡才查得到)

```bash
base="{INTEGRATION_BRANCH}"   # specs/pipeline.yaml 的 integration_branch
git fetch origin "$base"
wt=".worktrees/escape-$(date +%Y%m%d%H%M%S)"
git worktree add --detach "$wt" "origin/$base" && cd "$wt" || exit 1
line="$(scripts/gates/escape add --summary "<一句話>" --card <卡|none|unknown> --severity <blocker|major|minor> \
        --gate <關> --why <類別> --note "<為何沒擋到>" --found <YYYY-MM-DD>)" || exit 1
id="${line%% *}"
git switch -c "chore/escape-${id}"
git add specs/_escapes.jsonl && git commit -m "chore(escape): ${line}"
```

推與開 PR **各自單獨一條指令**(使用者層級的 push-guard hook 會擋「同一條指令裡有 push 又有整合分支名稱」):

```bash
git push -u origin "chore/escape-${id}"
```

```bash
gh pr create --base "$base" --title "chore(escape): ${line}" --body "<步驟 3 那張表>"   # GitLab:glab mr create
```

```bash
cd - && git worktree remove "$wt"
```

- `auto_push: false` → 停在 commit,把表給人看,人說推才推
- PR 由人 merge;不要自動合
- 兩筆還沒合的 PR 都在檔尾加一行,後合的那個會衝突 → rebase 到最新的整合分支,兩行都留

**看統計:** `scripts/gates/escape list`(讀的是當前 checkout 的檔;要看整合分支上的,先在主 checkout 拉到最新)。
