---
name: gitlab-mr-reviewer
description: >
  審查 GitLab Merge Request，發佈 inline comments 並產出評分報告。當使用者輸入 /review-mr 指令，或說「幫我 review MR」「審查 Merge Request」「檢查 GitLab MR」「gitlab-mr-reviewer」時，必須使用此技能包。
  Codex 扮演資深 Code Reviewer，透過 glab CLI 取得 MR diff，依 Clean Architecture / Null Safety / Compose 等維度審查，以 curl 發佈 DiffNote inline comments，並發佈含 0–100 評分的總結報告。
  只要任務牽涉到 GitLab MR 審查、程式碼品質檢查、發佈 MR 評論，一律觸發此技能包。
compatibility: "需要 glab CLI（已認證）、curl、bash"
---

# GitLab MR Reviewer — Merge Request 審查 Agent

Codex 扮演資深 Code Reviewer，自動審查 GitLab MR、發佈 inline DiffNote comments，並產出含評分的總結報告。

## 觸發方式

```
/review-mr <MR_ID 或 MR_URL>
```

### 範例
```
/review-mr !123
/review-mr 123
/review-mr https://gitlab.com/your-org/your-repo/-/merge_requests/123
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
| `codex_available=true`（推薦） | Codex CLI | **主 shell**（Claude） | `Agent(subagent_type="codex:codex-rescue", prompt=…)` |
| `codex_available=false` fallback | Claude | Claude | `Agent(subagent_type="general-purpose")` + 把本 skill 完整內容打包進 prompt |
| User 明示 `--engine=claude` | Claude | Claude | 同 fallback |

**❌ 反模式**：主機 Claude 直接讀 diff、自己跑審查、貼留言（簽 `🤖 Reviewed by Codex` 但其實沒呼叫 codex）。這違反 skill 設計初衷，浪費掉多引擎複審的品質保證。

### Sandbox 網路限制（重要）

Codex 沙箱通常**無法**連到 GitLab API host（會回 `connect: operation not permitted`）。所以分工是：

- **Codex**：負責 read diff + analyze + 回傳 findings payload + summary markdown。**不貼任何 GitLab 留言。**
- **主 shell（Claude）**：收到 codex 回傳的 payload 後，用 `curl` + `glab` 把 inline DiffNote 與 summary 貼到 MR。

派遣 codex 時 prompt 要明確：「DO NOT curl GitLab — return findings; dispatcher will relay」。

完整 prompt template 範本見 workflow-orchestrator skill 的 `references/codex-mr-review-prompt-template.md`。

### Step 1 — 解析 MR ID

從 `$ARGUMENTS` 中擷取純數字 MR ID：

| 輸入格式 | 解析結果 |
|---|---|
| `!123` | `123` |
| `123` | `123` |
| `https://gitlab.com/.../merge_requests/123` | `123` |

---

### Step 2 — 驗證 glab CLI

```bash
glab auth status
```

若未認證，停止並告知使用者執行 `glab auth login`。

---

### Step 3 — 取得 MR 資訊與 Diff

```bash
# MR 基本資訊
glab mr view <MR_ID>

# 完整 diff
glab mr diff <MR_ID>
```

同時讀取每個變更檔案的完整內容，確保理解上下文：

```bash
cat <changed_file_path>
```

若專案根目錄存在 `CLAUDE.md`，一併讀取作為專案規範：

```bash
cat CLAUDE.md 2>/dev/null || echo "無 CLAUDE.md，使用預設規範"
```

---

### Step 4 — 分析變更

對每個變更檔案，依以下維度逐一檢查，記錄問題（含檔案路徑與行號）：

#### 🔴 CRITICAL（必須修正）

**API Response Null Safety**
- `ApiResponse.data` 使用 `!!` → 禁用，改用 `requireData()` / `getDataOrNull()` / `mapData()`
- 任何可能 Crash 的強制解包

