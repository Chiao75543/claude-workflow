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
    integration_branch: main           # scan-siblings / runs 判斷「已落地」的基準
"""

from __future__ import annotations

import pathlib

DEFAULTS = {
    "runner": "swift-testing",
    "tests": {
        "globs": ["**/Tests/**/*", "**/*Tests/**/*"],
        # 慣例:測試的**描述字串**以 SC-id 開頭。
        # 預設綁 Swift Testing 的寫法;裸的 (SC-\d+) 會把註解裡的「// SC-002 另外處理」
        # 也當成測試(對抗審查實證),所以預設必須錨在測試宣告上,其他 stack 要自己設。
        "scenario_pattern": r'@Test\(\s*"(SC-\d+[a-z]?)',
    },
    "reachability": {"globs": ["**/*"]},
    # 兩個都預設 None。**沒設定 = 無法驗證 = 失敗**,不是「跳過」——
    # 「沒有人檢查」和「檢查通過」是兩件完全不同的事。
    "lint": None,
    "test": None,
    "integration_branch": "main",
}


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
