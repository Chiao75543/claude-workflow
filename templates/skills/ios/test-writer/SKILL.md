---
name: test-writer
description: >
  依據規格文件的驗收條件撰寫 iOS 單元測試。當使用者輸入 /test 指令，或說「幫我寫測試」「依照規格寫單元測試」「test-writer」「按驗收條件寫測試」時，必須使用此技能包。
  Claude 扮演資深 QA/RD 角色，從 OpenSpec change 讀取規格與 production code，以 Swift Testing 撰寫涵蓋 UseCase、Repository、ViewModel 的單元測試，並回報 Scenario 覆蓋率與發現的問題。
  只要任務牽涉到依照規格文件生成測試、驗證業務邏輯、確認 Scenario 覆蓋，一律觸發此技能包。
compatibility: "需要 bash / 檔案系統（讀取 production code 與寫入測試，必要）"
---

# Test Writer — iOS 單元測試 Agent

Claude 扮演資深 QA/RD，以規格驗收條件為基準撰寫完整單元測試。測試依據是規格，不是程式碼；發現不一致時回報，不修改 production code。

## 觸發方式

```
/test <OpenSpec change 名稱或路徑>
```

### 範例
```
/test auth-sign-in
/test openspec/changes/auth-sign-in/
```

---

## 核心原則

1. **測試依據是規格，不是程式碼** — Scenario、錯誤情境、UI 行為規格決定測試內容
2. **不修改 production code** — 只新增測試檔案（TDD 模式例外：允許新增「空殼」stub 讓測試可編譯，見 Step 2）
3. **發現程式碼與規格不一致時立即回報** — 列出差異，等待使用者裁示
4. **每個 Scenario 都必須有對應測試** — 最終驗證每個 Scenario 的覆蓋狀態
5. **TDD 模式時測試先行** — 在 workflow pipeline 中，測試在 production code 之前撰寫，預期全部 FAIL（true RED）

---

## 測試型態分類（6a / 6b / 6c）

依 Scenario 內容分類，一個 change 可混用三種：

| 型態 | 判斷依據 | 產出 |
|---|---|---|
| **6a Unit-test** | 行為規格：狀態轉換、資料轉換、錯誤處理（`WHEN <user action>` / `WHEN <external system returns>`） | Swift Testing 單元測試（本文件主體，Step 4a–4c） |
| **6b Static-validation** | 設定檔斷言：`WHEN 檢視 project.yml / Info.plist / *.xcconfig`、`THEN (NOT) contains <pattern>` | assertion script（grep / PlistBuddy，Step 4d） |
| **6c Manual-smoke** | 需真機／模擬器實測或 build 產物檢查（APNs 權限彈窗、Universal Links 實跳、上架前產物檢查） | `smoke-checklist.md`，無自動測試（Step 4e） |

---

## 測試框架規範

| 工具 | 用途 |
|---|---|
| Swift Testing（`@Test` / `#expect` / `#require`） | 所有測試；**不用 XCTest** |
| 手刻 spy/stub（無 MockK 這類框架） | mock 縫**只開在 Repository 與外部服務 protocol**；UseCase 是具體 struct 不做 protocol，不 mock |
| URLProtocol stub | APIClient／網路層測試（URLSession 可注入） |
| `Fixtures/*.json` decode 測試 | **契約鎖**：真實 API 回應樣本，web 端改壞先在這爆 |
| 真 UseCase + 假 Repository | ViewModel 測試，測真實協作，不做 mock 對 mock |

**測試方法命名**：`@Test` 的 display name 用中文，清楚描述情境與預期結果；function 名用簡短英文：
```swift
@Test("登入成功時，ViewModel 應更新為已登入狀態")
func signInSuccess() async throws { ... }

@Test("API 回傳 {error} 時，應直顯繁中文案")
func serverErrorShowsMessage() async { ... }
```

---

## 測試檔案位置

