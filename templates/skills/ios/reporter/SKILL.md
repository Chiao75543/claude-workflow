---
name: reporter
description: >
  Code Review 完成後產出規格與實作對照報告，儲存為本地 .md 或 .html 檔案。當使用者輸入 /report 指令，或 /verify、/review-mr 執行完畢後，必須使用此技能包產出報告。
  報告內容包含：Requirement × Scenario 覆蓋率、每個 Scenario vs 實作對照表、問題清單摘要。
  以 OpenSpec change 為單一資料來源。
  只要任務牽涉到產出 code review 報告、規格對照報告、覆蓋分析，一律觸發此技能包。
compatibility: "需要 bash / 檔案系統（寫入報告檔案，必要）"
---

# Reporter — 規格與實作對照報告

在 `/verify` 或 `/review-mr` 完成後（或手動執行 `/report`），自動產出一份本地報告檔案，清楚呈現規格覆蓋率與每個 Scenario 的實作狀態。

## 觸發方式

```
/report <OpenSpec change 名稱或路徑> [--format md|html]
```

或由 `/verify`、`/review-mr` 完成後自動呼叫。

### 範例
```
/report etf-curated-themes
/report openspec/changes/etf-curated-themes/ --format html
```

預設輸出格式：`.md`

---

## ⛔ 前置條件（Gate）

**Reporter 只在審查通過後才執行。** 執行前必須確認：

```
觸發條件（滿足其一）：
✅ code-reviewer 明確輸出「✅ 可以 Commit」
✅ mr-reviewer 明確輸出「✅ 可以 Merge」
```

若有未解決的 CRITICAL 問題：

```
⛔ Reporter 不執行

原因：審查尚未通過，仍有 X 個 CRITICAL 問題待修正。
請修正後重新執行 /verify 或 /review-mr，
審查通過後將自動產出報告。
```

---

## 執行流程

### Step 1 — 收集資料

**來源 A：規格文件（OpenSpec 優先）**

OpenSpec change 內：
- `specs/*.md` — 所有 Requirement + Scenario（作為覆蓋率基準）
- `ios.md` — API Contract + Navigation（驗證一致性）
- `tasks.md` — 實作清單（驗證完成度）
- `design.md` — Domain Model（驗證結構一致）

**模式判定（雙模式）**：
- **Pipeline 模式**（Stage 7.5 / verify 之後，有具名 change）：報告除本地檔名外，**同步寫入 canonical `openspec/changes/{name}/report.md`**。找不到 change → 停止並要求建立，不走 fallback。
- **獨立 PR review 模式**（`/review-mr` 後、無對應 change）：接受 `--spec <name>` 指定；未指定且找不到 spec 時，產出 PR-only 報告 `report_pr{PR_ID}_{YYYYMMDD}.md`——僅含 findings 摘要與品質評分、開頭標明「無規格對照」，不做 Requirement × Scenario 覆蓋表。

**來源 B：實作現況（從 git diff 或檔案系統）**

**來源 C：Review 結果（從 /verify 或 /review-mr 的輸出）**

---

### Step 2 — 計算覆蓋率

以 Requirement × Scenario 為單位：

```
狀態判定規則：
✅ 已實作   — 對應的程式碼存在且與 Scenario 描述一致
⚠️ 部分實作  — 程式碼存在但有缺漏或與規格有差異
❌ 未實作   — 完全找不到對應實作
🔍 無法驗證  — 需人工確認（如 UI 動畫、第三方整合）
```

---

### Step 3 — 產出報告

**檔案命名規則（依模式）**：
```
Pipeline 模式:report_{change-name}_{YYYYMMDD}.md / .html
             （並同步寫入 canonical openspec/changes/{name}/report.md）
PR-only 模式:report_pr{PR_ID}_{YYYYMMDD}.md
             （僅 findings 摘要+品質評分,開頭標明「無規格對照」,不做 Scenario 覆蓋表）
```

---

## Markdown 報告範本 — OpenSpec 格式

````markdown
# 📋 Code Review 報告 — <功能名稱>

> 規格：`openspec/changes/{name}/`
> 產出時間：<YYYY-MM-DD HH:mm>
> Reviewer：Codex

---

## 📊 總覽

| 項目 | 結果 |
|---|---|
| 功能名稱 | <功能名稱> |
| 規格來源 | `openspec/changes/{name}/` |
| Requirement 總數 | N 個 |
| Scenario 總數 | N 個 |
| Scenario 覆蓋率 | X / N（XX%）|
| 實作清單完成率 | X / N（XX%）|
| 覆蓋率達標 | ✅ / ❌ |
| 品質評分 | XX / 100 |
| CRITICAL 問題 | X 個 |
| WARNING 問題 | X 個 |
| AI 產出比例 | XX%（AI 產出檔案 / 總變更檔案）|

