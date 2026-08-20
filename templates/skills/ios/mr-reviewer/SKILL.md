---
name: mr-reviewer
description: >
  審查專案的 Pull Request，發佈 inline comments 並產出評分報告。本實作（iOS template）使用 GitHub + `gh` CLI；其他 stack 可改用 `glab` 或對應工具。當使用者輸入 /review-mr 指令，或說「幫我 review PR」「審查 Pull Request」「檢查 MR/PR」「mr-reviewer」時，必須使用此技能包。
  Codex 扮演資深 Code Reviewer，透過 gh CLI 取得 PR diff，依 Clean Architecture / Optional Safety / SwiftUI 等維度審查，以 `gh api` 發佈 inline review comments，並發佈含 0–100 評分的總結報告。
  只要任務牽涉到 GitHub PR 審查、程式碼品質檢查、發佈 PR 評論，一律觸發此技能包。
compatibility: "需要 gh CLI（已認證）、bash"
---
> **套用注意**：本 template 以首個專案（MindEY）的具體規則與範例為示範；套用到新專案時，請將 MindEY 專屬細節（鐵則清單、web 對照路徑、端點與範例）替換為該專案 CLAUDE.md／架構文件的對應內容。

# GitHub PR Reviewer — Pull Request 審查 Agent

Codex 扮演資深 Code Reviewer，自動審查 GitHub PR、發佈 inline review comments，並產出含評分的總結報告。

> Skill 名稱維持 `mr-reviewer`、指令維持 `/review-mr` —— workflow-orchestrator 靠這個 convention name 派遣，不因平台換名。

## 觸發方式

```
/review-mr <PR_ID 或 PR_URL>
```

### 範例
```
/review-mr #123
/review-mr 123
/review-mr https://github.com/{owner}/{repo}/pull/123
```

---

## 執行流程

### Step 0 — Engine 選擇與派遣（強制第一步）

本 skill 名稱叫「Codex 扮演...」— 實際分析工作 **必須** 透過真正的 codex CLI 跑，不是主機端 Claude 自己角色扮演。第一步先判斷誰來分析、誰來貼留言：

```bash
codex_available=false
if command -v codex >/dev/null 2>&1 \
   && [ -d "$HOME/.claude/plugins/marketplaces/openai-codex" ]; then
    codex_available=true
fi
```

| 情境 | 分析者 | 貼留言者 | 派遣方式 |
|---|---|---|---|
| `codex_available=true`（推薦） | Codex CLI | **主 shell**（Claude，用 `gh` 代貼） | `Agent(subagent_type="codex:codex-rescue", prompt=…)` |
| `codex_available=false` fallback | Claude | Claude | `Agent(subagent_type="general-purpose")` + 把本 skill 完整內容打包進 prompt |
| User 明示 `--engine=claude` | Claude | Claude | 同 fallback |

**❌ 反模式**：主機 Claude 直接讀 diff、自己跑審查、貼留言（簽 `🤖 Reviewed by Codex` 但其實沒呼叫 codex）。這違反 skill 設計初衷，浪費掉多引擎複審的品質保證。

### Sandbox 網路限制（重要）

Codex 沙箱通常**無法**連到 GitHub API host（`api.github.com`，會回 `connect: operation not permitted`）。所以分工是：

- **Codex**：負責 read diff + analyze + 回傳 findings payload + summary markdown。**不呼叫任何 gh 指令、不打 GitHub API。**
- **主 shell（Claude，dispatcher）**：收到 codex 回傳的 payload 後，用 `gh api` + `gh pr comment` 把 inline comments 與 summary 代貼到 PR。

派遣 codex 時 prompt 要明確：「DO NOT call gh or GitHub API — return findings; dispatcher will relay via gh」。

完整 prompt template 範本見 workflow-orchestrator skill 的 `references/codex-mr-review-prompt-template.md` — **僅參考其結構**：該範本是 GitLab 版（glab + DiffNote、base/head/start SHA 收集），指令一律改用本 skill Step 5–6 的 gh / GitHub API 版，不可照抄。