```
{PROJECT_ROOT}/
├── Packages/MindEYDomain/Tests/MindEYDomainTests/
│   └── XxxUseCaseTests.swift            # UseCase + Domain 純函式（鐵則回歸包）
├── Packages/MindEYData/Tests/MindEYDataTests/
│   ├── XxxRepositoryImplTests.swift     # URLProtocol stub
│   └── Fixtures/                        # 真實 API 回應樣本 *.json（Package.swift 標 resources）
└── MindEYTests/
    └── XxxViewModelTests.swift          # ViewModel（真 UseCase + 假 Repository）
```

假 Repository 手刻於各測試 target；跨 target 重複時可抽共用 TestSupport target。

---

## 執行流程

### Step 1 — 讀取規格（OpenSpec 優先）

**優先讀取 OpenSpec 結構：**

```
openspec/changes/{name}/
├── specs/*.md     → 取得 Requirement + Scenario（SHALL/WHEN/THEN）
├── ios.md         → 取得 API 契約、錯誤碼定義
├── design.md      → 取得 Domain Model 設計
└── proposal.md    → 取得功能動機與範圍
```

從 `specs/*.md` 擷取：
- 每個 Requirement 名稱
- 每個 Scenario 的 WHEN/THEN 條件
- UI Behavior 章節的狀態描述
- Error scenario 的錯誤觸發與處理

將每個 Scenario 記錄並標定型態（6a/6b/6c），供後續覆蓋率報告使用。

**找不到 OpenSpec**：先要求使用者建立 OpenSpec change（或將舊規格遷移成 canonical spec），不另走 fallback。

---

### Step 2 — 閱讀 Production Code

使用 bash 讀取對應的實作檔案：

```bash
# 依功能名稱推斷路徑，例如：
cat Packages/MindEYDomain/Sources/MindEYDomain/UseCases/auth/SignInUseCase.swift
cat Packages/MindEYData/Sources/MindEYData/Repositories/AuthRepositoryImpl.swift
cat App/Features/SignIn/SignInViewModel.swift
```

理解重點：
- UseCase 的輸入參數與回傳／拋錯型別
- Repository protocol 的方法簽名與 `DomainError` 種類
- ViewModel（`@Observable @MainActor`）暴露的狀態值與 intent 方法
- 所有可能的狀態轉換路徑

**TDD 模式（workflow 的 test-writer／RED 階段）**：production code 可能尚未存在。Swift 與 Kotlin 現實不同：protocol conformance 不完整時**整個 target 編不過**，測試連跑都跑不起來，所以「stub-first 讓測試可編譯」不是選項而是必要步驟：

1. 依 spec 的 Domain Model 先在 `MindEYDomain` 定好 Entity 與 Repository protocol
2. 建最小空殼實作，讓 RED 測試可編譯：
```swift
public struct SignInUseCase {
    let auth: AuthRepository
    public init(auth: AuthRepository) { self.auth = auth }
    public func callAsFunction(email: String, password: String) async throws {
        fatalError("未實作")   // implement 階段填肉
    }
}
```
3. 測試以「未實作」行為 FAIL = true RED（若 `fatalError` crash 中斷整包測試回報，空殼可改丟 `DomainError.notConfigured`，RED 效果相同）

空殼只有型別簽名、沒有邏輯，不算違反「不修改 production code」原則。

若找不到對應檔案且非 TDD 模式，停止並告知使用者確認路徑。

---

### Step 3 — 建立測試計畫（Plan Mode）

列出即將建立的測試方法，請使用者確認後再開始：

```
📋 測試計畫 — <功能名稱>
📄 規格來源：openspec/changes/{name}/
🧪 型態：6a unit（含 6b/6c Scenario 時另列）

UseCaseTests（MindEYDomainTests/SignInUseCaseTests.swift）
  ✅ Scenario: 正常流程成功
  ✅ Scenario: Repository 拋出 server 錯誤
  ✅ Scenario: 斷網錯誤原樣上拋

RepositoryImplTests（MindEYDataTests/ProfileRepositoryImplTests.swift）
  ✅ Scenario: API 成功轉換 DTO → Entity
  ✅ Scenario: 契約鎖 — 真實回應樣本 decode
  ✅ Scenario: API 回傳 {error} 轉 DomainError.server

ViewModelTests（MindEYTests/SignInViewModelTests.swift）
  ✅ Scenario: 初始狀態驗證
  ✅ Scenario: Loading 狀態管理
  ✅ Scenario: 成功後導航事件
  ✅ Scenario: 錯誤時文案直顯

Scenario 覆蓋率預估：10/10 (100%)

確認開始撰寫？
```

