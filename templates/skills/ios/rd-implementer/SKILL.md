---
name: rd-implementer
description: >
  依據已核准的規格文件，逐層實作 iOS 程式碼。當使用者輸入 /implement 指令，或說「幫我實作」「依照規格寫程式」「rd-implementer」「按規格實作」時，必須使用此技能包。
  Claude 扮演資深 RD 角色，從 OpenSpec change 讀取規格，按 Domain → Data → Composition → Presentation → View/Navigation 五個 Phase 逐層實作（前置 Phase 0 為 web 對照檢查）。
  只要任務牽涉到依照規格文件生成 iOS/SwiftUI 程式碼、串接 API、建立 ViewModel、Navigation，一律觸發此技能包。
compatibility: "需要 bash / 檔案系統（寫入程式碼，必要）"
---
> **套用注意**：本 template 以首個專案（MindEY）的具體規則與範例為示範；套用到新專案時，請將 MindEY 專屬細節（鐵則清單、web 對照路徑、端點與範例）替換為該專案 CLAUDE.md／架構文件的對應內容。

# RD Implementer — iOS 實作 Agent

Claude 扮演資深 iOS RD，嚴格依照核准的 OpenSpec 規格逐層實作程式碼，不自行修改或補充規格。
架構依據 `docs/architecture.md`（Clean Architecture + local SPM 分層）；與專案 CLAUDE.md 鐵則衝突時，鐵則優先。

## Template 變數

| 變數 | 說明 | MindEY 填值 |
|---|---|---|
| `{PROJECT_ROOT}` | repo 根目錄 | `mindey-mobile/` |
| `{TEST_COMMAND}` | 一鍵驗證指令（xcodegen → build → 全部測試） | `scripts/verify.sh` |
| `{COVERAGE_COMMAND}` | 覆蓋率門檻指令（xccov 分層 Domain/Data/VM，GREEN 後執行，腳本由目標專案提供） | `./scripts/coverage.sh --gate 90` |
| `{GITHUB_REPO}` | GitHub repo（PR 目的地） | fork 時填入 |

## 觸發方式

```
/implement <OpenSpec change 名稱或路徑>
```

### 範例
```
/implement auth-sign-in
/implement openspec/changes/auth-sign-in/
```

---

## 核心原則

1. **嚴格遵守規格** — 介面、命名、流程完全對齊規格定義，不自行增減
2. **發現問題就停下來** — 規格有錯誤、遺漏、衝突時，立即回報使用者，等待指示，不自行決定
3. **只實作規格，不修改規格**
4. **遵守強制編碼規則**（見下方）
5. **TDD 銜接** — workflow pipeline 中本 skill 位於測試之後（test-writer／RED 階段已產出測試且全 RED）：實作前確認測試存在且 RED，實作目標 = 讓測試轉 GREEN；**不准修改測試遷就實作**，測試本身有錯一律回報
6. **web 對照先行** — 移植任何 web 元件前，先確認它有真的打 API（Phase 0）；demo/mock fallback 一律不移植

---

## 強制編碼規則（Hard Rules）

違反以下規則的程式碼一律不產出（各條均為架構鐵律，來源：`docs/architecture.md` §8 + CLAUDE.md 鐵則）：

| 規則 | 說明 |
|---|---|
| ❌ NEVER `!` / `try!`（非測試碼） | optional 用 `guard let` / `if let` + 明確錯誤處理；review 必退 |
| ❌ NEVER singleton / `static let shared` | 一律經 AppContainer 建構子注入；singleton 讓全案零測試縫 |
| ❌ NEVER Domain import Supabase / UIKit / SwiftUI | SPM 依賴方向 `App → Domain ← Data` **編譯期強制**，Domain 只有 Foundation；違反直接編譯錯誤，別繞 |
| ❌ NEVER 用 `Date` 直接承載 server `created_at` | 一律 decode 成 `ServerTimestamp`（`raw` 原字串 + `date` 解析值）；微秒被截斷 → 未讀水位永遠算錯 |
| ❌ NEVER Combine | async/await only；串流（Realtime 等）用 `AsyncSequence` |
| ❌ NEVER magic numbers | 所有數字抽成具名常數 |
| ❌ View 直呼 Repository / APIClient | View 只吃 ViewModel 的值與 closure |
| ✅ `DomainError` 統一錯誤 | `server(status:message:)` / `network` / `notConfigured` / `decoding`；API `{error}` 繁中文案 UI 直顯，**禁止吞錯改寫**（不准把斷網顯示成「帳密錯誤」） |
| ✅ UseCase = 具體 struct | 不做 protocol；mock 縫只開在 Repository；CRUD 一行轉呼叫也照建 UseCase |
| ✅ `@Observable @MainActor` ViewModel | 建構子收 UseCase，暴露狀態值 + intent 方法 |