### Step 1 — 解析 PR ID

從 `$ARGUMENTS` 中擷取純數字 PR ID：

| 輸入格式 | 解析結果 |
|---|---|
| `#123` | `123` |
| `123` | `123` |
| `https://github.com/{owner}/{repo}/pull/123` | `123` |

---

### Step 2 — 驗證 gh CLI

```bash
gh auth status
```

若未認證，停止並告知使用者執行 `gh auth login`。

---

### Step 3 — 取得 PR 資訊與 Diff

```bash
# PR 基本資訊（標題 / 描述 / 分支 / 狀態 / 變更規模）
gh pr view {PR_ID} --json title,body,baseRefName,headRefName,state,additions,deletions,changedFiles

# 完整 diff
gh pr diff {PR_ID}
```

同時讀取每個變更檔案的完整內容，確保理解上下文：

```bash
cat <changed_file_path>
```

若專案根目錄存在 `CLAUDE.md`，一併讀取作為專案規範（鐵則來源）；有 `docs/architecture.md` 也必讀（審查維度的權威來源）：

```bash
cat CLAUDE.md 2>/dev/null || echo "無 CLAUDE.md，使用預設規範"
cat docs/architecture.md 2>/dev/null || true
```

---

### Step 4 — 分析變更

對每個變更檔案，依以下維度逐一檢查，記錄問題（含檔案路徑與行號）：

#### 🔴 CRITICAL（必須修正）

**強制解包 / Crash 風險**
- 非測試碼使用 `!` 強制解包、`try!`、`as!` → 一律退（architecture.md §8）
- 隱式解包 Optional（如 `var name: String!`）承載可能為 nil 的伺服器資料

**架構違規（architecture.md §8）**
- Domain package import Supabase / SwiftUI / UIKit（Domain 零依賴是硬規則；SPM 已在編譯期擋，若 PR 改動 `Package.swift` 繞開防線直接退）
- View 直呼 Repository / APIClient（View 只吃 ViewModel 的值和 closure）
- `static let shared` / 任何 singleton（舊 `APIClient.shared` 讓全案零測試縫）
- 違反依賴方向 `App → Domain ← Data`；cross-feature 直接 import internal 型別
- Entity 帶 view concern（頭像 fallback、顯示字串格式化不放 Domain）

**鐵則違規（CLAUDE.md，踩過的坑）**
- server `created_at` 用 `Date` 直接承載——必須 decode 成 `ServerTimestamp` 保留原字串；`latest_seen` 回報一字不改（微秒精度）
- 註冊改用 SDK signUp（必走 `POST /api/auth/register` → 再 signInWithPassword）
- Realtime 用 broadcast（只准 postgres_changes）；`created_at` 無時區後綴未補 Z 當 UTC
- 吞錯誤改寫文案（斷網不准顯示成「帳密錯誤」；`DomainError.server` 的 `{error}` 繁中文案直顯）
- 移植 web 的 demo/mock fallback 或「不做清單」的假 UI

#### 🟡 WARNING（應修正）

**禁用模式**
- Magic numbers / Magic strings（未抽成具名常數）
- 大量被註解掉的程式碼
- 引入 Combine（全案 async/await only）或未經 owner 同意的新 SPM 套件

**品質問題**
- 函式超過 40 行
- ViewModel 未標 `@Observable @MainActor`，或未走建構子注入 UseCase
- UseCase 做成 protocol（慣例是具體 struct，mock 縫只開在 Repository）
- `Task` 生命週期未管理（未 cancel、無理由的 `Task.detached`）
- 錯誤未收斂進 `DomainError` 分類（raw error 直丟 UI）

#### 💡 SUGGESTION / SIMPLIFY（建議改進）

