---
name: code-reviewer
description: >
  對照 OpenSpec change 規格驗證目前實作是否符合規格。當使用者輸入 /verify 指令，或說「幫我驗證實作」「code review」「對照規格審查程式碼」「確認實作符合規格」時，必須使用此技能包。
  Claude 扮演資深 Code Reviewer，從 `openspec/changes/<name>/specs/*.md` 讀取驗收基準，從 git diff 取得程式碼變更，逐項比對，產出 CRITICAL / WARNING / SUGGESTION 分級報告。
  只要任務牽涉到驗證程式碼符合規格、審查 iOS 實作品質、比對規格與程式碼差異，一律觸發此技能包。
compatibility: "需要 bash / git（讀取 diff 與原始碼，必要）"
---

# Code Reviewer — 規格合規審查 Agent（iOS）

Claude 扮演資深 Code Reviewer，以 OpenSpec 規格為黃金標準審查實作，產出分級問題清單。

## 觸發方式

```
/verify <OpenSpec change 名稱或路徑>
```

### 範例
```
/verify auth-login
/verify openspec/changes/auth-login/
```

---

## 審查維度與權重

| 維度 | 權重 | 審查重點 |
|---|---|---|
| Architecture Compliance | 25% | SPM 依賴方向（Domain 零依賴）、UseCase/Repository 分工、composition root 注入（任何 `static let shared` / singleton = CRITICAL）、View 不得直呼 Repository/APIClient |
| Code Quality | 20% | 命名清晰、無重複、複雜度受控、SwiftFormat/SwiftLint 乾淨 |
| Swift Safety | 15% | 非測試碼 `!` 強制 unwrap 與 `try!` = CRITICAL、Sendable/併發正確性（@MainActor VM、actor 使用）、錯誤處理不吞錯（禁把斷網顯示成別的文案） |
| SwiftUI Best Practices | 15% | body 純度（無副作用）、@State vs @Binding 正確、view identity、避免不必要 re-render、NavigationStack/AppRoute 慣例 |
| MindEY 鐵則遵循 | 15% | CLAUDE.md 鐵則逐條 + demo/mock 判別 + architecture.md §8 禁止事項全表（檢查清單見 Step 4） |
| Maintainability | 10% | 測試覆蓋（Domain/Data/VM 90% line）、DRY、職責單一、文件同步 |

---

## 執行流程

### Step 1 — 讀取規格（OpenSpec 優先）

**優先讀取 OpenSpec 結構：**

| 檔案 | 審查用途 |
|---|---|
| `specs/*.md` — Requirement + Scenario | 驗證所有 SHALL 需求是否都有實作 |
| `specs/*.md` — Error Scenario | 驗證所有錯誤路徑是否都有實作 |
| `specs/*.md` — UI Behavior | 驗證 ViewModel 狀態欄位 / intent 方法定義 |
| `ios.md` — API Contract | 驗證 Repository protocol / APIClient Endpoint 介面 |
| `ios.md` — Navigation | 驗證 AppRoute / NavigationStack 設定 |
| `ios.md` — Impact Analysis | 驗證 AppContainer 組裝與受影響 package 變更 |
| `design.md` — Domain Model | 驗證 Domain Entity 結構一致 |
| `tasks.md` | 驗證所有預期檔案是否存在 |

**找不到 OpenSpec change**：先要求使用者建立或將舊規格遷移成 canonical OpenSpec spec，不另走 fallback。

---

### Step 2 — 讀取程式碼變更

```bash
# 取得 staged + unstaged 變更
git diff HEAD

# 若無 git，列出功能相關目錄
find Packages App -name "Xxx*.swift" | sort
```

同時讀取完整檔案內容（不只看 diff），確保能追蹤跨行的問題。

---

### Step 3 — 規格合規比對

#### 使用 OpenSpec 時：以 Requirement × Scenario 為單位

逐一核對 `specs/*.md` 的每個 Requirement 及其 Scenario：

```
Requirement: 登入頁以 email + 密碼登入
  ├── Scenario: 成功登入                 → ✅ 已實作
  ├── Scenario: 帳密錯誤                 → ✅ 已實作
  └── Scenario: 網路異常                 → ⚠️ 未走 DomainError.network 文案

Requirement: 活動 6 碼簽到
  ├── Scenario: 今天的活動輸碼成功       → ✅ 已實作
  └── Scenario: 非今天的活動             → ❌ 只信 status 欄位，未用 Asia/Taipei 判斷
```

---

#### 3a. 介面一致性
- ViewModel 暴露的狀態欄位名稱、型別是否與規格完全一致
- 規格定義的所有 intent 方法是否都有實作

