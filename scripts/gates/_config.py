"""機器可讀的技術棧綁定。

AGENTS.md 是寫給 AI 讀的散文;腳本需要真正的設定檔。
放在 <repo>/specs/pipeline.yaml,缺檔時用下面的預設值。

範例:
    runner: swift-testing          # red-capture 用哪個輸出解析器
    tests:
      globs:
        - "Packages/*/Tests/**/*.swift"
        - "AppTests/**/*.swift"
      scenario_pattern: '@Test\\("(SC-[\\w]+)'
    reachability:
      globs: ["App/**/*.swift"]    # G8 在哪裡找建構點
    lint: "swiftlint lint --quiet"     # 會把變更的檔案路徑接在後面
    test: "./scripts/verify.sh"        # 沒設定的話 G4 直接算失敗
    smoke: "./scripts/smoke.sh"        # 用真的入口跑一次、拿到真的結果;沒設定 = 失敗
    smoke_timeout: 600                 # 秒;超時算 hang
    smoke_max_s: null                  # 秒;整支 smoke 超過就 FAIL(效能最低保障)。不設 = 不檢查
    integration_branch: main           # scan-siblings / runs 判斷「已落地」的基準
    auto_push: true                    # 全綠且零待決事項 → 自動推功能分支 + 開 PR
    ci: none                           # none | github | gitlab;有 CI 才有 S12
    rules_files: [AGENTS.md]           # 資安基準與架構鐵則在哪;派給 code-adversary
    spec_lint:
      allow_vague: [works]             # 選填;領域名詞撞上 spec-lint 空話黑名單才列(只收黑名單裡有的字)
    risk_paths:                        # 必填。impact.files 命中任一類 → 強制 full 車道(改造方案 1.3)
      permissions: ["App/Info.plist", "App/*.entitlements"]
      privacy: ["src/recording/*"]     # fnmatch:* 會跨過 /,底下所有層都算
      payments: []                     # 六類都要寫,沒有就寫 []
      irreversible_data: ["src/migrations/*"]
      critical_security: ["src/auth/*", ".github/workflows/*"]
      core_entrypoint: ["src/main.ts"]
    models:                            # 選填。站 × 車道 → 模型(改造方案 2.1);沒寫的格子用 DEFAULTS
      S8: {lite: sonnet, full: opus}   # 值:模型名,或 {model: opus, effort: xhigh}
      S4: {full: [opus, sonnet]}       # S4 兩個讀者可以各給一個

以上每個鍵都可以用 /workflow:init 問卷一次填好。
"""

from __future__ import annotations

import pathlib
import re

DEFAULTS = {
    "runner": "swift-testing",
    "tests": {
        "globs": ["**/Tests/**/*", "**/*Tests/**/*"],
        # 慣例:測試的**描述字串**以 SC-id 開頭。
        # 預設綁 Swift Testing 的寫法;裸的 (SC-\d+) 會把註解裡的「// SC-002 另外處理」
        # 也當成測試(對抗審查實證),所以預設必須錨在測試宣告上,其他 stack 要自己設。
        "scenario_pattern": r'@Test\(\s*"(SC-\d+[a-z]?)',
    },
    # 沒設 = G7 失敗。預設 **/* 會把測試檔算成建構點,G7 就成了劇場(對抗審查實證,兩次)。
    "reachability": {"globs": None},
    # 兩個都預設 None。**沒設定 = 無法驗證 = 失敗**,不是「跳過」——
    # 「沒有人檢查」和「檢查通過」是兩件完全不同的事。
    "lint": None,
    "test": None,
    "smoke": None,
    "smoke_timeout": 600,
    "smoke_max_s": None,
    "integration_branch": "main",
    "auto_push": True,
    "ci": "none",
    "rules_files": ["AGENTS.md"],
    # 沒設 = 每張卡都 full(路徑複核做不了,不能當成「沒命中」)。config-check 也會 FAIL。
    "risk_paths": None,
    # 改造方案 2.1/2.2:每一站派哪個模型(站 × 車道),scripts/gates/dispatch 查這張表。
    # 沒列的車道 = 那個車道不派這一站。agents/*.md 的 frontmatter 只是沒經過 dispatch 直接派時的缺省。
    # 起始值是方案 2.2 的建議分配(chiao 決定一次全換;出事時一格一格退回去試,見 SKILL.md「模型與額度」)。
    "models": {
        "S3": {"lite": "opus", "full": "fable"},
        "S4": {"full": ["opus", "sonnet"]},
        "S7": {"lite": "sonnet", "full": "opus"},
        "S7½": {"full": "opus"},
        "S8": {"lite": "sonnet", "full": "sonnet"},
        "S9c": {"lite": "sonnet", "full": "sonnet"},
        "S12": {"lite": "sonnet", "full": "sonnet"},
        "G9": {"full": "opus"},
        "G10": {"lite": "fable", "full": "fable"},
        "G10-fix": {"lite": "opus", "full": "opus"},
    },
    # 測試裡「這一行是斷言」長什麼樣。test-review 用它抓空測試(零斷言)。
    "assert_pattern": r"#expect\(|#require\(|XCTAssert|assert(?:Equals|True|False|That|Throws)?\(|expect\(",
}