**SwiftUI 最佳實踐**
- View `body` 過大 → 拆子 View 或 computed property
- `@State` 應為 `private`；狀態能放子 View 就不上提
- `body` 內做重運算 / 格式化 → 移到 ViewModel
- 不必要的 `AnyView` 型別擦除、過度巢狀的 `GeometryReader`
- Preview 應用 `PreviewSupport/` 假 Repo 組真 UseCase，不打真網路

**可讀性 / 重構機會**
- 重複邏輯可抽成 extension 或 Domain 純函式
- 可提取的共用元件放 `MindEYDesignSystem`
- 命名可更具描述性

---

### Step 5 — 取得 repo 與 commit_id（取代 GitLab 的三 SHA + Token）

**GitHub 與 GitLab 定位機制不同，不要沿用舊習慣**：

- **不需要** `PRIVATE-TOKEN` header、不需要 curl —— `gh` 已認證，自帶 auth。
- **不需要** `base_sha` / `head_sha` / `start_sha` —— GitHub inline comment 定位只靠 **`commit_id` + `path` + `line` + `side`** 四個欄位。
- repo path 是 `owner/repo` 純字串，**不需要 URL encode**。

```bash
# {GITHUB_REPO}（owner/repo 形式），供 gh api 路徑使用
gh repo view --json nameWithOwner -q .nameWithOwner

# commit_id = PR head commit SHA
gh pr view {PR_ID} --json headRefOid -q .headRefOid
```

以下 `{GITHUB_REPO}`、`{PR_ID}` 均為 placeholder，執行前先代入實際值。

---

### Step 6 — 發佈 Inline Review Comments（**主 shell 負責**，不是 codex）

> ⚠️ 若 Step 0 派遣了 codex 來分析：codex 只回傳 findings payload，**留言一律由主 shell（dispatcher）用以下 gh 模式代貼**。codex 沙箱無法連 GitHub API host，硬要它貼會 silent fail。

每個問題發佈一則 inline comment（單行定位）：

```bash
gh api repos/{GITHUB_REPO}/pulls/{PR_ID}/comments \
  -f body=$'**[🔴 CRITICAL]** 問題標題\n\n**問題**: 具體描述問題\n\n**建議修正**:\n```swift\n// 修正後程式碼\n```\n\n---\n*🤖 Reviewed by Codex*' \
  -f commit_id=$(gh pr view {PR_ID} --json headRefOid -q .headRefOid) \
  -f path='App/Features/Chat/ChatViewModel.swift' \
  -F line=42 \
  -f side=RIGHT
```

若 comment 針對**多行區間**（如整個函式），`line` 填區間**末行**，再加兩個參數指定起點：

```bash
  -F start_line=起行 -f start_side=RIGHT
```

**定位欄位規則（只有 commit_id + path + line + side，沒有三 SHA）**：

| 情境 | 設定方式 |
|---|---|
| 針對新增 / 修改後的行 | `side=RIGHT`，`line` = head 版本行號 |
| 針對被刪除的行 | `side=LEFT`，`line` = base 版本行號 |
| 多行區間 | 加 `-F start_line=<起行> -f start_side=RIGHT`，`line` = 區間末行 |
| 重新命名的檔案 | `path` 一律填**新路徑**（repo 相對路徑） |

驗證：成功時回傳 JSON 含 `id` 與 `path`。若回 `422 Validation Failed`（訊息含 `line must be part of the diff`），代表行號不在 diff hunk 內 —— GitHub **不會**像 GitLab 那樣默默降級成一般 Note，而是直接拒絕；改用該檔 diff 內的行號，或把該 finding 移到總結留言。

**Comment body 格式依嚴重程度**：
- CRITICAL：`**[🔴 CRITICAL]**`
- WARNING：`**[🟡 WARNING]**`
- SUGGESTION：`**[💡 SUGGESTION]**`
- SIMPLIFY：`**[🔧 SIMPLIFY]**`

---

### Step 7 — 計算評分

**基礎分 100 分，依問題數扣分**：

| 問題類型 | 每個扣分 |
|---|---|
| CRITICAL | -15 分 |
| WARNING | -5 分 |
| SUGGESTION / SIMPLIFY | -1 分 |
| 最低分 | 0 分 |

**五維度加權評分**（分析輔助；**Overview 分數與評級一律以扣分制為準**，五維表用於定位弱項，不重算總分）：

| 維度 | 權重 |
|---|---|
| Architecture Compliance | 25% |
| Code Quality | 25% |
| Security & Optional Safety | 20% |
| Maintainability | 15% |
| SwiftUI & iOS Best Practices | 15% |

**評級對照**：

| 分數 | 評級 |
|---|---|
| 90–100 | ✅ Excellent |
| 75–89 | 👍 Good |
| 60–74 | ⚠️ Acceptable（需要修正）|
| 40–59 | ❗ Needs Improvement（建議大幅修改）|
| 0–39 | 🚫 Poor（建議重新設計）|

---

### Step 8 — 核准結論

**GitHub 限制**：PR author 不能對自己的 PR 送 review（`gh pr review --approve` / `--request-changes` 會回 `422 Can not approve your own pull request`），而本 skill 常以 author 同帳號執行。所以**結論一律用 `gh pr comment` 發佈**，不用 `gh pr review`；gate 輸出格式照舊。

發佈總結報告後，給出**明確的合併結論**：

#### ✅ 可以 Merge（零 CRITICAL）
```
✅ 可以 Merge