#### 3b. 流程邏輯一致性
- ViewModel 的業務流程步驟是否與規格描述順序一致
- Loading / Success / Error 狀態轉換是否正確

#### 3c. 錯誤處理完整性
- 規格定義的每個錯誤情境是否都有對應的 do / catch 與 `DomainError` 分支處理
- 錯誤處理方式（Alert / Toast / 導航）是否與規格一致
- API `{error}` 繁中文案是否直顯，未被吞錯改寫

#### 3d. Navigation 一致性
- `AppRoute` case 與參數是否與 `ios.md` Navigation section 一致
- 進入點、離開點（成功 / 取消 / 錯誤）是否完整

#### 3e. 檔案完整性
- 逐一核對 `tasks.md` 的實作清單

#### 3f. DI 註冊完整性
- `AppContainer` 是否組裝所有新增的 Repository / UseCase，並提供對應 `makeXXXViewModel()` 工廠
- 是否有人繞過 composition root 自行建構依賴或使用 singleton

---

### Step 4 — 程式碼品質審查

對每個變更檔案執行靜態審查，依嚴重程度分級：

#### CRITICAL（必須修正）
- 非測試碼使用 `!` 強制 unwrap 或 `try!`
- `static let shared` / 任何 singleton（繞過 composition root，全案零測試縫）
- View 直接呼叫 Repository / APIClient（必須經 ViewModel → UseCase）
- Domain package import Supabase / SwiftUI / UIKit（分層失效；SPM 已在編譯期擋，不可繞）
- Entity 帶 view concern（頭像 fallback、顯示字串格式化不放 Domain）
- 用 `Date` 直接承載 server `created_at`（必須用 `ServerTimestamp` 保留原字串；微秒截斷會讓未讀水位永遠算錯）
- 吞錯誤改寫文案（例：把斷網顯示成「帳密錯誤」）
- 照 web demo/mock 元件移植（動工前未確認該元件有真的打 API）
- ViewModel 持有 View 參考或 import SwiftUI
- 違反下方「MindEY 鐵則檢查清單」任一條

#### WARNING（應修正）
- Magic numbers（未抽成具名常數的數字或字串）
- ViewModel 未標 `@MainActor`，或跨 actor 傳遞非 `Sendable` 型別
- SwiftFormat / SwiftLint 違規未清
- `body` 內有副作用（應移至 `.task` / `.onAppear` 或 VM intent 方法）
- `@State` 應用 `@Binding` 替代（或反之）、view identity 誤用
- 函式超過 40 行（單一職責原則）
- 缺少對應規格 Scenario 的測試（Domain/Data/VM 覆蓋門檻 90% line）

#### SUGGESTION（建議改進）
- 可提取的共用 View / MindEYDesignSystem 元件
- 重複的邏輯可抽成 extension
- 命名可更具描述性
- 不必要 re-render 可透過拆分子 View / `Equatable` 降低

#### MindEY 鐵則檢查清單（違反任一條 = CRITICAL）

| 鐵則 | 檢查點 |
|---|---|
| 註冊走 API 不走 SDK | 必走 `POST /api/auth/register` → 再 signInWithPassword，**不可**用 SDK signUp |
| latest_seen 原字串 | 未讀水位必須回傳 `ServerTimestamp.raw` 伺服器原字串，一字不改（微秒精度） |
| Realtime 限 postgres_changes | **禁用 broadcast**；訊息 `created_at` 無時區後綴一律補 Z 當 UTC |
| 上傳路徑第一層 = userId | client 直傳 Storage，路徑第一層 = 自己 userId；content-type 以檔案自身 type 為準 |
| JPEG 不是 WebP | 壓縮規格照 web（尺寸/品質）但輸出 JPEG；相簿 HEIC 主動轉檔 |
| 活動時區 Asia/Taipei | 活動「今天」用 Asia/Taipei 判斷，不可只信 status 欄位；簽到是 6 碼輸碼制不是 QR |
| `{error}` 直顯 | 錯誤格式統一 `{error}`，繁中文案直接顯示，禁改寫 |
| demo/mock 判別 | 對照 `pc/mindey-share` 元件時，**必先確認該元件有真的打 API**；web 的 demo/mock fallback 一律不移植 |
| 測試資料衛生 | 測試碼/fixture 的 API 呼叫遵守專案 CLAUDE.md 衛生規則（測試帳號範圍/禁用端點/資料前綴）；fixture 含真實使用者個資 = CRITICAL |
| 其餘鐵則 | CLAUDE.md 鐵則段逐條比照（profiles 走 RLS 直寫、附件簽名 URL 24h 重簽等）+ architecture.md §8 禁止事項全表 |