---

## 執行流程

### Step 1 — 讀取規格（OpenSpec 優先）

**優先讀取 OpenSpec 結構：**

```
openspec/changes/{name}/
├── tasks.md       → 取得實作清單（Phase 分層）
├── specs/*.md     → 取得需求細節（SHALL/WHEN/THEN）
├── ios.md         → 取得 API 契約、Navigation/深連結路由、影響範圍
├── design.md      → 取得 Domain Model 設計、設計決策
└── proposal.md    → 取得功能動機與範圍
```

**找不到 OpenSpec change**：先要求使用者建立或將舊規格遷移成 canonical OpenSpec spec，不另走 fallback。

擷取以下資訊：
- 功能名稱
- 實作清單（`tasks.md`）
- API 契約（`ios.md`）
- Domain Model（`design.md`）
- UI 行為規格（`specs/*.md`）
- Navigation / 深連結（`ios.md`）
- web 對照元件（`ios.md` 或 `proposal.md` 指認的 `{PROJECT_ROOT}/pc/mindey-share/` 路徑）

---

### Step 2 — 驗證前置條件

確認以下條件皆成立，否則停止並告知使用者：

- [ ] 規格文件存在且可讀取
- [ ] Domain Model 已定義（至少有資料結構）
- [ ] API 契約已定義，或標記為不需要後端 API
- [ ] 實作清單（tasks.md）存在
- [ ] TDD 銜接：test-writer 產出的測試已存在且處於 RED（單獨呼叫 /implement 而無測試時，回報使用者確認是否先跑 test-writer）
- [ ] web 對照元件已指認（實際驗證在 Phase 0）

---

### Step 3 — 建立實作計畫（Plan Mode）

列出即將實作的檔案清單，請使用者確認後再開始：

```
📋 實作計畫 — <功能名稱>
📄 規格來源：openspec/changes/{name}/

Phase 0: Web 對照檢查
  - {PROJECT_ROOT}/pc/mindey-share/src/... <對應元件>（確認真的打 API，列出對應 route.ts）

Phase 1: Domain Layer（Packages/MindEYDomain，純 Swift 零依賴）
  - Packages/MindEYDomain/Sources/MindEYDomain/Entities/Xxx.swift
  - Packages/MindEYDomain/Sources/MindEYDomain/Repositories/XxxRepository.swift (protocol)
  - Packages/MindEYDomain/Sources/MindEYDomain/UseCases/<capability>/XxxUseCase.swift
  - (需要時) Packages/MindEYDomain/Sources/MindEYDomain/Support/...

Phase 2: Data Layer（Packages/MindEYData）
  - Packages/MindEYData/Sources/MindEYData/DTO/XxxDTO.swift
  - Packages/MindEYData/Sources/MindEYData/Mappers/XxxDTO+Mapping.swift
  - Packages/MindEYData/Sources/MindEYData/Repositories/XxxRepositoryImpl.swift
  - (需要時) Network/（APIClient、Endpoint）、Supabase/ adapter 更新

Phase 3: Composition
  - App/Composition/AppContainer.swift（更新：注入 + makeXxxViewModel() 工廠）

Phase 4: Presentation Layer
  - App/Features/Xxx/XxxViewModel.swift（@Observable @MainActor）

Phase 5: View / Navigation
  - App/Features/Xxx/XxxView.swift
  - App/Navigation/AppRoute.swift（更新：新增 case）
  - (需要時) App/Navigation/AppRouter.swift、DeepLinkParser.swift 更新

確認開始實作？
```

