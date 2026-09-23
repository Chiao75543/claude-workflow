# Pipeline

從一句需求到開好的 PR。**你固定出現兩次(批說明頁、按 merge),中間只在 PR 上有「需要你決定」時才叫你。
沒有一次需要讀程式碼。**

```
S0  第一次:問卷      技術棧 / 指令含 smoke / 主線與自動推 / CI / 邊界 / 模型 → specs/pipeline.yaml
S1  識別              scan-siblings:誰在飛、會不會撞
S2  worktree
S3  起草              全 codebase scope audit + spec-grill(fable)
S4  歧義偵測          spec-reader ×2(fable,隔離,只看規格)
S5  ⏸ 你批准說明頁    白話 + 分歧選擇題 + N/A 主張 + 碰撞警告
S6  定稿凍結          spec-lint + 反向回譯 + hash
S7  測試 RED          stub-first → 格式化 → red-capture
S7½ 審測試            test-review + test-reviewer(opus)→ 才凍結
S8  實作 GREEN        autonomy plan/complete/check + green-writer(opus):只做 examples 涵蓋的事
S9a 腳本關卡 G0–G7
S9b smoke             真的入口跑一次;沒過不派審查
S9c 付費審查 G9/G10   四類分流:must_fix / ask_user / overbuilt / style;loop 腳本數次數
S9d pre-commit 證據表  候選快照已 stage 才能 commit;絕不自動推
S10 commit
S10½ delivery 證據表   manifest/status/index/HEAD byte-exact，批准快照已 commit 才可推
S11 自動推 + 開 PR    證據表貼成留言;有「需要你決定」才叫你
S12 CI 獨立重跑       ci: none 就跳過;紅了 orchestrator 自己拉 log 修
S13 ⏸ 你按 merge
```

## 為什麼

程式和測試是**同一個模型、從同一份規格、用同一種理解**產生的。
「測試綠了」只證明它跟自己一致,不證明它是對的。
目前唯一站在這個圈外面的檢查,就是人去讀程式碼。

這條 pipeline 的目的是把每一個「AI 說 OK」換成「機器跑得出來」,
讓人可以安全地從圈外走開。

## 四個洞與補法

| 洞 | 補法 |
|---|---|
| 測試根本沒在測東西 | 實作前先跑一次;那時就綠的測試是假的 |
| 測試是照著程式改出來的 | 審過、紅過就上鎖;要改是明確事件,退回重來 |
| 程式和測試**一起**誤讀規格 | 第二個讀者,只給規格不給程式碼 |
| AI 說有 bug 但沒人能驗 | 要它把 bug 演出來;演不出來自動作廢 |

## 做到哪算夠

**你批准的那些 examples,一個字不多。** 例子外的實作叫多做(擋);例子外的問題不是 fix,
是問你「要不要防?」。這條也是審查迴圈會收斂的原因。

## 關卡:順序就是花錢的順序

腳本關卡 G0–G7 幾乎不花錢 → smoke 用真的入口跑一次 → **兩者都過才啟動**付費審查 G9/G10。
功能不對,其他免談。

G9/G10 完成後以 `findings <spec> dispatched --gate G9|G10 --status completed` 留證；平台拒絕則
保存 `--status denied` 並停止，不得改道重派。dashboard 寫自身 artifact 前用
`evidence-check <spec> --index|--commit --pre-dashboard` 驗其餘 roots，寫完後仍跑一般完整驗證。

## 完整規範

**`SKILL.md` 是唯一的規範來源。** 這份只是入口,不是鏡像。

`specs/pipeline.yaml` 缺少 `autonomy` 或為 `version: 0` 時完整保留舊九命令行為；只有 version 1
啟用 ledger CAS、static runner、嚴格 CLI/schema 與 delivery manifest verifier。
