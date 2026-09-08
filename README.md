# claude-workflow

一條 spec-driven 的開發流水線,給 [Claude Code](https://claude.com/claude-code) 用。

**目標:你不再讀程式碼,但你知道它是對的 —— 因為每一句「這是對的」都得跑得出來。**

---

## 為什麼

程式和測試是**同一個模型、從同一份規格、用同一種理解**產生的。
所以「測試綠了」只證明它跟自己一致,不證明它是對的。

目前唯一站在這個圈外面的檢查,就是人去讀程式碼。

這條 pipeline 把每一個「AI 說 OK」換成「機器跑得出來」,讓人可以安全地從圈外走開。

### 四個洞與補法

| 洞 | 為什麼測試抓不到 | 補法 |
|---|---|---|
| **測試根本沒在測東西** | 斷言有回傳值就好、只把 mock 測了一遍 | 實作前先跑一次;**那時就綠的測試是假的** |
| **測試是照著程式改出來的** | 紅了改不過就把測試放寬 | 紅過就上鎖;要改是明確事件,退回重來 |
| **程式和測試一起誤讀規格** | 兩邊都以為是 A,規格講的是 B。全綠 | 第二個讀者,**只給規格不給程式碼** |
| **AI 說有 bug 但沒人能驗** | 只好丟給人判 | 要它把 bug **演出來**;演不出來自動作廢 |

---

## 人類只出現三次

```
S1  識別              scan-siblings:誰在飛、會不會撞到
S2  worktree
S3  起草              全 codebase scope audit + spec-grill(fable)
S4  歧義偵測          spec-reader ×2(fable,隔離,只看規格)
S5  ⏸ 你批准說明頁     白話 + 分歧選擇題 + N/A 主張 + 碰撞警告
S6  定稿凍結          spec-lint + 反向回譯 + 指紋
S7  測試 RED          stub-first → 格式化 → red-capture → 凍結測試
S8  實作 GREEN
S9  十二道關卡        八道腳本全綠,才啟動四道付費
S10 commit
S11 ⏸ 你看證據表按推   可達性排最前面,和嚴重度分開
S12 push + MR
S13 ⏸ 你按 merge
```

**沒有一次需要你讀程式碼。** 你判斷的是**意圖**(S5)和**證據**(S11)。

---

## 十二道關卡:順序就是花錢的順序

```
腳本判定 · 幾乎不花錢 · 全綠才啟動下半
  G0  spec-lint        schema + 完備性六類 + 可測性
  G1  freeze-check     規格指紋 + 可解析性
  G2  freeze-check     規格測試指紋
  G3  lint             只看變更的檔案
  G4  測試 + 專案自有的靜態檢查
  G5  red-capture      六類 failure_class + 三方對帳
  G6  traceability     Scenario ↔ 測試雙向
  G7  examples 覆蓋
  G8  可達性           新增的型別有沒有人建構它
────────────────────────────────────────────
付費判定
  G9   變異測試        有工具才跑
  G10  spec-oracle     隔離的第二讀者,只憑規格寫驗收測試
  G11  code-adversary  每條主張附可執行的重現
  G12  UI 截圖         有畫面變更才跑
```

**絕不花錢請 AI 去審一個腳本本來就會擋掉的東西。**

---

## 安裝

```bash
brew install --cask claude
brew install gh          # 或 glab
npm install -g @openai/codex   # 選配:跨引擎去相關性

git clone https://github.com/<you>/claude-workflow.git ~/code/claude-workflow
~/code/claude-workflow/scripts/setup.sh
```

`setup.sh` 會 symlink skill、slash commands、以及 `agents/` 底下的四個精簡 agent。
**agent 定義要重啟 Claude Code session 才會載入。**

### 每個專案

```bash
cp ~/code/claude-workflow/templates/project-AGENTS.md.template <repo>/AGENTS.md
~/code/claude-workflow/scripts/init-project.sh ios <repo>
```

會 scaffold 兩件事:

- `<repo>/.claude/skills/` —— 兩個專案自備的 skill(`test-writer`、`rd-implementer`)
- `<repo>/specs/pipeline.yaml` —— **機器可讀**的技術棧綁定,給關卡腳本用

兩層設定的分工:**AGENTS.md 是寫給 AI 讀的散文,`pipeline.yaml` 是給腳本讀的。**

---

## Slash commands

| 指令 | 做什麼 |
|---|---|
| `/workflow <描述>` | 完整流程 |
| `/workflow:spec` | 只寫規格,停在 S6 |
| `/workflow:test` | 寫測試並擷取 RED 證據 |
| `/workflow:implement` | 實作到全綠 |
| `/workflow:verify` | 跑十二道關卡 |
| `/workflow:dashboard` | 產出證據表 |
| `/workflow:runs` | 跨 worktree 看誰卡在哪、誰在等你 |
| `scripts/gates/runs --yield` | 哪道關擋過東西、擋了幾次;跑過 ≥5 次從沒擋過的會被點名 |

---

## 同時進行多個需求

**pipeline,不是 parallel。** 機器階段 30–60 分鐘、人類階段約 6 分鐘,比例 7:1 ——
所以要讓「你審 A 的說明頁時 B 正在跑建置」,而不是 N 個功能各自來打擾你。
實務建議同時 2–3 個。

一個功能一個 session、一個 worktree。**共享狀態放檔案系統,不需要協調者:**

```bash
scripts/gates/scan-siblings <spec>   # 能力清單 + impact.files 碰撞警告
scripts/gates/runs                   # 誰卡在哪、誰在等你
```

碰撞偵測在**寫程式之前**就把「這兩個分支都會動 MeView 和 AppContainer」講出來,
比合併時才發現便宜得多。

---

## 目錄

```
claude-workflow/
├── skills/workflow-orchestrator/
│   ├── SKILL.md                    ← 唯一的規範來源
│   ├── PIPELINE.md                 ← 入口(不是鏡像)
│   └── references/
│       ├── spec-template.yaml      通得過自己的 spec-lint
│       └── dispatch-prompts.md
├── agents/                          六個精簡定義
│   ├── spec-grill.md               fable · 挑洞,兼第一個讀者
│   ├── spec-reader.md              fable · 隔離,tools: []
│   ├── spec-oracle.md              fable · 隔離,tools: []
│   ├── code-adversary.md           fable · 有 Bash,要真的去跑重現
│   ├── red-writer.md               opus  · S7 寫測試並擷取 RED 證據
│   └── green-writer.md             opus  · S8 實作;「衝突就停」寫死在定義裡
├── scripts/
│   ├── gates/                       十二道關卡的實作
│   ├── setup.sh
│   └── init-project.sh
├── commands/                        slash commands
└── templates/
    ├── project-AGENTS.md.template
    └── skills/{android,ios}/        每個 stack 兩個:test-writer、rd-implementer
```

---

## 關卡腳本自己的測試

```bash
scripts/gates/tests/run
```

```bash
scripts/gates/tests/mutate     # 測試自己有沒有牙齒
```

**驗收標準是變異存活率,不是測試條數。**

`mutate` 把已知的破壞逐一注入關卡腳本,跑測試,看有沒有被抓到。
存活 = 那條防線目前是裝飾品。`--max-survivors N` 可以當 CI 門檻。

軌跡:對抗審查初測 **1/29 被殺(存活 97%)** → 現在 **54 條變異全被殺(存活 0%)**。

77 條測試,每一條都對應真實出過的錯,不是為了覆蓋率而寫:

- 完備性指向別的 Requirement 的 Scenario(挑洞者抓到的,linter 當時擋不住)
- 指紋一致但 YAML 載不進來(切片凍結了一個解析不了的規格)
- 參數化測試的 issue 行格式(錨點選錯把 4 條正常測試誤判成沒跑)
- 測試掛住導致後面靜默不執行(只解析結果會誤報成全過)
- 可達性搜尋外包給 `git grep -E`(POSIX ERE 不支援 `\b`,pattern 靜默匹配不到)

**一個反覆出現的失誤模式:用「本來就會通過」的案例去驗一個檢查。**
這在開發過程中出現四次 —— 用沒有測試檔的乾淨 struct 驗可達性、
用 `TBD` 驗中文佔位符偵測、斷言 `"mapping" in out` 卻被 YAML 錯誤訊息滿足、
斷言 `"error" in out` 卻被統計行滿足。每一次那個檢查都看起來有效,其實沒有。
`mutate` 存在的理由就是把「這條測試真的守著那個行為嗎」自動化,不靠自覺。

**門檻要照語言校。** 中文密度高,一句 33 個字的話低於拉丁文校出來的 40 字上限而漏過;
中文另設 20 字門檻,純 ASCII 無空白的 token(query 參數、識別字)則不受長度規則管。

**兩個方向都要測。** 可達性那條的假訊號是「全部誤報成到不了」——
只測「該擋有沒有擋」看不出來,要有「該過有沒有過」才抓得到。
反過來,存活的變異幾乎全是把某個 `f.error` 換成 `pass` ——
**沉默地放行**才是最危險的失效方向,而只驗「正常情況能不能過」對它毫無保護力。

## 核心原則

1. **證據** —— 每一句「這是對的」都要跑得出來。附不出重現就自動作廢,不需要人裁決。
2. **凍結** —— 規格批准後凍結,測試 RED 後凍結。要改是明確事件。
3. **成本** —— 腳本關卡全綠才啟動付費關卡。
4. **隔離** —— 獨立讀者看不到程式碼,那是它存在的全部理由。
5. **缺席** —— 「必須附重現」會低估缺席類問題,所以可達性是獨立的機械關卡。

---

## 這條線本身是怎麼驗證的

設計不是推理出來的。它在一個真實的 iOS 專案上跑完一個完整功能
(規格 → 59 條測試 → 實作 → 十二道關卡 → 證據表 → commit),
過程中撞出**九個設計缺陷**並全部修正,包括:

- 「實作前就綠 = 假測試」會誤判純值型別 → 改成書面豁免 + 機械條件
- `failure_class` 漏了「掛住」—— 它會讓後面的測試靜默不執行
- lint gate 要求整包乾淨,在有歷史債的 repo 上等於從第一天就失效
- 「必須附重現」低估缺席類問題 → 新增可達性關卡(已用變異驗證)
- **規格從來沒被機器讀過** —— 凍結了一個載不進來的 YAML,凍得很成功但毫無意義

最後一條是 `spec-lint` 第一次執行就抓到的。

---

## License

隨意取用。建議:對外分享用 MIT;自用可以不放 license。