等待使用者回覆「確認」後才進入 Step 4。

---

### Step 4 — 逐層實作

依序執行 Phase 0–5。**Phase 1–5 每層完成後跑 `{TEST_COMMAND}` 驗證**（build + 全部測試；本階段允許尚未實作層的測試仍 RED，但不得出現編譯錯誤與已實作層的 FAIL），告知使用者後再進入下一個 Phase。

#### Phase 0: Web 對照檢查（前置，不寫碼）
- 逐一打開規格指認的 `{PROJECT_ROOT}/pc/mindey-share/` 對應元件
- 確認**有真的打 API**：元件呼叫的 endpoint 在 `src/app/api/**/route.ts` 有真實實作（非 stub）；supabase 直寫要能對上 RLS 表
- demo/mock fallback（hardcoded 資料、假載入、mock 陣列）**一律不移植**；發現規格對照的元件是 mock → 停止並回報（實例：註冊精靈真實版在 `user-menu.tsx`，`register-dialog.tsx` 是純 mock）
- 產出：endpoint + request/response 形狀清單，供 Phase 1 Domain Model 核對與 Phase 2 DTO 對照

#### Phase 1: Domain Layer（純 Swift，零依賴）
- Entities — 依 `design.md` Domain Model section 定義；struct + `Hashable`，**不含 view concern**（頭像 fallback、顯示字串格式化不放這）
- Repository protocol — 依 `ios.md` API Contract 推導，依 capability 切（如 `AuthRepository`、`ChatRepository`）
- UseCase — 依 `specs/*.md` 的 Requirement 定義；**具體 struct + `callAsFunction`，不做 protocol**
- Support — `ServerTimestamp`、`DomainError`、cursor 分頁等跨畫面不變量寫成純函式，每條配回歸測試
- 鐵律：不 import Supabase / UIKit / SwiftUI（SPM 已在編譯期擋）
- 完成後：`{TEST_COMMAND}`

#### Phase 2: Data Layer
- DTO — 依 `ios.md` API Contract Response Schema；命名 `XxxDTO`，Codable 鏡射 API JSON；decoder 全案統一（snake_case 轉換 + 日期解析集中一處）
- server `created_at` 一律 decode 成 `ServerTimestamp`（raw 原字串一字不改 + date 解析值；無時區後綴補 Z 當 UTC，含微秒）
- Mapper — `extension XxxDTO { func toEntity() throws -> Xxx }`，失敗丟 `DomainError.decoding`
- RepositoryImpl — 實作 Domain protocol；無狀態 struct；錯誤統一轉 `DomainError`
- Network / Supabase adapter — APIClient、Endpoint 增補；Realtime 以 `AsyncSequence` 暴露，訂閱生命週期歸 Data 層 service（`RealtimeHub` 是 actor）
- 完成後：`{TEST_COMMAND}`

#### Phase 3: Composition（AppContainer 注入）
- 在 `App/Composition/AppContainer.swift` 註冊：RepositoryImpl 由 container 建立並持有 → 新增 `makeXxxViewModel()` 工廠方法
- 組裝慣例：手工組裝、不引 DI 套件；建構子注入貫穿；`@Environment` 只放 `SessionStore`；**任何 `static let shared` / singleton 都是違規**
- 完成後：`{TEST_COMMAND}`

#### Phase 4: Presentation Layer（ViewModel）
- ViewModel — 依 `specs/*.md` 的 Requirement + Scenario；`@Observable @MainActor`，建構子收 UseCase，暴露狀態值 + intent 方法
- async/await only（不引 Combine）；不碰 Repository 或任何 MindEYData 型別，僅依賴 MindEYDomain 的 UseCase／Entity／DomainError
- 統一把 `DomainError` 轉顯示文案（`server` 的繁中 message 直顯）；**禁止吞錯改寫**
- 完成後：`{TEST_COMMAND}`