等待使用者確認後才進入 Step 4。

---

### Step 4 — 撰寫測試

#### 4a. UseCaseTests（Domain 層）

mock 縫只開在 Repository：手刻 stub 預設回傳結果、記錄呼叫。

```swift
// Packages/MindEYDomain/Tests/MindEYDomainTests/SignInUseCaseTests.swift
import Testing
@testable import MindEYDomain

// 手刻假 Repository：可預設結果、記錄呼叫（spy + stub 合一）
final class AuthRepositoryStub: AuthRepository {
    var signInResult: Result<Void, DomainError> = .success(())
    private(set) var signInCalls: [(email: String, password: String)] = []

    func signIn(email: String, password: String) async throws {
        signInCalls.append((email, password))
        try signInResult.get()
    }
}

struct SignInUseCaseTests {

    // Scenario: 正常流程
    @Test("登入成功時，應以輸入參數呼叫 Repository 一次")
    func signInSuccess() async throws {
        let repo = AuthRepositoryStub()
        let useCase = SignInUseCase(auth: repo)

        try await useCase(email: "iostest+1@example.com", password: "secret")

        #expect(repo.signInCalls.count == 1)
        #expect(repo.signInCalls.first?.email == "iostest+1@example.com")
    }

    // Scenario: 錯誤情境
    @Test("Repository 拋出 server 錯誤時，UseCase 應原樣上拋，不吞錯改寫")
    func signInServerError() async {
        let repo = AuthRepositoryStub()
        repo.signInResult = .failure(.server(status: 401, message: "帳號或密碼錯誤"))
        let useCase = SignInUseCase(auth: repo)

        await #expect(throws: DomainError.self) {
            try await useCase(email: "iostest+1@example.com", password: "wrong")
        }
    }
}
```

#### 4b. RepositoryImplTests（Data 層）

網路層用 URLProtocol stub（APIClient 需可注入 `URLSession`）；API 回應形狀用 `Fixtures/*.json` decode 測試鎖契約。`Fixtures.load` 從 `Bundle.module` 讀 `Tests/MindEYDataTests/Fixtures/*.json`；`URLProtocolStub` 為測試 target 內手刻的 `URLProtocol` 子類。

**Fixture 抓取的衛生硬約束**（若專案直打 production，違反任一條立即停止；權威出處 = 專案 CLAUDE.md 的測試資料衛生規則）：
- 只用專案指定的測試帳號範圍；互動只准發生在測試帳號之間
- 絕不呼叫專案標記為禁用的端點（無驗證 stub、排程專用等）
- 抓取過程建立的資料依專案慣例加測試前綴並於抓完清理
- fixture 存檔前檢查：樣本內不得含真實使用者的個資——有就換測試帳號資料重抓

```swift
// Packages/MindEYData/Tests/MindEYDataTests/ProfileRepositoryImplTests.swift
import Testing
import Foundation
import MindEYDomain
@testable import MindEYData

struct ProfileRepositoryImplTests {

    // Scenario: 資料正確轉換
    @Test("API 200 時，應正確將 DTO 轉換為 Entity")
    func fetchProfileSuccess() async throws {
        URLProtocolStub.enqueue(status: 200, data: try Fixtures.load("profile_ok.json"))
        let repository = ProfileRepositoryImpl(api: APIClient(session: URLProtocolStub.session()))

        let profile = try await repository.fetchProfile(id: "123")

        #expect(profile.id == "123")
    }

    // Scenario: 契約鎖 — 真實回應樣本 decode
    @Test("契約鎖：conversations 樣本可 decode，created_at 原字串一字不改")
    func conversationsFixtureDecodes() throws {
        let data = try Fixtures.load("conversations_list.json")
        let dto = try APIClient.decoder.decode(ConversationsResponseDTO.self, from: data)
        let first = try #require(dto.conversations.first)
        #expect(first.createdAt.raw == "2026-08-01T03:21:45.123456")  // 微秒精度、無時區後綴（鐵則）
    }

    // Scenario: 錯誤情境
    @Test("API 回傳 {error} 時，應轉成 DomainError.server 並保留繁中文案")
    func serverErrorKeepsMessage() async {
        URLProtocolStub.enqueue(status: 400, data: Data(#"{"error":"找不到使用者"}"#.utf8))
        let repository = ProfileRepositoryImpl(api: APIClient(session: URLProtocolStub.session()))

        do {
            _ = try await repository.fetchProfile(id: "123")
            Issue.record("應拋出 DomainError.server")
        } catch DomainError.server(_, let message) {
            #expect(message == "找不到使用者")
        } catch {
            Issue.record("錯誤型別不符：\(error)")
        }
    }
}
```

