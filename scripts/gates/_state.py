"""工作樹指紋:證據「新不新鮮」的判準。

evidence/ 底下的檔案 AI 全都能寫,所以每份證據都要記下「當時工作樹長什麼樣」,
讀的時候比對 —— 對不上就是過期證據,不能拿來宣稱現在是綠的。

算法:用一個**臨時 index** 把工作樹內容(已追蹤 + 未追蹤、尊重 .gitignore)寫成 git tree,
tree hash 就是指紋。對抗審查實證了三個用 diff + ls-files 手刻的洞,這個做法一次解掉:
  · 未追蹤的非 ASCII 檔名(ls-files 會用引號+八進位輸出,路徑找不到就漏掉)
  · commit 之後指紋必變(HEAD 換了但內容沒動 —— 對非內容事件過敏)
  · `:(exclude)specs/*/evidence` 對已追蹤的 evidence 檔不生效(要 /**)
證據檔與命中率紀錄一律從 tree 裡拿掉:否則每跑一次關卡指紋就變,永遠「過期」。"""

from __future__ import annotations

import os
import pathlib
import subprocess
import tempfile

EXCLUDED = ["specs/*/evidence/**", "specs/_yield.jsonl"]


def tree_fingerprint(root: pathlib.Path) -> str:
    with tempfile.TemporaryDirectory() as td:
        env = {**os.environ, "GIT_INDEX_FILE": str(pathlib.Path(td) / "index")}

        def git(*args: str, allow_failure: bool = False) -> subprocess.CompletedProcess:
            try:
                result = subprocess.run(["git", *args], cwd=root, env=env, capture_output=True, text=True)
            except OSError as exc:
                raise RuntimeError(f"算不出工作樹指紋: git {args[0]}: {exc}") from exc
            if result.returncode != 0 and not allow_failure:
                detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
                raise RuntimeError(f"算不出工作樹指紋: git {args[0]}: {detail}")
            return result

        if git("rev-parse", "--verify", "-q", "HEAD", allow_failure=True).returncode == 0:
            git("read-tree", "HEAD")
        # 已追蹤的證據檔也要拿掉,不然它們留在 HEAD 的版本裡,commit 前後 tree 會不同
        git("rm", "-r", "-q", "--cached", "--ignore-unmatch", "--", *EXCLUDED)
        git("add", "-A", "--", ".", *[f":(exclude){p}" for p in EXCLUDED])
        tree = git("write-tree")
        return "tree:" + tree.stdout.strip()


def index_fingerprint(root: pathlib.Path) -> str:
    """實際 index candidate 的內容指紋，同樣排除 evidence。

    先讓真實 index 產生 tree，再在臨時 index 移除 evidence；不會改動使用者的 index。
    """
    try:
        candidate = subprocess.run(
            ["git", "write-tree"], cwd=root, capture_output=True, text=True
        )
    except OSError as exc:
        raise RuntimeError(f"算不出 index 指紋: git write-tree: {exc}") from exc
    if candidate.returncode != 0:
        detail = candidate.stderr.strip() or candidate.stdout.strip() or f"exit {candidate.returncode}"
        raise RuntimeError(f"算不出 index 指紋: git write-tree: {detail}")

    with tempfile.TemporaryDirectory() as td:
        env = {**os.environ, "GIT_INDEX_FILE": str(pathlib.Path(td) / "index")}

        def git(*args: str) -> subprocess.CompletedProcess:
            try:
                result = subprocess.run(["git", *args], cwd=root, env=env, capture_output=True, text=True)
            except OSError as exc:
                raise RuntimeError(f"算不出 index 指紋: git {args[0]}: {exc}") from exc
            if result.returncode != 0:
                detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
                raise RuntimeError(f"算不出 index 指紋: git {args[0]}: {detail}")
            return result

        git("read-tree", candidate.stdout.strip())
        git("rm", "-r", "-q", "--cached", "--ignore-unmatch", "--", *EXCLUDED)
        tree = git("write-tree")
        return "tree:" + tree.stdout.strip()
