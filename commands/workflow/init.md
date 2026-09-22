---
name: "workflow:init"
description: "第一次在一個專案用 pipeline:問一輪設定問卷(技術棧 / 指令含 smoke / 主線與自動推 / CI 有無 / 邊界 / 模型),寫成 specs/pipeline.yaml,config-check 過了才算完成。"
category: Workflow
tags: [workflow, init, config]
---

跑 S0:專案問卷 → `specs/pipeline.yaml`。

**什麼時候跑**

`specs/pipeline.yaml` 不存在,或 `scripts/gates/config-check` 說有缺。
`/workflow` 自己會在 S0 檢查並轉進來,也可以手動叫。

**動作**

先看專案(`AGENTS.md`、`CLAUDE.md`、build 設定、既有測試)能自己推出多少,**推得出的當預設值,
問的時候帶著**。然後用 `AskUserQuestion` 一組一組問,每組最多四題:

| 組 | 問題 | 鍵 |
|---|---|---|
| 技術棧 | 測試框架是哪個?(swift-testing / junit / pytest / jest …;決定 `red-capture` 解析器)| `runner` |
| | 測試檔在哪些路徑?| `tests.globs` |
| | 測試怎麼標 Scenario 編號?(預設:測試描述字串以 `SC-nnn` 開頭)| `tests.scenario_pattern` |
| 指令 | 跑全部測試的指令?| `test` |
| | lint 指令?(會把變更檔的路徑接在後面)| `lint` |
| | **smoke 指令?** 用真的入口跑一次、拿到真的結果 —— UI 就開 app 導航到目標畫面截圖到 `$SMOKE_SCREENSHOTS`;API 就打一次端點;CLI 就跑一次。沒有的話**現在一起寫一支** `scripts/smoke.sh` | `smoke` `smoke_timeout` `smoke_max_s`(整支 smoke 的秒數上限,效能底線;不填不檢查) |
| 版本 | 整合分支叫什麼?| `integration_branch` |
| | 全綠零待決時可以自動推功能分支 + 開 PR 嗎?(整合分支永遠不直推)| `auto_push` |
| | 有 CI 嗎?(github / gitlab / 沒有 → `none`,那就沒有 S12)| `ci` |
| 邊界 | 新型別的建構點該去哪些目錄找?(G7 可達性)| `reachability.globs` |
| | 資安基準與架構鐵則寫在哪個檔?| `rules_files` |

寫檔 → 跑 `scripts/gates/config-check` → PASS 才回報完成。

**注意**

- **沒填的鍵會讓對應關卡失敗,不是跳過。** 所以問卷不能跳過 `test` / `lint` / `smoke`。
- `ci: none` 是合法答案。`ci: github|gitlab` 時要**另外問**要不要把 `templates/ci/` 的範本裝進專案 ——
  改 CI 是人確認的事,不隨問卷自動做。
- 答錯了之後任何時候改 `specs/pipeline.yaml` 就好,不用重跑問卷。