#### 4c. ViewModelTests（App 層）

**真 UseCase + 假 Repository**：只替換 Repository，UseCase 用真的，測真實協作。

```swift
// {PROJECT_ROOT}/MindEYTests/SignInViewModelTests.swift
import Testing
import MindEYDomain
@testable import MindEY

@MainActor
struct SignInViewModelTests {

    private func makeVM(repo: AuthRepositoryStub = AuthRepositoryStub()) -> SignInViewModel {
        SignInViewModel(signIn: SignInUseCase(auth: repo))   // 真 UseCase + 假 Repository
    }

    // Scenario: 初始狀態
    @Test("初始狀態應為 isLoading false、errorMessage nil")
    func initialState() {
        let vm = makeVM()
        #expect(vm.isLoading == false)
        #expect(vm.errorMessage == nil)
    }

    // Scenario: 成功流程
    @Test("登入成功時，isLoading 收尾為 false 且無錯誤")
    func signInSuccess() async {
        let vm = makeVM()

        await vm.submit(email: "iostest+1@example.com", password: "secret")

        #expect(vm.isLoading == false)
        #expect(vm.errorMessage == nil)
    }

    // Scenario: 錯誤狀態
    @Test("server 錯誤時，errorMessage 直顯 API 繁中文案，不得改寫")
    func serverErrorShowsMessage() async {
        let repo = AuthRepositoryStub()
        repo.signInResult = .failure(.server(status: 401, message: "帳號或密碼錯誤"))
        let vm = makeVM(repo: repo)

        await vm.submit(email: "iostest+1@example.com", password: "wrong")

        #expect(vm.errorMessage == "帳號或密碼錯誤")   // 禁止吞錯改寫（如把斷網顯示成「帳密錯誤」）
    }
}
```

#### 4d. 6b 靜態驗證（project.yml / Info.plist / xcconfig）

設定檔類 Scenario 不寫 unit test，改寫 assertion script，每個 Scenario 一條檢查：

```bash
# tests/static_validation.sh
set -euo pipefail
# Scenario: project.yml 的 deploymentTarget 必須是 iOS 17+
grep -q 'deploymentTarget: "17' project.yml || { echo "FAIL: deploymentTarget 非 17+"; exit 1; }
# Scenario: Info.plist 必須含相機用途描述
/usr/libexec/PlistBuddy -c "Print :NSCameraUsageDescription" App/Info.plist >/dev/null \
  || { echo "FAIL: 缺 NSCameraUsageDescription"; exit 1; }
# Scenario: 金鑰樣板不得含真值
! grep -qE 'SUPABASE_ANON_KEY *= *ey' Configs/Secrets.xcconfig.example \
  || { echo "FAIL: 樣板含真金鑰"; exit 1; }
echo "PASS"
```

先對現狀執行一次確認 FAIL（true RED），實作完成後轉 PASS。

#### 4e. 6c Manual-smoke checklist

無法自動化的 Scenario（真機推播、Universal Links 實跳、build 產物檢查）寫成 `openspec/changes/{name}/smoke-checklist.md`：每條 scenario + 預期結果 + checkbox。明確告知使用者：實作完成後須手動跑完矩陣；此類 Scenario 無自動測試、跳過覆蓋率檢查。

---

### Step 5 — 驗證 Scenario 覆蓋率

逐一核對 `specs/*.md` 的每個 Requirement + Scenario：