---

### Step 5 — 產出審查報告

```
════════════════════════════════════════
📋 Code Review Report — <功能名稱>
════════════════════════════════════════

📄 規格來源：openspec/changes/{name}/

📊 規格合規摘要
┌────────────────────────┬────────┐
│ Requirement 覆蓋率      │ X/Y    │
│ Scenario 覆蓋率         │ X/Y    │
│ 介面一致性             │ ✅ 通過 │
│ 流程邏輯一致性         │ ⚠️ 差異 │
│ 錯誤處理完整性         │ ❌ 缺漏 │
│ Navigation 一致性      │ ✅ 通過 │
│ 檔案完整性             │ ✅ 通過 │
│ DI 註冊完整性          │ ✅ 通過 │
└────────────────────────┴────────┘

📊 品質評分
┌────────────────────────────────┬──────┐
│ Architecture Compliance (25%)  │ 22/25│
│ Code Quality (20%)             │ 16/20│
│ Swift Safety (15%)             │ 15/15│
│ SwiftUI Best Practices (15%)   │ 13/15│
│ MindEY 鐵則遵循 (15%)          │ 15/15│
│ Maintainability (10%)          │  8/10│
│ 總分                           │ 89/100│
└────────────────────────────────┴──────┘

════════════════════════════════════════
🔴 CRITICAL（N 個）— 必須修正才可合併
════════════════════════════════════════

[C-1] <問題標題>
  📁 XxxViewModel.swift：第 42 行
  📋 對應規格：specs/{name}/spec.md — Requirement: {name} — Scenario: {name}
  ❌ 問題：...
  ✅ 建議：...

════════════════════════════════════════
🟡 WARNING（N 個）
════════════════════════════════════════

[W-1] ...

════════════════════════════════════════
🔵 SUGGESTION（N 個）
════════════════════════════════════════

[S-1] ...
```

#### 寫回 `review.md`（append-only）

報告產出後，將彙總摘要 append 到 `openspec/changes/{name}/review.md`；**不改寫舊 section**，每次執行新增一個 section：

```markdown
# Review log: {Feature Name}

## Verify (YYYY-MM-DD)

- Reviewers: code-reviewer
- Iterations: N

### CRITICAL
_(none)_

### WARNING
1. {short} — {檔案}:{行} — disposition: pending

### SUGGESTION
1. {short} — disposition: pending

### Verdict
PASS / BLOCK
```

**Disposition 規則：**
- 每條 finding 以 `— disposition: fixed | rejected | deferred | pending` 結尾。
- 新 WARNING / SUGGESTION 一律從 `pending` 起；CRITICAL 走「修正 → 重新 /verify」迴圈，清零後記 `fixed`。
- 後續階段（或使用者）處理或駁回某條 finding 時，**就地更新**該標記——這是這份 append-only log 唯一允許的 in-place 修改。
- `deferred` 必須帶追蹤參照（例 `deferred ({GITHUB_REPO} issue #123)`）；沒票的 deferral 從來不會被關。

---

### Step 6 — 核准結論

#### ✅ 可以 Commit（零 CRITICAL）
```
✅ 可以 Commit

CRITICAL：0 個
WARNING：X 個（建議修正但不阻擋）
品質評分：XX / 100

→ 自動產出審查報告...
```

滿足條件後，**立即執行 reporter 技能包**產出本地報告；`review.md` 該次 section 的 Verdict 記 `PASS`。

#### ❌ 不可 Commit（有 CRITICAL）
```
❌ 不可 Commit，請修正後重新執行 /verify

待修正項目：
- [C-1] XxxViewModel.swift:42 — 錯誤處理遺漏
- [C-2] XxxRepositoryImpl.swift:18 — 非測試碼使用 try!

修正完成後執行：/verify {change-name}
```

Reporter **不觸發**，不產出報告；`review.md` 該次 section 的 Verdict 記 `BLOCK`。

---

## 常見問題處理

| 狀況 | 處理方式 |
|---|---|
| `git diff` 無輸出（無變更） | 改用 find 列出相關檔案，對整個功能做全面審查 |
| 找不到 OpenSpec change | 停止，請使用者先建立或將舊規格遷移成 canonical OpenSpec spec |
| 找不到對應實作檔案 | 列為 WARNING：tasks.md 項目未完成 |
| 規格本身有錯誤或模糊 | 標注為 `[規格待釐清]`，不自行判斷正確行為 |
| 程式碼與規格不一致但無法判斷誰對 | 列為 WARNING，請使用者裁示 |