# 沒填就跑不了 pipeline 的鍵。/workflow:init 問卷與 config-check 都看這份。
REQUIRED = ["runner", "lint", "test", "smoke"]
PLACEHOLDER = re.compile(r"\{[A-Z_]+\}")


def missing(config: dict) -> list[str]:
    """哪些必填鍵還是空的或還是佔位符。"""
    out = []
    for key in REQUIRED:
        value = config.get(key)
        if value in (None, "") or (isinstance(value, str) and PLACEHOLDER.search(value)):
            out.append(key)
    for section in ("tests", "reachability"):
        globs = (config.get(section) or {}).get("globs")
        if not globs or any(PLACEHOLDER.search(str(g)) for g in globs):
            out.append(f"{section}.globs")
    return out


# 站 → 派哪個 agent。S9c 修 finding、S12 修 CI 紅,都是 green-writer。
STATION_AGENTS = {"S3": "spec-grill", "S4": "spec-reader", "S7": "red-writer", "S7½": "test-reviewer",
                  "S8": "green-writer", "S9c": "green-writer", "S12": "green-writer", "G9": "spec-oracle",
                  "G10": "code-adversary", "G10-fix": "fix-reviewer"}
MODEL_LADDER = ["haiku", "sonnet", "opus", "fable"]
ESCALATION_CAP = "opus"   # 連續失敗的升級最高到這裡(chiao 決定):Fable 額度只留給表上本來就用它的站
EFFORTS = {"low", "medium", "high", "xhigh", "max"}
OLD_MODEL_KEYS = {"draft", "review", "build"}   # 2.1 之前的格式,從沒有腳本讀過


def model_cell(config: dict, station: str, lane: str):
    """這一站在這個車道派什麼:專案 models 寫了那一格就用它,沒寫用 DEFAULTS;那個車道不派 → None。"""
    own = config.get("models")
    own = own.get(station) if isinstance(own, dict) else None
    if isinstance(own, dict) and lane in own:
        return own[lane]
    return DEFAULTS["models"].get(station, {}).get(lane)


def cell_problem(station: str, cell) -> str | None:
    """一格的值哪裡不對;沒問題回 None。"""
    if isinstance(cell, str):
        return None if cell in MODEL_LADDER else f"不認得的模型 {cell}"
    if isinstance(cell, dict):
        if set(cell) - {"model", "effort"}:
            return "只能寫 model、effort"
        if not isinstance(cell.get("model"), str) or cell["model"] not in MODEL_LADDER:
            return f"不認得的模型 {cell.get('model')}"
        if "effort" in cell and (not isinstance(cell["effort"], str) or cell["effort"] not in EFFORTS):
            return f"不認得的 effort {cell['effort']}"
        return None
    if isinstance(cell, list) and station == "S4":
        ok = len(cell) == 2 and all(isinstance(m, str) and m in MODEL_LADDER for m in cell)
        return None if ok else "要剛好兩個讀者、每個都是認得的模型"
    return "格式不對"


def models_problem(raw) -> str | None:
    """specs/pipeline.yaml 的 models 哪裡不對;沒寫或沒問題回 None。舊格式的鍵(draft/review/build)略過,另外提示。"""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        return "要寫成「站: {lite: 模型, full: 模型}」"
    bad = []
    for station, cells in raw.items():
        if station in OLD_MODEL_KEYS:
            continue
        if station not in STATION_AGENTS:
            bad.append(f"不認得的站 {station}")
        elif not isinstance(cells, dict) or not cells:
            bad.append(f"{station} 要寫成 {{lite: …, full: …}}")
        else:
            for lane_name, cell in cells.items():
                problem = "不認得的車道" if lane_name not in ("lite", "full") else cell_problem(station, cell)
                if problem:
                    bad.append(f"{station}.{lane_name} {problem}")
    return "、".join(bad) or None


def load(root: pathlib.Path) -> dict:
    import yaml

    path = root / "specs" / "pipeline.yaml"
    config = {k: (v.copy() if isinstance(v, dict) else v) for k, v in DEFAULTS.items()}
    if path.exists():
        loaded = yaml.safe_load(path.read_text()) or {}
        for key, value in loaded.items():
            if isinstance(value, dict) and isinstance(config.get(key), dict):
                config[key].update(value)
            else:
                config[key] = value
    return config