| Requirement | Scenario | 對應測試方法 | 狀態 |
|---|---|---|---|
| 登入 | 成功登入 | `登入成功時，應以輸入參數...` | ✅ |
| 登入 | API 回傳 {error} | `API 回傳 {error} 時，應轉成...` | ✅ |
| 專案設定 | deploymentTarget 17+ | `static_validation.sh` 第 1 條 | ✅（6b） |

若有 Scenario 未被覆蓋，補寫測試方法後再標記完成。

---

### Step 5.5 — 執行測試 & 覆蓋率報告

**目的**：滿足「新增功能 90%+ unit testing 覆蓋率」門檻（line coverage，計 Domain／Data／ViewModel，**View 不計**）。

1. 執行測試確認全部通過：
```bash
cd {PROJECT_ROOT}
{TEST_COMMAND}    # iOS 專案通常填 scripts/verify.sh（xcodegen → build → 全部測試）
```

單獨跑測試（迭代時較快）：
```bash
xcodebuild -project MindEY.xcodeproj -scheme MindEY -destination 'platform=iOS Simulator,name=iPhone 17 Pro' test
# 只跑單一 suite 可加 -only-testing:MindEYDomainTests/SignInUseCaseTests
```

2. 覆蓋率從 xcresult 以 xccov 擷取：
```bash
xcodebuild -project MindEY.xcodeproj -scheme MindEY \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' \
  -enableCodeCoverage YES -resultBundlePath build/tests.xcresult test
xcrun xccov view --report build/tests.xcresult
```

3. 從報告中擷取本次功能相關檔案（Domain／Data／ViewModel）的 line coverage %
4. 若覆蓋率 < 90%，列出未覆蓋的分支／行，建議補寫測試

**TDD 模式例外**：RED 階段測試預期全部 FAIL，**跳過覆蓋率**（coverage 腳本需測試全綠才能產出報告）；GREEN 後由 rd-implementer 執行 `{COVERAGE_COMMAND}` 把關。6c Scenario 亦無覆蓋率可計。

---

### Step 6 — 更新規格 Test Coverage

在 OpenSpec change 內補充 test coverage 資訊（若 spec 有欄位），或在 `tasks.md` 勾選 test 任務完成。

---

### Step 7 — 回報測試報告

```
✅ 測試撰寫完成！

📦 功能：<功能名稱>
📄 規格：openspec/changes/{name}/

📊 Scenario 覆蓋率：10/10（100%）
📊 程式碼覆蓋率：XX%（目標 ≥ 90%，View 不計）
🎯 覆蓋率達標：✅ / ❌

📁 產出檔案：
- MindEYDomainTests/SignInUseCaseTests.swift（3 個測試）
- MindEYDataTests/ProfileRepositoryImplTests.swift（3 個測試）
- MindEYTests/SignInViewModelTests.swift（4 個測試）
- tests/static_validation.sh（6b，如適用）
- smoke-checklist.md（6c，如適用）

⚠️ 發現的問題（程式碼與規格不一致）：
- [ ] SignInViewModel 未處理 DomainError.network，但 spec.md 有定義
- [ ] AuthRepositoryImpl 未依 design.md 把 created_at decode 成 ServerTimestamp

請確認是否需要修正 production code 或更新規格。
```

---

## 常見問題處理

| 狀況 | 處理方式 |
|---|---|
| Production code 路徑找不到（非 TDD 模式） | 停止，請使用者提供正確路徑 |
| Production code 不存在（TDD 模式） | 正常；先建 Repository protocol + `fatalError("未實作")` 空殼讓測試可編譯（見 Step 2） |
| 測試 target 編不過（protocol conformance 不完整） | 補齊空殼 conformance 簽名，不填業務邏輯 |
| specs/*.md 的 Scenario 不存在 | 停止，提示先完善規格再執行 /test |
| 程式碼與規格行為不一致 | 不自行決定，回報給使用者 |
| OpenSpec change 不存在 | 停止，請使用者先建立或遷移成 canonical OpenSpec spec |
| ViewModel 狀態／事件型別定義與預期不符 | 列出差異，確認後再撰寫 |
