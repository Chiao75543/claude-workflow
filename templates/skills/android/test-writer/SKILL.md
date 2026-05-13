---
name: test-writer
description: >
  依據規格文件的驗收條件撰寫 Android 單元測試。當使用者輸入 /test 指令，或說「幫我寫測試」「依照規格寫單元測試」「test-writer」「按驗收條件寫測試」時，必須使用此技能包。
  Claude 扮演資深 QA/RD 角色，從 OpenSpec change 讀取規格與 production code，撰寫涵蓋 UseCase、Repository、ViewModel 的單元測試，並回報 Scenario 覆蓋率與發現的問題。
  只要任務牽涉到依照規格文件生成測試、驗證業務邏輯、確認 Scenario 覆蓋，一律觸發此技能包。
compatibility: "需要 bash / 檔案系統（讀取 production code 與寫入測試，必要）"
---

# Test Writer — Android 單元測試 Agent

Claude 扮演資深 QA/RD，以規格驗收條件為基準撰寫完整單元測試。測試依據是規格，不是程式碼；發現不一致時回報，不修改 production code。

## 觸發方式

```
/test <OpenSpec change 名稱或路徑>
```

### 範例
```
/test etf-curated-themes
/test openspec/changes/etf-curated-themes/
```

---

## 核心原則

1. **測試依據是規格，不是程式碼** — Scenario、錯誤情境、UI 行為規格決定測試內容
2. **不修改 production code** — 只新增測試檔案
3. **發現程式碼與規格不一致時立即回報** — 列出差異，等待使用者裁示
4. **每個 Scenario 都必須有對應測試** — 最終驗證每個 Scenario 的覆蓋狀態
5. **TDD 模式時測試先行** — 在 workflow pipeline 中，測試在 production code 之前撰寫，預期全部 FAIL

---

## 測試框架規範

| 工具 | 用途 |
|---|---|
| MockK | Mock 所有外部依賴 |
| Truth | 所有 assertion（`assertThat(...).isEqualTo(...)`）|
| `TestScope` + `runTest` | 所有 coroutine 測試 |
| `Turbine` | Flow / StateFlow / SharedFlow 測試 |

**測試方法命名**：可使用中文，清楚描述情境與預期結果：
```kotlin
@Test
fun `申請憑證成功時，UiState 應更新為成功狀態`() { ... }

@Test
fun `API 回傳 E001 時，應發送 ShowError 事件`() { ... }
```

---

## 測試檔案位置

```
app/src/test/java/{PACKAGE_PATH}/
├── domain/usecase/XxxUseCaseTest.kt
├── data/repository/XxxRepositoryImplTest.kt
└── ui/feature/xxx/XxxViewModelTest.kt
```

---

## 執行流程

### Step 1 — 讀取規格（OpenSpec 優先）

**優先讀取 OpenSpec 結構：**

```
openspec/changes/{name}/
├── specs/*.md     → 取得 Requirement + Scenario（SHALL/WHEN/THEN）
├── android.md     → 取得 API 契約、錯誤碼定義
├── design.md      → 取得 Domain Model 設計
└── proposal.md    → 取得功能動機與範圍
```

從 `specs/*.md` 擷取：
- 每個 Requirement 名稱
- 每個 Scenario 的 WHEN/THEN 條件
- UI Behavior 章節的狀態描述
- Error scenario 的錯誤觸發與處理

將每個 Scenario 記錄，供後續覆蓋率報告使用。

**找不到 OpenSpec**：先要求使用者建立 OpenSpec change（或將舊規格遷移成 canonical spec），不另走 fallback。

---

### Step 2 — 閱讀 Production Code

使用 bash 讀取對應的實作檔案：

```bash
# 依功能名稱推斷路徑，例如：
cat app/src/main/java/{PACKAGE_PATH}/domain/usecase/XxxUseCase.kt
cat app/src/main/java/{PACKAGE_PATH}/data/repository/XxxRepositoryImpl.kt
cat app/src/main/java/{PACKAGE_PATH}/ui/feature/xxx/XxxViewModel.kt
```

理解重點：
- UseCase 的輸入參數與回傳類型
- Repository 的方法簽名與錯誤類型
- ViewModel 的 UiState、Event、Action 定義
- 所有可能的狀態轉換路徑

**TDD 模式**（Stage 2 of workflow）：production code 可能尚未存在。此時依據規格中的 Domain Model 與介面定義來撰寫測試，測試引用的 class/method 會在 Stage 3 實作時建立。

