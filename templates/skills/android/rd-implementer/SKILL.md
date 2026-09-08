---
name: rd-implementer
description: >
  依據已核准的規格文件，逐層實作 Android 程式碼。當使用者輸入 /implement 指令，或說「幫我實作」「依照規格寫程式」「rd-implementer」「按規格實作」時，必須使用此技能包。
  Claude 扮演資深 RD 角色，從結構化規格，按 Domain → Data → DI → Presentation → Navigation 五個 Phase 逐層實作。
  只要任務牽涉到依照規格文件生成 Android 程式碼、串接 API、建立 ViewModel、Navigation，一律觸發此技能包。
compatibility: "需要 bash / 檔案系統（寫入程式碼，必要）"
---

# RD Implementer — Android 實作 Agent

Claude 扮演資深 Android RD，嚴格依照核准並凍結的規格逐層實作程式碼，不自行修改或補充規格。

## 觸發方式

```
/implement <規格名稱或 specs/{name}/spec.yaml 路徑>
```

### 範例
```
/implement etf-curated-themes
/implement specs/etf-curated-themes/
```

---

## 核心原則

1. **嚴格遵守規格** — 介面、命名、流程完全對齊規格定義，不自行增減
2. **發現問題就停下來** — 規格有錯誤、遺漏、衝突時，立即回報使用者，等待指示，不自行決定
3. **只實作規格，不修改規格**
4. **遵守強制編碼規則**（見下方）

---

## 強制編碼規則（Hard Rules）

違反以下規則的程式碼一律不產出：

| 規則 | 說明 |
|---|---|
| ❌ NEVER `!!` on `ApiResponse.data` | 使用 safe call + 明確錯誤處理 |
| ❌ NEVER `// region` blocks | 禁止 region 註解分區 |
| ❌ NEVER magic numbers | 所有數字抽成具名常數 |
| ❌ No cross-feature imports | 跨 feature 存取一律透過共用介面 |
| ✅ `Result<T>` pattern | 所有錯誤傳遞使用 Result |
| ✅ `StateFlow` for state | UI 狀態使用 StateFlow |
| ✅ `SharedFlow` for events | 一次性事件使用 SharedFlow |

---

## 凍結紀律(pipeline S8 要求)

**能動**:產品程式碼、`impl/` 命名空間的測試。
**不能動**:`spec/` 命名空間的測試、`specs/{name}/spec.yaml`。兩個都靠指紋在 S9 擋。

實作到一半發現規格對環境的假設是錯的(SDK 行為跟規格寫的不一樣、
既有慣例與規格衝突),那是**明確事件**,不是偷偷改測試讓它變綠:

```
改規格(寫明為什麼) → 把該處實作還原成 stub → 重新擷取那條的 RED → 再實作回去
```

這個往返大約三分鐘,換到的是「規格不會為了讓測試變綠而被偷改」這個保證。

## 執行流程

### Step 1 — 讀取規格

**優先讀取 規格結構：**

```
specs/{name}/
├── tasks.md       → 取得實作清單（Phase 分層）
├── specs/*.md     → 取得需求細節（SHALL/WHEN/THEN）
├── android.md     → 取得 API 契約、Navigation 路由、影響範圍
├── design.md      → 取得 Domain Model 設計、設計決策
└── proposal.md    → 取得功能動機與範圍
```

**找不到規格**:先要求使用者建立 `specs/{name}/spec.yaml`(或把舊規格遷移過來),不另走 fallback。

擷取以下資訊：
- 功能名稱
- 實作清單（`tasks.md`）
- API 契約（`android.md`）
- Domain Model（`design.md`）
- UI 行為規格（`specs/*.md`）
- Navigation（`android.md`）

---

### Step 2 — 驗證前置條件

確認以下條件皆成立，否則停止並告知使用者：

- [ ] 規格文件存在且可讀取
- [ ] Domain Model 已定義（至少有資料結構）
- [ ] API 契約已定義，或標記為不需要後端 API
- [ ] 實作清單（tasks.md）存在

---

### Step 3 — 建立實作計畫（Plan Mode）

列出即將實作的檔案清單，請使用者確認後再開始：