**架構違規**
- Cross-feature direct import（跨 feature 直接 import internal class）
- ViewModel 持有 View 參考
- Coroutine 在非 `viewModelScope` 啟動（記憶體洩漏）
- 違反 Clean Architecture 依賴方向（UI → ViewModel → UseCase → Repository → DataSource）

#### 🟡 WARNING（應修正）

**禁用模式**
- `// region` block 使用
- Magic numbers / Magic strings（未抽成具名常數）
- 大量被註解掉的程式碼

**品質問題**
- 函式超過 40 行
- StateFlow / SharedFlow 使用錯誤
- `Result<T>` 未正確使用

#### 💡 SUGGESTION / SIMPLIFY（建議改進）

**Compose 最佳實踐**
- Composable 命名：UI 元件用 PascalCase 名詞，回傳值用 camelCase
- Modifier 參數順序：必填參數後、選填參數前、callback 最後
- Modifier 只傳給最外層 layout，不重複傳遞
- Recomposition 最小化（lambda 是否被記憶）

**可讀性 / 重構機會**
- 重複邏輯可抽成 extension function
- 可提取的共用 Composable
- 命名可更具描述性

---

### Step 5 — 取得 SHA refs 與 API Token

```bash
# 取得 project path（從 git remote）
git remote get-url origin | sed 's/.*gitlab\.com[:/]//' | sed 's/\.git$//'

# 取得 SHA refs
glab api projects/<PROJECT_PATH>/merge_requests/<MR_IID> | python3 -c "
import sys, json
d = json.load(sys.stdin)
refs = d['diff_refs']
print(f'base_sha={refs[\"base_sha\"]}')
print(f'head_sha={refs[\"head_sha\"]}')
print(f'start_sha={refs[\"start_sha\"]}')
print(f'gitlab_host={d[\"web_url\"].split(\"/\")[2]}')
"

# 取得 API Token
glab auth status -t 2>&1 | grep -oP '(?<=Token: )\S+'
```

---

### Step 6 — 發佈 Inline DiffNote Comments（**主 shell 負責**，不是 codex）

**重要**：`glab api -f` 不支援巢狀 JSON，**必須使用 curl** 發佈 DiffNote。

> ⚠️ 若 Step 0 派遣了 codex 來分析：codex 只回傳 findings payload，**留言一律由主 shell 用以下 curl 模式貼**。codex 沙箱無法連 GitLab API host，硬要它貼會 silent fail。

每個問題發佈一則 inline comment：

```bash
curl -s --request POST \
  --header "PRIVATE-TOKEN: <TOKEN>" \
  --header "Content-Type: application/json" \
  --data @- \
  "https://<GITLAB_HOST>/api/v4/projects/<PROJECT_PATH_ENCODED>/merge_requests/<MR_IID>/discussions" <<'JSONEOF'
{
  "body": "**[CRITICAL]** 問題標題\n\n**問題**: 具體描述問題\n\n**建議修正**:\n```kotlin\n// 修正後程式碼\n```\n\n---\n*🤖 Reviewed by Codex*",
  "position": {
    "base_sha": "<base_sha>",
    "start_sha": "<start_sha>",
    "head_sha": "<head_sha>",
    "position_type": "text",
    "old_path": "<file_path>",
    "new_path": "<file_path>",
    "new_line": <line_number>
  }
}
JSONEOF
```

**Position 欄位規則**：

| 情境 | 設定方式 |
|---|---|
| 新增的檔案 | 只設 `new_line` |
| 刪除的檔案 | 只設 `old_line` |
| 修改的檔案（新增行） | 設 `new_line` |
| 修改的檔案（刪除行） | 設 `old_line` |
| 重新命名的檔案 | `old_path` 填舊路徑，`new_path` 填新路徑 |

驗證回應中包含 `"type":"DiffNote"`；若為 `"Note"` 表示位置未正確套用，需檢查 SHA 或行號。

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

**五維度加權評分**：

| 維度 | 權重 |
|---|---|
| Architecture Compliance | 25% |
| Code Quality | 25% |
| Security & Null Safety | 20% |
| Maintainability | 15% |
| Compose & Android Best Practices | 15% |

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

#### ❌ 不可 Merge（有 CRITICAL）
```
❌ 不可 Merge，請修正後重新執行 /review-mr