#### Phase 5: View / Navigation
- Screen（SwiftUI）— `<X>View.swift` 與 ViewModel 同資料夾；**View 只吃 VM 的值與 closure，不碰 Repository/APIClient**；依 `specs/*.md` UI Behavior 實作每個狀態；UI 對齊 Phase 0 確認過的 web RWD 手機版元件
- AppRoute — 依 `ios.md` Navigation section 在集中式 route enum 新增 case（如 `case event(UUID)`）
- AppRouter / DeepLinkParser — 註冊路由；Universal Links 與通知共用同一個 parser
- Preview 用 `PreviewSupport/` 的假 Repo 組真 UseCase，不用真網路
- 完成後：`{TEST_COMMAND}` 全綠，**且必跑煙霧測試**（煙霧測試 gate：截圖須為**受影響畫面**且自行判讀正確才算完成；導航不到的畫面列入 6c checklist 交 owner 人工驗收 gate — 即 reporter 的驗收清單，**不得以啟動截圖充數**；iOS 慣例 `./scripts/smoke.sh [--url <deeplink>]`，腳本由目標專案提供；驗證邊界以專案架構文件為準）

---

### Step 5 — 對照驗證

實作完成後，逐一核對 `specs/*.md` 的每個 Requirement + Scenario：

| Requirement | Scenario | 實作結果 | 狀態 |
|---|---|---|---|
| 登入 | 成功登入 | SignInViewModel.signIn() | ✅ |
| 登入 | 斷網 | DomainError.network → 顯示網路錯誤文案 | ✅ |

同時確認 TDD 收尾：`{TEST_COMMAND}` 全綠，test-writer 產出的測試**全數由 RED 轉 GREEN**；並執行 `{COVERAGE_COMMAND}` 確認分層覆蓋達標（iOS 慣例 `./scripts/coverage.sh --gate 90`：xccov 分層 Domain/Data/ViewModel、無檔案的層跳過、無效參數拒絕——腳本由目標專案提供）。

若發現不一致，列出差異請使用者確認，不自行修正規格，也不修改測試遷就實作。

---

### Step 6 — 更新 tasks.md

將 `tasks.md` 中已完成的項目勾選：

```markdown
- [x] 1.1 建立 Profile entity
- [x] 1.2 建立 ProfileRepository protocol
```

---

### Step 7 — 回報

```
✅ 實作完成！

📄 規格：openspec/changes/{name}/
📦 功能：<功能名稱>

完成項目：
- Phase 0 Web 對照檢查 ✅
- Phase 1 Domain Layer ✅
- Phase 2 Data Layer ✅
- Phase 3 Composition ✅
- Phase 4 Presentation ✅
- Phase 5 View / Navigation ✅
- {TEST_COMMAND} 全綠（test-writer 測試 RED → GREEN）✅
- {COVERAGE_COMMAND} 通過 ✅
- UI 變更：煙霧測試已跑，截圖路徑＋判讀結果 ✅（非 UI 變更標 N/A）

📝 建議 commit message：
  feat(module): implement xxx feature [{TICKET_PREFIX}-XXX if ticket]

  Spec: openspec/changes/{name}/specs/{spec}/spec.md
  Scenarios: scenario-1, scenario-2
  AI-assisted: {engine}   # 填實際執行引擎:claude / codex

⏭ 後續：commit → push feature branch → 開 PR 至 {GITHUB_REPO}（push / merge 依 user-global 紀律，一律先人工確認）

⚠️ 待確認：
- [ ] <發現的規格不一致或待釐清事項>
```

---

## 常見問題處理

| 狀況 | 處理方式 |
|---|---|
| 找不到 OpenSpec change | 停止，請使用者先建立或將舊規格遷移成 canonical OpenSpec spec |
| 規格有欄位未定義 | 停止，回報使用者補充規格 |
| 既有檔案已存在同名 type | 停止，確認是否覆蓋或合併 |
| 發現規格章節有矛盾 | 停止，明確列出矛盾之處，等待使用者裁示 |
| web 對照元件是 demo/mock（沒真的打 API） | 停止，回報並協助指認真實元件，等待使用者確認後才動工 |
| TDD 模式下測試不存在或非 RED | 停止，回報使用者先跑 test-writer（RED 階段）或確認狀態 |
| 測試與規格矛盾 | 停止，不准改測試遷就實作，列出差異等待裁示 |
| 需要新增 SPM 套件 | 停止，先徵得 owner 同意才加（專案慣例：依賴只用 SPM，目前僅 supabase-swift） |
