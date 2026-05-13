---
name: review-fixer
description: >
  修復 Code Review 或 GitLab MR Review 發現的問題。當使用者輸入 /fix 指令，或說「幫我修 review 問題」「修復 MR comments」「fix review issues」「修 code review」「處理 review 意見」時，必須使用此技能包。
  Claude 扮演資深 RD 角色，**嚴格遵守專案 `AGENTS.md` 的 PR Comment Fix Workflow（如 Stage 11）規範**：**一個 comment 一個 commit**、修前**先出 fix PLAN 等人工核可**、commit 帶指定 footer、**不自動 push、不自動 resolve discussion**。修完僅貼修復摘要 reply，是否 resolve 留給人工驗證後由 pipeline 處理。
  只要任務牽涉到修復 code review 問題、處理 MR review comments、解決 review 意見、修正 CRITICAL/WARNING 問題，一律觸發此技能包。
compatibility: "需要 glab CLI（已認證）、curl、bash"
---

# Review Fixer — Review 問題修復 Agent

Claude 扮演資深 RD，讀取 GitLab MR 上的 review comments，**逐個**修復 CRITICAL / WARNING 問題。

## 與專案 AGENTS.md 的契約（**最高優先**）

專案 `AGENTS.md` 內的 PR Comment Fix Workflow（典型寫在 Stage 11）是本 skill 的硬性規範，**任何衝突以 AGENTS.md 為準**。預設 contract：

- **一個 comment 一個 commit**，禁止 batch
- 修前**先產出 fix PLAN**（files / changes / spec mapping / risks / confidence），**等人工核可**才動 Edit
- commit footer 須含 `Comment:` / `PR:` / `Spec:` / `Scenarios:` / `AI-assisted:`
- **不自動 push、不自動 mark discussion as resolved** —— Resolve 留給人工驗證 + pipeline 處理

若專案 AGENTS.md 沒寫對應規範，採用以上預設。若 AGENTS.md 明文允許 auto-resolve / push，遵循 AGENTS.md。

## 觸發方式

```
/fix <MR_ID> [--spec <OpenSpec change>] [--include-suggestions]
```

### 範例
```
/fix !123
/fix 456 --spec etf-curated-themes
/fix !789 --include-suggestions
```

### 參數說明

| 參數 | 說明 |
|---|---|
| `<MR_ID>` | GitLab MR 編號（支援 `!123`、`123`、完整 URL） |
| `--spec <OpenSpec change>` | OpenSpec change 名稱或路徑，用於確保修復符合規格（選用；無則從 MR description / branch name 推斷） |
| `--include-suggestions` | 一併修復 SUGGESTION 等級問題（預設只修 CRITICAL + WARNING） |

---

## 執行流程

### Step 1 — 解析參數與驗證環境

從 `$ARGUMENTS` 中擷取 MR ID（同 mr-reviewer 的解析邏輯）。

```bash
glab auth status
```

若未認證，停止並告知使用者執行 `glab auth login`。

---

### Step 2 — 讀取 MR Review Comments

```bash
# 取得 MR 基本資訊
glab mr view <MR_ID>

# 取得 GitLab host 和 project path（支援自建 GitLab）
REMOTE_URL=$(git remote get-url origin)
GITLAB_HOST=$(echo "$REMOTE_URL" | sed -E 's#https?://([^/]+).*#\1#' | sed -E 's#.*@([^:]+).*#\1#')
PROJECT_PATH=$(echo "$REMOTE_URL" | sed -E 's#https?://[^/]+/##' | sed -E 's#.*:##' | sed 's/\.git$//')
PROJECT_PATH_ENCODED=$(echo "$PROJECT_PATH" | sed 's/\//%2F/g')

# 取得 API Token（macOS 相容）
TOKEN=$(glab auth status -t 2>&1 | grep 'Token:' | awk '{print $NF}')

# 取得所有 discussions（包含 inline comments）
curl -s --header "PRIVATE-TOKEN: $TOKEN" \
  "https://$GITLAB_HOST/api/v4/projects/$PROJECT_PATH_ENCODED/merge_requests/<MR_IID>/discussions?per_page=100" \
  | python3 -c "
import sys, json
discussions = json.load(sys.stdin)
for d in discussions:
    for note in d.get('notes', []):
        if note.get('resolvable') and not note.get('resolved'):
            print(f'---')
            print(f'discussion_id: {d[\"id\"]}')
            print(f'note_id: {note[\"id\"]}')
            print(f'body: {note[\"body\"]}')
            if note.get('position'):
                pos = note['position']
                print(f'file: {pos.get(\"new_path\", pos.get(\"old_path\", \"unknown\"))}')
                print(f'line: {pos.get(\"new_line\", pos.get(\"old_line\", \"?\"))}')
"
```

