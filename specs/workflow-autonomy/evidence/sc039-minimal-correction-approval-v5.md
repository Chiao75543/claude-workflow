# SC039 最小更正核准

- Owner 原文：`同意 SC039 最小更正`
- 核准時間：2026-09-15T15:03:09+08:00
- 範圍：補齊 smoke、G9/G10 dispatch、findings、dashboard 的 producer；將 delivery、status、dashboard 作為 snapshot direct roots，避免 dashboard hash 與 manifest 自我參照。
- 不變：evidence-check 維持唯讀；平台安全拒絕不得視為通過或改道重派；不自動 merge。