待修正項目：
- [C-1] XxxViewModel.kt:42 — E002 錯誤處理遺漏
- [C-2] XxxDataSource.kt:18 — ApiResponse.data 使用 !!

修正完成後執行：/review-mr <MR_ID>
```

Reporter **不觸發**，不產出報告。

---

### Step 9 — 發佈總結報告

```bash
glab mr note <MR_ID> --message "$(cat <<'EOF'
## 📋 Code Review Summary

### Overview Score: **XX / 100** — [評級]

| 評分項目 | 分數 | 權重 | 加權分 |
|---------|------|------|--------|
| Architecture Compliance | X/100 | 25% | X |
| Code Quality | X/100 | 25% | X |
| Security & Null Safety | X/100 | 20% | X |
| Maintainability | X/100 | 15% | X |
| Compose & Android Best Practices | X/100 | 15% | X |

### 審查範圍
- 審查了 X 個檔案
- 總變更：+Y / -Z 行

### 發現問題

#### 🔴 Critical Issues（X 個）
- `FileA.kt:42` — 問題描述

#### 🟡 Warnings（X 個）
- `FileB.kt:18` — 問題描述

#### 💡 Suggestions（X 個）
- `FileC.kt:55` — 建議描述

#### 🔧 Code Simplification（X 個）
- `FileD.kt:30` — 簡化建議

### 正面評價
- ✅ 列出本次 MR 做得好的地方

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

## 注意事項

- **Step 0 強制**：先做 engine detection，能用 codex 就 dispatch codex；主機 Claude 不要自己角色扮演 Codex。
- **Sandbox 邊界**：codex 負責分析，主 shell 負責 POST 到 GitLab。不要讓 codex 直接 curl GitLab。
- **一律繁體中文**撰寫 comment 描述（技術名詞保留英文）
- **每則 comment 必須簽名** `*🤖 Reviewed by Codex*`
- **先讀完整檔案**再審查，避免誤判需要上下文的程式碼
- **建設性回饋**：每個問題都附上建議的修正方式與範例程式碼
- PROJECT_PATH 用於 API 時需 URL encode（`/` → `%2F`）
- **冪等性**：若 MR 已有 `🤖 Reviewed by Codex` 簽名的 discussion，先檢查再決定是否重貼（避免 duplicate）。User 可用 `--re-review` 強制重跑。

## 常見問題處理

| 狀況 | 處理方式 |
|---|---|
| glab 未認證 | 停止，提示 `glab auth login` |
| DiffNote 回應為 `"Note"` 而非 `"DiffNote"` | 檢查 SHA 是否正確、行號是否在 diff 範圍內 |
| PROJECT_PATH 含特殊字元 | URL encode 後再帶入 curl |
| MR 已關閉或不存在 | 告知使用者確認 MR ID |
| CLAUDE.md 不存在 | 使用技能包內建規範繼續審查 |
| Codex 沙箱 `connect: operation not permitted` 到 GitLab | 正常 — codex 不該直接打 GitLab；改由主 shell 用 curl 貼，codex 只回傳 findings payload |
| Codex 找不到（`codex_available=false`） | Fallback 到 Claude general-purpose agent + 把本 skill 完整內容打包進 prompt；簽名仍用 `🤖 Reviewed by Codex` 但在 chat 標示「fallback engine」 |
| 多 host scenario（GitLab API host 與 web host 不同） | 例如 API `<api-host>` vs Web `<web-host>` 指同一個 GitLab instance — `glab` 用 API host，貼 link 給 user 用 web host |

## 觸發點

| 觸發者 | 場景 |
|---|---|
| User 手動 | `/review-mr <MR>` 直接審查任何 MR |
| workflow-orchestrator | Stage 10.5（push + create MR 之後自動 advisory pass）|
| workflow-orchestrator | Stage 11 fix loop 起始時 fetch + classify comments 也會用到部分本 skill 函式 |