---

### Step 3 — 分類與篩選問題

從 comment body 中識別問題嚴重程度（review-mr skill 使用的標記格式）：

| Comment 標記 | 嚴重程度 | 預設處理 |
|---|---|---|
| `[CRITICAL]` 或 `[🔴 CRITICAL]` | CRITICAL | 必修 |
| `[WARNING]` 或 `[🟡 WARNING]` | WARNING | 必修 |
| `[SUGGESTION]` 或 `[💡 SUGGESTION]` | SUGGESTION | 僅 `--include-suggestions` 時修復 |
| `[SIMPLIFY]` 或 `[🔧 SIMPLIFY]` | SIMPLIFY | 僅 `--include-suggestions` 時修復 |
| 無標記 | UNKNOWN | 由 Claude 判斷是否為需修復的問題 |

產出待修復清單：

```
📋 待修復問題清單 — MR !<ID>

🔴 CRITICAL（X 個）— 必須修復
  [C-1] XxxViewModel.kt:42 — E002 錯誤處理遺漏
        discussion_id: abc123
  [C-2] XxxDataSource.kt:18 — ApiResponse.data 使用 !!
        discussion_id: def456

🟡 WARNING（X 個）— 需要修復
  [W-1] XxxViewModel.kt:28 — Magic Number
        discussion_id: ghi789

💡 SUGGESTION（X 個）— 可選修復
  [S-1] XxxScreen.kt:65 — 可提取共用元件
        discussion_id: jkl012

修復範圍：CRITICAL + WARNING（共 X 個）
是否同時修復 SUGGESTION？請輸入 --include-suggestions 或 ok 繼續
```

等待使用者確認後進入 Step 4。

---

### Step 4 — 讀取 OpenSpec change（強烈建議）

若提供了 `--spec` 參數，讀取 `openspec/changes/<name>/` 內：

| 檔案 | 修復參考用途 |
|---|---|
| `specs/*.md` | Requirement × Scenario，確認修復後行為與規格一致 |
| `android.md` | API Contract + Navigation，確認介面修復符合規格 |
| `design.md` | Domain Model，確認結構修復正確 |
| `tasks.md` | 確認修復後不破壞既有任務勾選的完成度 |

若未提供 `--spec`，從 MR description / branch name (`feat/<ticket>-<spec-name>`) 嘗試推斷對應的 OpenSpec change。**找不到對應 OpenSpec change** 時：先要求使用者指明（或先建立 / 遷移成 canonical spec），再開始修復；不另走 fallback。CLAUDE.md 專案規範始終適用。

---

### Step 5 — 逐一處理每個 comment（**per-comment loop**）

對清單上每個待修復的 comment 走以下子流程；**完成一個 comment 才能進到下一個**：

#### 5a. 讀取完整檔案上下文

先讀取問題所在檔案的完整內容，理解上下文後再規劃修改。不要只看 diff 片段。

```bash
cat <file_path>
```

#### 5b. 產出 fix PLAN（**等人工核可才往下**）

依專案 `AGENTS.md` 要求，**先出 plan、不要直接 Edit**。Plan 須含以下 5 欄：

```
🛠 Fix PLAN for [C-1] XxxViewModel.kt:42

Files       : XxxViewModel.kt （唯一檔案）
Changes     : - handleE002() 新增 InsufficientBalance branch
              - 在 errorAction 加 NavigateToTopUp(amount)
Spec mapping: openspec/changes/<name>/specs/<name>/spec.md
              Requirement: 「不足餘額處理」/ Scenario: 「E002 出現時導航至儲值」
Risks       : Navigation 跨 feature；確認 TopUpRoute 已在 NavigationGraph 註冊
Confidence  : High（spec 明確、單檔修改）

請確認 PLAN，回 "ok" 進入修改，或提出調整。
```

**等使用者明確回應後**才進 5c。任何非 "ok" 的回應（含「再想想」「等等」）都視為「不要動」。

#### 5c. 套用最小修正

使用 Edit tool 修改。原則：

| 原則 | 說明 |
|---|---|
| 最小變更 | 只修這一個 comment 指出的問題，不順手重構周圍程式碼 |
| 符合規格 | 若有 OpenSpec change 參考，修復後的行為必須與規格一致 |
| 遵守專案規範 | 依照 CLAUDE.md 編碼規則（無 `!!`、無 region、無 magic number 等） |
| 一致性 | 修復風格與現有程式碼一致 |

#### 5d. 驗證單次修改

只跑針對這次變更的快速驗證：

1. 取最新 `git diff`（只看本次修改的檔案）
2. 若有 OpenSpec 參考，對該 Scenario 做點對點比對
3. 確認沒新增 CRITICAL / WARNING