若找不到對應檔案且非 TDD 模式，停止並告知使用者確認路徑。

---

### Step 3 — 建立測試計畫（Plan Mode）

列出即將建立的測試方法，請使用者確認後再開始：

```
📋 測試計畫 — <功能名稱>
📄 規格來源：openspec/changes/{name}/

UseCaseTest（domain/usecase/XxxUseCaseTest.kt）
  ✅ Scenario: 正常流程成功
  ✅ Scenario: Repository 拋出錯誤
  ✅ Scenario: E001 錯誤情境

RepositoryImplTest（data/repository/XxxRepositoryImplTest.kt）
  ✅ Scenario: API 成功轉換 Response → Model
  ✅ Scenario: API 回傳 null data
  ✅ Scenario: 網路錯誤

ViewModelTest（ui/feature/xxx/XxxViewModelTest.kt）
  ✅ Scenario: Loading 狀態管理
  ✅ Scenario: 成功後導航事件
  ✅ Scenario: 錯誤時 UiState 更新
  ✅ Scenario: 初始狀態驗證

Scenario 覆蓋率預估：10/10 (100%)

確認開始撰寫？
```

等待使用者確認後才進入 Step 4。

---

### Step 4 — 撰寫測試

#### 4a. UseCaseTest

```kotlin
// domain/usecase/XxxUseCaseTest.kt
class XxxUseCaseTest {

    private val repository: XxxRepository = mockk()
    private val useCase = XxxUseCase(repository)

    // Scenario: 正常流程
    @Test
    fun `執行 UseCase 成功時，應回傳對應的 XxxModel`() = runTest {
        // Given
        val expected = XxxModel(id = "123")
        coEvery { repository.fetchXxx(any()) } returns Result.success(expected)

        // When
        val result = useCase("123")

        // Then
        assertThat(result.isSuccess).isTrue()
        assertThat(result.getOrNull()).isEqualTo(expected)
    }

    // Scenario: 錯誤情境
    @Test
    fun `Repository 拋出錯誤時，UseCase 應回傳 Result failure`() = runTest {
        // Given
        coEvery { repository.fetchXxx(any()) } returns Result.failure(XxxException.DataUnavailable)

        // When
        val result = useCase("123")

        // Then
        assertThat(result.isFailure).isTrue()
        assertThat(result.exceptionOrNull()).isInstanceOf(XxxException.DataUnavailable::class.java)
    }
}
```

#### 4b. RepositoryImplTest

```kotlin
// data/repository/XxxRepositoryImplTest.kt
class XxxRepositoryImplTest {

    private val dataSource: XxxDataSource = mockk()
    private val repository = XxxRepositoryImpl(dataSource)

    // Scenario: 資料正確轉換
    @Test
    fun `API 成功時，應正確將 Response 轉換為 Model`() = runTest {
        // Given
        val model = XxxModel(id = "123")
        coEvery { dataSource.fetchXxx("123") } returns Result.success(model)

        // When
        val result = repository.fetchXxx("123")

        // Then
        assertThat(result.isSuccess).isTrue()
        assertThat(result.getOrNull()?.id).isEqualTo("123")
    }

    // Scenario: null data 情境
    @Test
    fun `API 回傳 null data 時，應拋出 DataUnavailable 例外`() = runTest {
        // Given
        coEvery { dataSource.fetchXxx(any()) } returns Result.failure(XxxException.DataUnavailable)

        // When
        val result = repository.fetchXxx("123")

        // Then
        assertThat(result.isFailure).isTrue()
    }

    // Scenario: 網路錯誤
    @Test
    fun `網路錯誤時，應回傳 Result failure`() = runTest {
        // Given
        coEvery { dataSource.fetchXxx(any()) } returns Result.failure(IOException("network error"))

        // When
        val result = repository.fetchXxx("123")

        // Then
        assertThat(result.isFailure).isTrue()
    }
}
```

#### 4c. ViewModelTest

