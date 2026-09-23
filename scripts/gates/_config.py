"""機器可讀的技術棧綁定。

AGENTS.md 是寫給 AI 讀的散文;腳本需要真正的設定檔。
放在 <repo>/specs/pipeline.yaml,缺檔時用下面的預設值。

範例:
    runner: swift-testing          # red-capture 用哪個輸出解析器
    tests:
      globs:
        - "Packages/*/Tests/**/*.swift"
        - "MindEYTests/**/*.swift"
      scenario_pattern: '@Test\\("(SC-[\\w]+)'
    reachability:
      globs: ["App/**/*.swift"]    # G8 在哪裡找建構點
    lint: "swiftlint lint --quiet"     # 會把變更的檔案路徑接在後面
    test: "./scripts/verify.sh"        # 沒設定的話 G4 直接算失敗
    smoke: "./scripts/smoke.sh"        # 用真的入口跑一次、拿到真的結果;沒設定 = 失敗
    smoke_timeout: 600                 # 秒;超時算 hang
    integration_branch: main           # scan-siblings / runs 判斷「已落地」的基準
    auto_push: true                    # 全綠且零待決事項 → 自動推功能分支 + 開 PR
    ci: none                           # none | github | gitlab;有 CI 才有 S12
    rules_files: [AGENTS.md]           # 資安基準與架構鐵則在哪;派給 code-adversary
    models: {draft: fable, review: fable, build: opus}

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
    "integration_branch": "main",
    "auto_push": True,
    "ci": "none",
    "rules_files": ["AGENTS.md"],
    "models": {"draft": "fable", "review": "fable", "build": "opus"},
    # 測試裡「這一行是斷言」長什麼樣。test-review 用它抓空測試(零斷言)。
    "assert_pattern": r"#expect\(|#require\(|XCTAssert|assert(?:Equals|True|False|That|Throws)?\(|expect\(",
}


def autonomy_version(config: dict) -> tuple[int | None, str | None, int]:
    """Return (effective version, rejection reason, exit code)."""
    value = config.get("autonomy", {"version": 0})
    if value is None or not isinstance(value, dict):
        return None, "invalid_autonomy_schema", 2
    version = value.get("version", 0)
    if isinstance(version, bool) or not isinstance(version, int):
        return None, "invalid_autonomy_schema", 2
    if version not in (0, 1):
        return version, "unsupported_autonomy_version", 1
    return version, None, 0

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