通過才進 5e；失敗回 5b 重出 PLAN。

#### 5e. Commit（**一個 comment 一個 commit**）

使用以下 footer 格式（**必填**，依 `AGENTS.md`）：

```
fix(review): {scope} address {file}:{line} - {summary}

Comment: {reviewer_name} on {file}:{line}
PR: !{MR_IID}
Spec: openspec/changes/{name}/specs/{name}/spec.md
Scenarios: {scenario-name}
AI-assisted: claude
```

**禁止 batch 多 comment**。Commit 後**不 push**。

#### 5f. Reply on the discussion（**informational only — 不 resolve**）

在該 discussion 貼修復摘要，明確標示「待人工驗證 + pipeline resolve」：

```bash
curl -s --request POST \
  --header "PRIVATE-TOKEN: $TOKEN" \
  --header "Content-Type: application/json" \
  --data '{"body": "Fix proposed in commit <SHA>. 變更摘要：<one-liner>.\n\n依 AGENTS.md，**未自動 resolve**，等 reviewer 確認 diff 後由 pipeline 處理。\n\n---\n*🤖 Fix proposal by Claude Code*"}' \
  "https://<GITLAB_HOST>/api/v4/projects/$PROJECT_PATH_ENCODED/merge_requests/<MR_IID>/discussions/<DISCUSSION_ID>/notes"
```

**禁止呼叫 `PUT .../discussions/<id>` resolved=true**。Resolve 由人工觸發 / pipeline 完成。

#### 5g. 進入下一個 comment

回到 5a 處理下一個。沒有下一個就進 Step 6。

---

### Step 6 — 產出修復摘要（**並提醒人工驗證**）

```
════════════════════════════════════════
📋 Review Fix Report — MR !<ID>
════════════════════════════════════════

📊 修復摘要
┌────────────────────────────┬────────┐
│ 待修復 comment              │ X 個   │
│ 已 commit fix proposal      │ X 個   │
│ 跳過                        │ X 個   │
│ Auto-resolved (應為 0)      │ 0 個   │
└────────────────────────────┴────────┘

════════════════════════════════════════
✅ 已提案修復（每筆對應一個 commit）
════════════════════════════════════════

[C-1] XxxViewModel.kt:42 — E002 錯誤處理遺漏
  Commit: <SHA1>
  GitLab reply: ✅ 已貼修復摘要（未 resolve）

[W-1] XxxViewModel.kt:28 — Magic Number
  Commit: <SHA2>
  GitLab reply: ✅ 已貼修復摘要（未 resolve）

════════════════════════════════════════
📌 下一步（**人工 / Reviewer 操作**）
════════════════════════════════════════
- [ ] 人工檢視每個 commit 的 diff 是否真的解決 comment
- [ ] 確認後 `git push` 推上去（本 skill 不自動 push）
- [ ] Pipeline 重跑通過後，由 pipeline 或 reviewer 手動 resolve discussion
- [ ] 本 skill **不會** mark resolved（依 AGENTS.md）

---
*🤖 Fix proposals by Claude Code — pending human verification*
```

---

## 與其他技能包的整合

| 觸發來源 | 行為 |
|---|---|
| `/review-mr` 完成後有 CRITICAL/WARNING | 提示使用者：「發現 X 個問題，是否執行 /fix !<MR_ID> 修復？」 |
| `/fix` 獨立執行 | per-comment 流程：讀取 → PLAN → 人工核可 → 修 → commit → 貼 reply（**不 resolve**、**不 push**） |
| `/workflow` Pipeline 中 | Stage 3a verify 有問題時，可呼叫 fix 修復後重新驗證 |

---

## 常見問題處理

| 狀況 | 處理方式 |
|---|---|
| glab 未認證 | 停止，提示 `glab auth login` |
| MR 無 review comments | 告知無待修復問題，建議先執行 `/review-mr` |
| Comment 無法辨識嚴重程度 | 歸類為 UNKNOWN，詢問使用者是否納入修復 |
| 修復後驗證仍有新問題 | 列出新問題，詢問是否繼續修復 |
| 使用者要求自動 resolve | 拒絕並引用專案 `AGENTS.md` PR Comment Fix Workflow：Resolve 由人工驗證後處理；本 skill 不執行 |
| OpenSpec 規格與 comment 建議衝突 | 以 OpenSpec 規格為準，在回覆中說明依規格修復 |
| 修改檔案不在 MR diff 範圍 | 警告使用者，確認是否仍要修改 |
| Comment 來自非 Claude 的 reviewer | 同樣處理，但回覆中標明「依 reviewer 意見修復」 |