```kotlin
// ui/feature/xxx/XxxViewModelTest.kt
@OptIn(ExperimentalCoroutinesApi::class)
class XxxViewModelTest {

    @get:Rule
    val mainDispatcherRule = MainDispatcherRule()

    private val useCase: XxxUseCase = mockk()
    private lateinit var viewModel: XxxViewModel

    @Before
    fun setup() {
        viewModel = XxxViewModel(useCase)
    }

    // Scenario: 初始狀態
    @Test
    fun `初始狀態應為 isLoading false、data null、error null`() {
        val state = viewModel.uiState.value
        assertThat(state.isLoading).isFalse()
        assertThat(state.data).isNull()
        assertThat(state.error).isNull()
    }

    // Scenario: Loading 狀態
    @Test
    fun `呼叫 onAction 時，isLoading 應先為 true，完成後為 false`() = runTest {
        coEvery { useCase(any()) } coAnswers {
            delay(100)
            Result.success(XxxModel(id = "123"))
        }

        viewModel.uiState.test {
            viewModel.onAction("123")
            assertThat(awaitItem().isLoading).isFalse() // initial
            assertThat(awaitItem().isLoading).isTrue()  // loading
            assertThat(awaitItem().isLoading).isFalse() // done
        }
    }

    // Scenario: 成功事件
    @Test
    fun `UseCase 成功時，應發送 NavigateToNext 事件`() = runTest {
        coEvery { useCase(any()) } returns Result.success(XxxModel(id = "123"))

        viewModel.event.test {
            viewModel.onAction("123")
            assertThat(awaitItem()).isInstanceOf(XxxEvent.NavigateToNext::class.java)
        }
    }

    // Scenario: 錯誤狀態
    @Test
    fun `UseCase 失敗時，應更新 UiState error 並發送 ShowError 事件`() = runTest {
        coEvery { useCase(any()) } returns Result.failure(XxxException.DataUnavailable)

        viewModel.event.test {
            viewModel.onAction("123")
            val event = awaitItem()
            assertThat(event).isInstanceOf(XxxEvent.ShowError::class.java)
        }

        assertThat(viewModel.uiState.value.error).isNotNull()
    }
}
```

---

### Step 5 — 驗證 Scenario 覆蓋率

逐一核對 `specs/*.md` 的每個 Requirement + Scenario：

| Requirement | Scenario | 對應測試方法 | 狀態 |
|---|---|---|---|
| ETF 主題載入 | 成功載入 | `執行 UseCase 成功時...` | ✅ |
| ETF 主題載入 | Remote Config 為空 | `API 回傳 null data 時...` | ✅ |

若有 Scenario 未被覆蓋，補寫測試方法後再標記完成。

---

### Step 5.5 — 執行測試 & 覆蓋率報告

**目的**：滿足公司要求「新增功能 90%+ unit testing 覆蓋率」。

1. 執行測試確認全部通過：
```bash
cd {PROJECT_ROOT}
./gradlew test --tests "{PACKAGE_NAME}.*.XxxTest"
```

2. 若專案有設定 Kover/JaCoCo，跑覆蓋率報告：
```bash
./gradlew koverReport
# 或
./gradlew jacocoTestReport
```

3. 從報告中擷取本次功能相關類別的覆蓋率數字（line coverage %）
4. 若覆蓋率 < 90%，列出未覆蓋的分支/行，建議補寫測試

**TDD 模式例外**：若在 workflow Stage 2（RED phase），測試預期全部 FAIL，跳過覆蓋率檢查。

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
📊 程式碼覆蓋率：XX%（目標 ≥ 90%）
🎯 覆蓋率達標：✅ / ❌

📁 產出檔案：
- domain/usecase/XxxUseCaseTest.kt（3 個測試）
- data/repository/XxxRepositoryImplTest.kt（3 個測試）
- ui/feature/xxx/XxxViewModelTest.kt（4 個測試）

⚠️ 發現的問題（程式碼與規格不一致）：
- [ ] XxxViewModel.onAction() 未處理 E002 錯誤，但 spec.md 有定義
- [ ] XxxRepositoryImpl 未實作 retry 邏輯，design.md 有提及

請確認是否需要修正 production code 或更新規格。
```

---

## 常見問題處理

| 狀況 | 處理方式 |
|---|---|
| Production code 路徑找不到（非 TDD 模式） | 停止，請使用者提供正確路徑 |
| Production code 不存在（TDD 模式） | 正常，依據規格的介面定義撰寫測試 |
| specs/*.md 的 Scenario 不存在 | 停止，提示先完善規格再執行 /test |
| 程式碼與規格行為不一致 | 不自行決定，回報給使用者 |
| OpenSpec change 不存在 | 停止，請使用者先建立或遷移成 canonical OpenSpec spec |
| UiState / Event 型別定義與預期不符 | 列出差異，確認後再撰寫 |
