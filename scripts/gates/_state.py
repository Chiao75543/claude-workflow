"""工作樹指紋:證據「新不新鮮」的判準。

evidence/ 底下的檔案 AI 全都能寫,所以每份證據都要記下「當時工作樹長什麼樣」,
讀的時候比對 —— 對不上就是過期證據,不能拿來宣稱現在是綠的。"""

from __future__ import annotations

import hashlib
import pathlib
import subprocess


def _git(root: pathlib.Path, *args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def tree_fingerprint(root: pathlib.Path) -> str:
    """HEAD + 未提交的變更(含未追蹤檔的內容)。任何一個檔案動了,指紋就變。"""
    h = hashlib.sha256()
    h.update(_git(root, "rev-parse", "HEAD").encode())
    # 證據檔與命中率紀錄本身不算工作樹的一部分 —— 否則每跑一次關卡指紋就變,永遠「過期」。
    h.update(_git(root, "diff", "HEAD", "--", ".", ":(exclude)specs/*/evidence",
                  ":(exclude)specs/_yield.jsonl").encode())
    for line in _git(root, "ls-files", "--others", "--exclude-standard").splitlines():
        if line.startswith("specs/") and ("/evidence/" in line or line == "specs/_yield.jsonl"):
            continue
        path = root / line
        if path.is_file():
            h.update(line.encode())
            h.update(path.read_bytes())
    return "sha256:" + h.hexdigest()