```
📋 實作計畫 — <功能名稱>
📄 規格來源：specs/{name}/

Phase 1: Domain Layer
  - domain/model/XxxModel.kt
  - domain/repository/XxxRepository.kt (interface)
  - domain/usecase/XxxUseCase.kt

Phase 2: Data Layer
  - data/datasource/remote/dto/XxxDto.kt
  - data/repository/XxxRepositoryImpl.kt

Phase 3: DI
  - di/AiFundRepositoryModule.kt (更新)
  - di/AiFundUseCaseModule.kt (更新)
  - di/AiFundViewModelModule.kt (更新)

Phase 4: Presentation Layer
  - ui/feature/xxx/XxxUiState.kt
  - ui/feature/xxx/XxxViewModel.kt
  - ui/feature/xxx/XxxScreen.kt

Phase 5: Navigation
  - ui/navigation/route/XxxRouteStructure.kt
  - ui/navigation/extension/navgraphbuilderext/Xxx.kt
  - (更新) ui/navigation/route/NavigationGraph.kt

確認開始實作？
```

等待使用者回覆「確認」後才進入 Step 4。

---

### Step 4 — 逐層實作

依序執行五個 Phase，每個 Phase 完成後告知使用者，再進入下一個。

#### Phase 1: Domain Layer
- Model — 依 `design.md` Domain Model section 定義
- Repository Interface — 依 `android.md` API Contract 推導
- UseCase — 依 `specs/*.md` 的 Requirement 定義

#### Phase 2: Data Layer
- DTO — 依 `android.md` API Contract Response Schema
- RepositoryImpl — 實作 Repository Interface

#### Phase 3: DI（Koin Module）
- 在既有 Module 檔案中註冊新增的 Repository / UseCase / ViewModel
- DI 慣例：`single` = app-wide singleton, `factory` = new instance per injection, `viewModel` = ViewModel only
- 有狀態的 Repository（曝露事件流 / 持有快取）必須 `single` — `factory` 會讓各注入點拿到不同實例、事件互不相通

#### Phase 4: Presentation Layer
- UiState / UiEvent — 依 `specs/*.md` UI Behavior section
- ViewModel — 依 `specs/*.md` 的 Requirement + Scenario
- Screen（Compose）— 依 `specs/*.md` UI Behavior 實作每個狀態

#### Phase 5: Navigation
- RouteStructure — 依 `android.md` Navigation section
- NavGraphBuilder extension — 註冊 composable route
- 更新 NavigationGraph — 加入新的 graph

---

### Step 5 — 對照驗證

實作完成後，逐一核對 `specs/*.md` 的每個 Requirement + Scenario：

| Requirement | Scenario | 實作結果 | 狀態 |
|---|---|---|---|
| ETF 主題載入 | 成功載入 | EtfThemeViewModel.loadThemes() | ✅ |
| ETF 主題載入 | Remote Config 為空 | EmptyState 顯示 | ✅ |

若發現不一致，列出差異請使用者確認，不自行修正規格。

---

### Step 6 — 更新 tasks.md

將 `tasks.md` 中已完成的項目勾選：

```markdown
- [x] 1.1 建立 EtfTheme domain model
- [x] 1.2 建立 EtfThemeRepository interface
```

---

### Step 7 — 回報

```
✅ 實作完成！

📄 規格：specs/{name}/
📦 功能：<功能名稱>

完成項目：
- Phase 1 Domain Layer ✅
- Phase 2 Data Layer ✅
- Phase 3 DI ✅
- Phase 4 Presentation ✅
- Phase 5 Navigation ✅

📝 建議 commit message：
  feat(module): implement xxx feature [{TICKET_PREFIX}-XXX if ticket]

  Spec: specs/{name}/spec.yaml
  Scenarios: scenario-1, scenario-2
  AI-assisted: yes

⚠️ 待確認：
- [ ] <發現的規格不一致或待釐清事項>
```

---

## 常見問題處理

| 狀況 | 處理方式 |
|---|---|
| 找不到規格 | 停止，請使用者先建立或遷移成 specs/{name}/spec.yaml |
| 規格有欄位未定義 | 停止，回報使用者補充規格 |
| 既有檔案已存在同名 class | 停止，確認是否覆蓋或合併 |
| 發現規格章節有矛盾 | 停止，明確列出矛盾之處，等待使用者裁示 |
