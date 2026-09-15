# Codex 精簡 Pipeline v1

這是 `claude-workflow` 同一個 repository 裡的 Codex profile，不是另一套 repository，也不取代既有 Claude workflow。

## 使用者看到的流程

1. 定方向
2. Codex 完成工作
3. 自動驗證
4. 使用者按 merge

快速與複雜／高風險需求都使用這四個 stage。差異只存在 stage 內：spec 有歧義或複雜度高才加入一位 spec-reader；權限、隱私、金流、不可逆資料操作／遷移、關鍵資安或核心入口才加入 spec-oracle。

## 元件邊界

- `profiles/codex-lean.yaml`：機器可讀的 stage、風險與中斷政策。
- `scripts/codex/route`：驗證 assessment 並 fail-closed 產生 quick/complex 路由。
- `skills/codex-workflow/`：Codex skill 發佈來源與 assessment template。
- `scripts/setup-codex.sh`：選配安裝；不修改原有 Claude setup。
- `scripts/gates/{scan-siblings,spec-lint,spec-diff,smoke}`：直接重用的共用核心。

## 快速開始

```bash
scripts/setup-codex.sh
cp skills/codex-workflow/assets/assessment.yaml /tmp/my-assessment.yaml
# 編輯 /tmp/my-assessment.yaml；所有 null 與空字串都必須換成實際盤點結果
scripts/codex/route /tmp/my-assessment.yaml
```

assessment template 預設會 fail closed，避免未盤點就被誤判成快速路徑。也可不安裝，
直接要求 Codex 讀取 `skills/codex-workflow/SKILL.md`。

## 明確限制與待接點

- v1 不執行 G8 mutation；profile 沒有真實 executor，所以只會明確顯示未宣稱通過。
- v1 不使用完整 `freeze-check`；它改用既有 `spec-diff` 鎖定核准的可見行為，避免 why、design、tasks 與檔案安排反覆要求批准。
- sibling `codex/workflow-autonomy` 的 `autonomy`、`evidence-check`、static-command RED 與 schema 還是 WIP。本版不修改、不複製也不吸收；待共用核心合併後再以 adapter 接入。
- Codex reader 在目前環境不等同 Claude `tools: []`；若沒有真正的工具隔離，不得聲稱結構性隔離。
