---
name: code-reviewer
description: >
  對照規格文件（OpenSpec 或 SDD），驗證目前實作是否符合規格。當使用者輸入 /verify 指令，或說「幫我驗證實作」「code review」「對照規格審查程式碼」「確認實作符合規格」時，必須使用此技能包。
  Claude 扮演資深 Code Reviewer，從 OpenSpec specs/*.md 或 SDD 讀取驗收基準，從 git diff 取得程式碼變更，逐項比對，產出 CRITICAL / WARNING / SUGGESTION 分級報告。
  只要任務牽涉到驗證程式碼符合規格、審查 Android 實作品質、比對規格與程式碼差異，一律觸發此技能包。
compatibility: "需要 bash / git（讀取 diff 與原始碼，必要）、Notion MCP（選用，fallback 用）"
---

# Code Reviewer — 規格合規審查 Agent

Claude 扮演資深 Code Reviewer，以規格文件為黃金標準審查實作，產出分級問題清單。

## 觸發方式

```
/verify <OpenSpec change 名稱或路徑>
/verify <Notion SDD 連結或 SDD 編號>    ← fallback（舊格式）
```

### 範例
```
/verify etf-curated-themes
/verify openspec/changes/etf-curated-themes/
/verify SDD-3                              ← fallback 舊 SDD
```

---

## 審查維度與權重

| 維度 | 權重 | 審查重點 |
|---|---|---|
| Architecture Compliance | 25% | Clean Architecture 分層、無 cross-feature import、依賴方向正確 |
| Code Quality | 25% | 命名清晰、無 magic numbers、無 `// region`、Result<T> 使用正確 |
| Security & Null Safety | 20% | 無 `!!`、錯誤處理完整、API response 安全存取 |
| Maintainability | 15% | DRY、可測試性、職責單一 |
| Compose & Android Best Practices | 15% | Modifier 傳遞、recomposition 最小化、StateFlow/SharedFlow 正確使用 |

---

## 執行流程

### Step 1 — 讀取規格（OpenSpec 優先）

**優先讀取 OpenSpec 結構：**

| 檔案 | 審查用途 |
|---|---|
| `specs/*.md` — Requirement + Scenario | 驗證所有 SHALL 需求是否都有實作 |
| `specs/*.md` — Error Scenario | 驗證所有錯誤路徑是否都有實作 |
| `specs/*.md` — UI Behavior | 驗證 UiState / UiEvent 定義 |
| `android.md` — API Contract | 驗證 Service / DataSource 介面 |
| `android.md` — Navigation | 驗證 Route / NavGraph 設定 |
| `android.md` — Impact Analysis | 驗證 DI 與影響模組變更 |
| `design.md` — Domain Model | 驗證 Domain Model 結構一致 |
| `tasks.md` | 驗證所有預期檔案是否存在 |

**Fallback（僅舊功能）：** 若 OpenSpec 不存在，改用 Notion MCP 讀取 SDD。

---

### Step 2 — 讀取程式碼變更

```bash
# 取得 staged + unstaged 變更
git diff HEAD

# 若無 git，列出功能相關目錄
find app/src/main -name "Xxx*.kt" | sort
```

同時讀取完整檔案內容（不只看 diff），確保能追蹤跨行的問題。

---

### Step 3 — 規格合規比對

#### 使用 OpenSpec 時：以 Requirement × Scenario 為單位

逐一核對 `specs/*.md` 的每個 Requirement 及其 Scenario：

```
Requirement: ETF精選主題頁面載入主題分類
  ├── Scenario: 成功載入主題分類         → ✅ 已實作
  ├── Scenario: Remote Config 為空       → ✅ 已實作
  └── Scenario: 網路異常                 → ⚠️ 缺少離線處理

Requirement: ETF 按鈕點擊帶入商品代碼
  ├── Scenario: 已登入，點擊 ETF         → ✅ 已實作
  └── Scenario: 未登入，點擊 ETF         → ❌ AuthRequiredWrapper 未包裹
```

#### 使用舊 SDD 時：以 AC 為單位

逐一核對 Chapter 9 的每條 AC（Given/When/Then）。

---

#### 3a. 介面一致性
- UiState 欄位名稱、型別是否與規格完全一致
- UiEvent sealed class 的所有子類別是否都有實作

#### 3b. 流程邏輯一致性
- ViewModel 的業務流程步驟是否與規格描述順序一致
- Loading / Success / Error 狀態轉換是否正確

#### 3c. 錯誤處理完整性
- 規格定義的每個錯誤情境是否都有對應的 catch / onFailure 處理
- 錯誤處理方式（Dialog / Toast / 導航）是否與規格一致

#### 3d. Navigation 一致性
- Route 參數是否與 `android.md` Navigation section 一致
- 進入點、離開點（成功 / 取消 / 錯誤）是否完整

#### 3e. 檔案完整性
- 逐一核對 `tasks.md`（或 SDD Chapter 10）的實作清單

#### 3f. DI 註冊完整性
- Koin module 中是否包含所有新增的 Repository / UseCase / ViewModel

---

### Step 4 — 程式碼品質審查

對每個變更檔案執行靜態審查，依嚴重程度分級：

#### CRITICAL（必須修正）
- `!!` 使用在 `ApiResponse.data` 或任何可能為 null 的值
- Cross-feature import（直接 import 其他 feature 的 internal class）
- ViewModel 直接持有 View 參考
- Coroutine 在非 viewModelScope 啟動（記憶體洩漏風險）
- 未捕獲的 Exception 可能導致 Crash

#### WARNING（應修正）
- Magic numbers（未抽成具名常數的數字或字串）
- `// region` block 使用
- StateFlow 應用 SharedFlow 替代（或反之）
- 函式超過 40 行（單一職責原則）
- 缺少對應規格 Scenario 的測試

#### SUGGESTION（建議改進）
- 可提取的共用 Composable
- 重複的邏輯可抽成 extension function
- 命名可更具描述性
- Modifier 未由外部傳入（Compose 最佳實踐）

---

### Step 5 — 產出審查報告

```
════════════════════════════════════════
📋 Code Review Report — <功能名稱>
════════════════════════════════════════

📄 規格來源：openspec/changes/{name}/
   （或 SDD: openspec/sdd/SDD-X-xxx.md）

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
│ Code Quality (25%)             │ 18/25│
│ Security & Null Safety (20%)   │ 20/20│
│ Maintainability (15%)          │ 12/15│
│ Compose & Android BP (15%)     │ 13/15│
│ 總分                           │ 85/100│
└────────────────────────────────┴──────┘

════════════════════════════════════════
🔴 CRITICAL（N 個）— 必須修正才可合併
════════════════════════════════════════

[C-1] <問題標題>
  📁 XxxViewModel.kt：第 42 行
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

滿足條件後，**立即執行 reporter 技能包**產出本地報告。

#### ❌ 不可 Commit（有 CRITICAL）
```
❌ 不可 Commit，請修正後重新執行 /verify

待修正項目：
- [C-1] XxxViewModel.kt:42 — 錯誤處理遺漏
- [C-2] XxxDataSource.kt:18 — ApiResponse.data 使用 !!

修正完成後執行：/verify {change-name}
```

Reporter **不觸發**，不產出報告。

---

## 常見問題處理

| 狀況 | 處理方式 |
|---|---|
| `git diff` 無輸出（無變更） | 改用 find 列出相關檔案，對整個功能做全面審查 |
| OpenSpec 與舊 SDD 都存在 | 優先使用 OpenSpec |
| 找不到對應實作檔案 | 列為 WARNING：tasks.md 項目未完成 |
| 規格本身有錯誤或模糊 | 標注為 `[規格待釐清]`，不自行判斷正確行為 |
| 程式碼與規格不一致但無法判斷誰對 | 列為 WARNING，請使用者裁示 |
