---
name: review-fixer
description: >
  修復 Code Review 或 GitLab MR Review 發現的問題，修完後自動驗證並在 GitLab 回覆已解決。當使用者輸入 /fix 指令，或說「幫我修 review 問題」「修復 MR comments」「fix review issues」「修 code review」「處理 review 意見」時，必須使用此技能包。
  Claude 扮演資深 RD 角色，從 GitLab MR 讀取 review comments（CRITICAL / WARNING），參照 OpenSpec change 規格確保修復符合規格，逐一修正程式碼，完成後執行 /verify 驗證，並透過 GitLab API 回覆已解決且 resolve 每則 discussion。
  只要任務牽涉到修復 code review 問題、處理 MR review comments、解決 review 意見、修正 CRITICAL/WARNING 問題，一律觸發此技能包。
compatibility: "需要 glab CLI（已認證）、curl、bash"
---

# Review Fixer — Review 問題修復 Agent

Claude 扮演資深 RD，讀取 GitLab MR 上的 review comments，逐一修復 CRITICAL / WARNING 問題，修完後驗證並在 GitLab 標記已解決。

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

### Step 5 — 逐一修復

對每個待修復問題，按以下流程處理：

#### 5a. 讀取完整檔案上下文

先讀取問題所在檔案的完整內容，理解上下文後再修改。不要只看 diff 片段。

```bash
cat <file_path>
```

#### 5b. 分析問題根因

理解 comment 指出的問題本質：
- comment 中的「建議修正」程式碼片段是否合理？
- 修復是否會影響其他地方？
- 修復是否符合 OpenSpec 規格定義？

#### 5c. 套用修正

使用 Edit tool 修改程式碼。修復時遵守以下原則：

| 原則 | 說明 |
|---|---|
| 最小變更 | 只修問題本身，不順便重構周圍程式碼 |
| 符合規格 | 若有 OpenSpec change 參考，修復後的行為必須與規格一致 |
| 遵守專案規範 | 依照 CLAUDE.md 的編碼規則（無 `!!`、無 region、無 magic number 等） |
| 保持一致性 | 修復風格與現有程式碼一致 |

#### 5d. 記錄修復結果

每修完一個問題，記錄修復細節供後續回報用：

```
[C-1] ✅ 已修復
  檔案：XxxViewModel.kt:42
  修復內容：新增 E002 InsufficientBalance 錯誤處理，導航至儲值頁
  discussion_id: abc123
```

---

### Step 6 — 執行驗證（/verify）

所有問題修完後，執行 code-reviewer 技能包的驗證流程：

1. 取得最新 git diff
2. 若有 OpenSpec change 參考，對照 specs/ 進行規格合規審查
3. 確認所有 CRITICAL / WARNING 問題已解決

```
驗證結果：
  CRITICAL: 0 個 ✅
  WARNING:  0 個 ✅
  品質評分: XX / 100
  結論: ✅ 可以 Commit
```

若驗證仍有新問題：
```
⚠️ 驗證發現新問題：
  [NEW-W-1] XxxRepositoryImpl.kt:35 — 新引入的 magic number

是否繼續修復新問題？(ok / 跳過)
```

---

### Step 7 — 回覆 GitLab Comments 並 Resolve

驗證通過後，對每個已修復的 discussion 執行兩個動作：

#### 7a. 回覆已解決訊息

```bash
curl -s --request POST \
  --header "PRIVATE-TOKEN: $TOKEN" \
  --header "Content-Type: application/json" \
  --data '{"body": "✅ 已修復 — <修復摘要>\n\n---\n*🤖 Fixed by Claude Code*"}' \
  "https://<GITLAB_HOST>/api/v4/projects/$PROJECT_PATH_ENCODED/merge_requests/<MR_IID>/discussions/<DISCUSSION_ID>/notes"
```

#### 7b. Resolve Discussion

```bash
curl -s --request PUT \
  --header "PRIVATE-TOKEN: $TOKEN" \
  --header "Content-Type: application/json" \
  --data '{"resolved": true}' \
  "https://<GITLAB_HOST>/api/v4/projects/$PROJECT_PATH_ENCODED/merge_requests/<MR_IID>/discussions/<DISCUSSION_ID>"
```

驗證回應 HTTP 200 且 `resolved: true`。

---

### Step 8 — 產出修復摘要

```
════════════════════════════════════════
📋 Review Fix Report — MR !<ID>
════════════════════════════════════════

📊 修復摘要
┌────────────────────────┬────────┐
│ 待修復問題              │ X 個   │
│ 已修復                  │ X 個   │
│ 跳過                    │ X 個   │
│ GitLab Resolved         │ X 個   │
└────────────────────────┴────────┘

════════════════════════════════════════
✅ 已修復問題
════════════════════════════════════════

[C-1] XxxViewModel.kt:42 — E002 錯誤處理遺漏
  修復：新增 InsufficientBalance case，導航至儲值頁
  GitLab: ✅ 已回覆 & Resolved

[W-1] XxxViewModel.kt:28 — Magic Number
  修復：抽出 RETRY_DELAY_MS = 3000L 常數
  GitLab: ✅ 已回覆 & Resolved

════════════════════════════════════════
📊 驗證結果
════════════════════════════════════════
品質評分：XX / 100
CRITICAL：0 個
WARNING：0 個
結論：✅ 可以 Commit / Merge

════════════════════════════════════════
📌 下一步
════════════════════════════════════════
- [ ] git add & commit 修復的檔案
- [ ] 推送至遠端分支
- [ ] 通知 Reviewer 重新檢視 MR

---
*🤖 由 Claude Code 自動修復*
```

---

## 與其他技能包的整合

| 觸發來源 | 行為 |
|---|---|
| `/review-mr` 完成後有 CRITICAL/WARNING | 提示使用者：「發現 X 個問題，是否執行 /fix !<MR_ID> 修復？」 |
| `/fix` 獨立執行 | 完整流程：讀取 comments → 修復 → 驗證 → resolve |
| `/workflow` Pipeline 中 | Stage 3a verify 有問題時，可呼叫 fix 修復後重新驗證 |

---

## 常見問題處理

| 狀況 | 處理方式 |
|---|---|
| glab 未認證 | 停止，提示 `glab auth login` |
| MR 無 review comments | 告知無待修復問題，建議先執行 `/review-mr` |
| Comment 無法辨識嚴重程度 | 歸類為 UNKNOWN，詢問使用者是否納入修復 |
| 修復後驗證仍有新問題 | 列出新問題，詢問是否繼續修復 |
| Resolve API 失敗 | 列出失敗的 discussion_id，提示使用者手動 resolve |
| OpenSpec 規格與 comment 建議衝突 | 以 OpenSpec 規格為準，在回覆中說明依規格修復 |
| 修改檔案不在 MR diff 範圍 | 警告使用者，確認是否仍要修改 |
| Comment 來自非 Claude 的 reviewer | 同樣處理，但回覆中標明「依 reviewer 意見修復」 |
