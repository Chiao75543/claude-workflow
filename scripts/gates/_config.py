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
"""

from __future__ import annotations

import pathlib

DEFAULTS = {
    "runner": "swift-testing",
    "tests": {
        "globs": ["**/Tests/**/*", "**/*Tests/**/*"],
        # 慣例:測試的描述以 SC-id 開頭。任何框架都能命名測試,所以這條夠中立。
        "scenario_pattern": r"(SC-\d+[a-z]?)",
    },
    "reachability": {"globs": ["**/*"]},
    # 兩個都預設 None。**沒設定 = 無法驗證 = 失敗**,不是「跳過」——
    # 「沒有人檢查」和「檢查通過」是兩件完全不同的事。
    "lint": None,
    "test": None,
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
