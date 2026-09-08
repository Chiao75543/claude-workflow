# 派遣 prompt 骨架

persona 已經寫在 `agents/*.md` 的定義裡,所以派遣訊息只負責**提供素材**和**指定這一次的視角**。
不要在派遣訊息裡重複 persona —— 重複會稀釋定義,而且兩邊哪天不一致就沒人知道以哪邊為準。

---

## S3 · spec-grill

```
Agent(subagent_type="spec-grill", prompt=...)
```

素材:

- 工作目錄(它有 Read/Grep/Glob,自己會去看)
- 專案分層與鐵則摘要(或直接指 AGENTS.md / CLAUDE.md 的路徑)
- **與這個功能相關的既有事實** —— 已經做完什麼、哪些是既有 bug 不在範圍內
- 草稿規格的路徑

明確指定要它評估的**已知風險**(如果有):

> 特別請你評估這兩個我已知的風險是否被規格正確處理:…

已知風險要點名,否則它會花力氣重新發現你已經知道的事。

---

## S4 · spec-reader ×2

```
Agent(subagent_type="spec-reader", prompt=...)   # ×2,一則訊息同時派
```

**規格內容直接貼在 prompt 裡** —— 它沒有工具,這是刻意的隔離。

必須附上的最小 API 脈絡:型別/介面簽章、錯誤型別的可用值域、列舉的值域。
不要附實作、不要附別人寫的測試。

兩個派遣的差別只有一句:

- 第一個:「你的視角是**字面讀者** —— 按字面讀,不腦補作者意圖。」
- 第二個:「你的視角是**敵意讀者** —— 找出完全符合字面但顯然不是本意的讀法。
  額外質疑**範例資料本身**:那組資料分得出正確與錯誤的實作嗎?」

輸出格式(兩者相同,才機械比對得起來):

```
SC-001:
  - in:  {具體字面值}
    out: {具體字面值}
```

---

## G10 · spec-oracle

```
Agent(subagent_type="spec-oracle", prompt=...)
```

**規格 + public API 簽章直接貼在 prompt 裡。不給實作、不給既有測試。**

要附上:

- 測試框架與慣例(它要寫出可編譯的檔案)
- mock 縫開在哪個介面
- 規格的每一條 Scenario 與其 `examples`

明確告訴它裁判規則,它才知道斷言要能對回規格:

> 你的斷言會被這樣裁判:與規格例子矛盾 → 判你錯自動作廢;
> 與例子一致但實作沒過 → 實作有 bug;落在例子之外 → 記成規格缺口。

---

## G11 · code-adversary

```
Agent(subagent_type="code-adversary", prompt=...)
```

素材:

- 工作目錄與 base 分支(它自己跑 `git diff`)
- 規格路徑
- **測試指令**(它要實跑重現與變異)
- 專案鐵則與 Security Baseline
- **已知並已接受的取捨清單** —— 不列的話它會重提你已經決定接受的事

最後一段一定要保留:

> 找不到就誠實寫「CRITICAL:無」,並詳列你檢查過哪些面向。
> 那是有價值的資訊,不是失敗。不要為了交差硬湊。

沒有這句,它會為了交差生出低品質的 finding。

---

## S7 · red-writer(opus)

```
Agent(subagent_type="red-writer", prompt=...)
```

素材:凍結規格的路徑、專案 `test-writer` skill 的路徑、測試指令、`red-capture` 的用法
(`evidence/red-inputs.json` 的格式)。

**不要在派遣訊息重述 stub 規則** —— 定義裡有。給素材就好。

驗收:報告必須含 `red-capture` 的輸出原文。只回「完成」→ 退回。

---

## S8 · green-writer(opus)

```
Agent(subagent_type="green-writer", prompt=...)
```

素材:凍結測試的路徑、專案 `rd-implementer` skill 的路徑、測試指令、
**已知並已接受的取捨**(不列的話它會重提)。

驗收:報告必須含測試結果原文,以及「規格與現實的衝突」一節(沒有就明寫沒有)。
收到衝突回報 → orchestrator 走 `spec-diff` 流程,**不要叫它自己解**。