CRITICAL：0 個
WARNING：X 個（建議修正但不阻擋）
品質評分：XX / 100

→ 自動產出審查報告...
```

滿足條件後，**立即執行 reporter 技能包**產出本地報告。

「可以 Merge」只是**結論**，不是動作：merge 一律由 owner 人工 plain merge。本 skill **絕不執行** `gh pr merge`、絕不 push。

#### ❌ 不可 Merge（有 CRITICAL）
```
❌ 不可 Merge，請修正後重新執行 /review-mr

待修正項目：
- [C-1] ChatViewModel.swift:42 — 吞錯改寫錯誤文案
- [C-2] MessageDTO.swift:18 — created_at 用 Date 直接承載

修正完成後執行：/review-mr {PR_ID}
```

Reporter **不觸發**，不產出報告。

---

### Step 9 — 發佈總結報告

```bash
gh pr comment {PR_ID} --body "$(cat <<'EOF'
## 📋 Code Review Summary

### Overview Score: **XX / 100** — [評級]

| 評分項目 | 分數 | 權重 | 加權分 |
|---------|------|------|--------|
| Architecture Compliance | X/100 | 25% | X |
| Code Quality | X/100 | 25% | X |
| Security & Optional Safety | X/100 | 20% | X |
| Maintainability | X/100 | 15% | X |
| SwiftUI & iOS Best Practices | X/100 | 15% | X |

### 審查範圍
- 審查了 X 個檔案
- 總變更：+Y / -Z 行

### 發現問題

#### 🔴 Critical Issues（X 個）
- `FileA.swift:42` — 問題描述

#### 🟡 Warnings（X 個）
- `FileB.swift:18` — 問題描述

#### 💡 Suggestions（X 個）
- `FileC.swift:55` — 建議描述

#### 🔧 Code Simplification（X 個）
- `FileD.swift:30` — 簡化建議

### 正面評價
- ✅ 列出本次 PR 做得好的地方

### 整體評估
整體評估說明

### 下一步
- [ ] 修正所有 Critical Issues
- [ ] 檢視 Warnings
- [ ] 考慮 Suggestions 與 Simplification 建議