---

## ✅ Requirement × Scenario 對照表

### Requirement: ETF精選主題頁面載入主題分類
> 來源：`specs/etf-theme-screen/spec.md`

| Scenario | 狀態 | 對應實作 | 備註 |
|---|---|---|---|
| 成功載入主題分類 | ✅ 已實作 | `EtfThemeViewModel.swift:42` | |
| Remote Config 為空 | ✅ 已實作 | `EtfThemeViewModel.swift:58` | |
| 網路異常 | ⚠️ 部分實作 | `EtfThemeViewModel.swift:65` | 缺少離線提示 |

### Requirement: ETF 按鈕點擊帶入商品代碼
> 來源：`specs/etf-theme-to-pockettw/spec.md`

| Scenario | 狀態 | 對應實作 | 備註 |
|---|---|---|---|
| 已登入，點擊 ETF | ✅ 已實作 | `EtfThemeView.swift:120` | |
| 未登入，點擊 ETF | ❌ 未實作 | — | AuthRequiredWrapper 未包裹 |

**Scenario 覆蓋率：3 / 5（60%）**

---

## 📁 實作清單對照表（tasks.md）

| Task | Layer | 狀態 |
|---|---|---|
| 1.1 建立 EtfTheme domain model | Domain | ✅ 存在 |
| 1.2 建立 EtfThemeRepository protocol | Domain | ✅ 存在 |
| 2.1 建立 EtfThemeDTO | Data | ✅ 存在 |
| 3.1 註冊 DI | DI | ⚠️ 存在但 UseCase 未註冊 |

---

## 🔴 CRITICAL 問題（X 個）

### C-1｜{問題標題}
- **檔案**：`XxxViewModel.swift`，第 65 行
- **對應規格**：`specs/{name}/spec.md` — Requirement: {name} — Scenario: {name}
- **問題**：...
- **建議**：...

---

## 🟡 WARNING 問題（X 個）

### W-1｜{問題標題}
- **檔案**：...
- **問題**：...
- **建議**：...

---

## 💡 SUGGESTION（X 個）

### S-1｜{問題標題}
- **建議**：...

---

## 🚩 需人工確認事項

- [ ] ...

---

## 📱 owner 驗收清單（gate 5，Claude 驗不了的部分）

自動彙整以下來源，逐條列給 owner 人工驗收：
- `smoke-checklist.md`（6c manual-smoke Scenario）尚未勾選的項目
- 本 change 涉及的真機專屬項：推播、相機/相簿、麥克風、鍵盤行為、深連結實跳、背景/前景切換
- （無適用項時本段標「無」，不留空）

## 📌 結論與下一步

**整體評估**：<綜合評估一段話>

**必須完成後才可合併**：
- [ ] ...

**建議在本 PR 內處理**：
- [ ] ...

---

*🤖 由 Codex 自動產出*
````

---

## HTML 報告範本（`--format html`）

輸出為單一 `.html` 檔，包含：

- **頂部 Dashboard**：Scenario 覆蓋率圓形進度條、品質評分大數字、CRITICAL/WARNING 計數
- **Requirement × Scenario 對照表**：可按 Requirement 摺疊、按狀態篩選
- **問題清單**：CRITICAL → WARNING → SUGGESTION 依序展開
- **配色**：✅ 綠色、⚠️ 橙色、❌ 紅色、🔍 灰色

---

## 與其他技能包的整合

| 觸發來源 | 傳入資料 | 報告自動包含 |
|---|---|---|
| `/verify` 完成後 | 規格路徑 + review 結果 | Scenario 對照表 + 問題清單 + 品質評分 |
| `/review-mr` 完成後 | PR ID + 規格路徑 + review 結果 | Scenario 對照表 + 問題清單 + 品質評分 |
| `/report` 獨立執行 | 規格路徑（重新讀取） | Scenario 對照表（無品質評分，除非提供） |

---

## 常見問題處理

| 狀況 | 處理方式 |
|---|---|
| 找不到 OpenSpec change | Pipeline 模式：停止並要求建立；PR-only 模式（/review-mr 後、無具名 change）：改產 `report_pr{PR_ID}_{YYYYMMDD}.md` |
| 無 git diff（獨立執行） | 改用 find 掃描對應目錄，標注「靜態分析」 |
| Scenario 描述模糊難以判定狀態 | 標記為 🔍 無法驗證，列入人工確認清單 |
| 輸出目錄無寫入權限 | 改輸出至當前目錄 `./` |
