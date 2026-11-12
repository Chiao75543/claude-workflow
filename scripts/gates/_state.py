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

import fnmatch
import hashlib
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


def _git(root: pathlib.Path, *args: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["git", "-c", "core.quotePath=false", *args], cwd=root, capture_output=True)
    except OSError as exc:
        raise RuntimeError(f"git {args[0]}: {exc}") from exc


def integration_refs(root: pathlib.Path, integration: str) -> list[str]:
    """本機與 origin 上的整合分支。併 main 常是併 origin/<分支>,本機那條可能落後,兩條都看。"""
    return [ref for ref in (integration, f"origin/{integration}")
            if _git(root, "rev-parse", "--verify", "-q", f"{ref}^{{commit}}").returncode == 0]


def branch_fingerprint(root: pathlib.Path, tree: str, integration: str) -> tuple[str, str]:
    """審查指紋:本卡自己的改動(整合分支的 merge-base → 工作樹)。回傳 (指紋, merge-base)。

    改造方案 1.2:併 main 不該讓審查過期,可是工作樹指紋算整棵樹,併 main 必然改變它。
    這個指紋只看本卡的 +/- 行:-U0 拿掉上下文,再去掉 index(blob hash)與 @@(行號)——
    main 改了同一個檔的別處、或在上面多插幾行,本卡的 +/- 行沒變,指紋就不變。
    只有衝突解決改到本卡的行、或 main 也做了一樣的改動,指紋才會變。
    用 plumbing(diff-tree)、core.quotePath 寫死:使用者的 diff 設定不影響輸出,本機和 CI 算得出同一個指紋。"""
    refs = integration_refs(root, integration)
    if not refs:
        raise RuntimeError(f"算不出本卡改動的指紋:找不到整合分支 {integration}")
    # 三個以上的參數 = HEAD 和「這幾條合起來」的 merge-base,也就是 HEAD 裡最新的那個整合分支 commit
    found = _git(root, "merge-base", "HEAD", *refs)
    if found.returncode != 0:
        raise RuntimeError(f"算不出本卡改動的指紋:git merge-base: {found.stderr.decode(errors='replace').strip()[:120]}")
    mb = found.stdout.decode().strip()
    diff = _git(root, "diff-tree", "-p", "-U0", "--no-renames", "--binary",
                mb, tree.removeprefix("tree:"), "--", ".", *[f":(exclude){p}" for p in EXCLUDED])
    if diff.returncode != 0:
        raise RuntimeError(f"算不出本卡改動的指紋:git diff-tree: {diff.stderr.decode(errors='replace').strip()[:120]}")
    body = [line for line in diff.stdout.split(b"\n") if not line.startswith((b"index ", b"@@ "))]
    return "diff:" + hashlib.sha256(b"\n".join(body)).hexdigest(), mb


def sync_merges(root: pathlib.Path, since_mb: str, integration: str) -> list[dict]:
    """since_mb(上次審查時的 merge-base)之後併進來的整合分支:HEAD first-parent 上的 merge,
    另一個 parent 是整合分支上、since_mb 還沒有的 commit。

    files = 衝突解決動到的檔(`git show --remerge-diff`:自動合併的結果 → 實際 commit 的版本,
    乾淨的合併是空的),排除 evidence。併進來的若是別的功能分支就不算 —— 那是本卡多了別人的改動。"""
    refs = integration_refs(root, integration)
    listed = _git(root, "rev-list", "--first-parent", "--merges", "--parents", "HEAD", f"^{since_mb}")
    if listed.returncode != 0:
        raise RuntimeError(f"git rev-list: {listed.stderr.decode(errors='replace').strip()[:120]}")
    found = []
    for line in listed.stdout.decode().splitlines():
        sha, _first, *others = line.split()
        if not any(_git(root, "merge-base", "--is-ancestor", p, since_mb).returncode != 0
                   and any(_git(root, "merge-base", "--is-ancestor", p, ref).returncode == 0 for ref in refs)
                   for p in others):
            continue
        shown = _git(root, "show", "--remerge-diff", "--format=", "--name-only", "-z", sha)
        when = _git(root, "show", "-s", "--format=%cI", sha)
        if shown.returncode != 0 or when.returncode != 0:
            raise RuntimeError(f"git show --remerge-diff {sha[:10]}(要 git 2.36 以上):"
                               f"{(shown.stderr or when.stderr).decode(errors='replace').strip()[:120]}")
        names = [f.strip() for f in shown.stdout.decode(errors="replace").split("\0") if f.strip()]
        files = [f for f in names if not any(fnmatch.fnmatch(f, p) for p in EXCLUDED)]
        found.append({"sha": sha, "at": when.stdout.decode().strip(), "files": files})
    return found