---
*🤖 Reviewed by Codex*
EOF
)"
```

---

### Step 10 — 列出 Review Threads（給 fixer / Stage 11 用）

fix loop 需要逐 thread 處理 inline comments。GitHub 的 review threads 與解決狀態要走 **GraphQL**（REST 拿不到 `isResolved`）：

```bash
gh api graphql -f query='
query($owner: String!, $repo: String!, $pr: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $pr) {
      reviewThreads(first: 100) {
        nodes {
          id
          isResolved
          isOutdated
          path
          line
          comments(first: 10) {
            nodes { body author { login } }
          }
        }
      }
    }
  }
}' -f owner='{OWNER}' -f repo='{REPO}' -F pr={PR_ID}
```

- `{GITHUB_REPO}` 在這裡拆成 `{OWNER}` 與 `{REPO}` 兩段帶入；`pr` 是數字用 `-F`。
- `id` 是 thread node id —— fixer 修完後以 GraphQL mutation `resolveReviewThread(input: {threadId: $id})` 標記解決，並在 thread 內回覆說明。
- `isResolved=false` 的 threads 才是待辦；`isOutdated=true` 表示該行已被後續 commit 改動，需人工比對新行號。

---

## 注意事項

- **Step 0 強制**：先做 engine detection，能用 codex 就 dispatch codex；主機 Claude 不要自己角色扮演 Codex。
- **Sandbox 邊界**：codex 產分析 → dispatcher（主 shell）用 `gh` 代貼。不要讓 codex 直接呼叫 gh / GitHub API。
- **忘掉 GitLab 習慣**：沒有 `PRIVATE-TOKEN`、沒有 `base_sha/head_sha/start_sha`、不需要 curl、repo path 不需 URL encode。inline 定位只靠 `commit_id + path + line + side`。
- **絕不 merge / push**：本 skill 只讀 diff + 貼留言。merge 一律由 owner 人工 plain merge（不可逆動作必經人工確認）。
- **一律繁體中文**撰寫 comment 描述（技術名詞保留英文）
- **每則 comment 必須簽名** `*🤖 Reviewed by Codex*`
- **先讀完整檔案**再審查，避免誤判需要上下文的程式碼
- **建設性回饋**：每個問題都附上建議的修正方式與範例程式碼
- **冪等性**：若 PR 已有 `🤖 Reviewed by Codex` 簽名的 comment（用 Step 10 的 threads query 或 `gh pr view {PR_ID} --json comments` 檢查），先檢查再決定是否重貼（避免 duplicate）。User 可用 `--re-review` 強制重跑。

## 常見問題處理

| 狀況 | 處理方式 |
|---|---|
| gh 未認證 | 停止，提示 `gh auth login` |
| inline comment 回 `422`（`line must be part of the diff`） | 行號不在 diff hunk 內：確認用 head 版本行號、該行確實出現在 `gh pr diff` 輸出；不行就移到總結留言 |
| `422 Can not approve your own pull request` | 正常 —— author 不能 review 自己的 PR；本 skill 規定結論用 `gh pr comment`，不要改用 `gh pr review` |
| force-push 後 commit_id 失效 | 重新 `gh pr view {PR_ID} --json headRefOid -q .headRefOid` 取新 SHA 再貼 |
| PR 已關閉或不存在 | 告知使用者確認 PR ID |
| CLAUDE.md 不存在 | 使用技能包內建規範繼續審查 |
| Codex 沙箱 `connect: operation not permitted` 到 GitHub | 正常 — codex 不該直接打 GitHub；改由主 shell 用 gh 代貼，codex 只回傳 findings payload |
| Codex 找不到（`codex_available=false`） | Fallback 到 Claude general-purpose agent + 把本 skill 完整內容打包進 prompt；簽名仍用 `🤖 Reviewed by Codex` 但在 chat 標示「fallback engine」 |
| GitHub Enterprise（API host 與 github.com 不同） | 用 `GH_HOST` 環境變數或 `gh auth login --hostname <host>` 切換；`{GITHUB_REPO}` 寫法不變 |

## 觸發點

| 觸發者 | 場景 |
|---|---|
| User 手動 | `/review-mr <PR>` 直接審查任何 PR |
| workflow-orchestrator | Stage 10.5（push + create PR 之後自動 advisory pass）|
| workflow-orchestrator | Stage 11 fix loop 起始時用 Step 10 的 review threads query fetch + classify comments |
