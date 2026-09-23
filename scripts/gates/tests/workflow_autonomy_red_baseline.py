#!/usr/bin/env python3
"""在核准的 pre-implementation production gates 上重播 workflow-autonomy RED。

這個 helper 不解析、改寫或合成 checker 結果；它只建立隔離 Git repo、以
git show 還原 baseline gates，執行目前 frozen-candidate checker，並逐 byte
轉送 stdout/stderr/exit。
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys
import tempfile
import hashlib


HERE = pathlib.Path(__file__).resolve().parent
SOURCE_ROOT = HERE.parents[2]
BASELINE_COMMIT = "0ce7886"
STUBS = HERE / "fixtures/workflow-autonomy-red-baseline"
RED_CAPTURE_SHA256 = "577b45672b0f161c24fdef2011795086453b817c467fd290bf57795f837aa70e"


def git(root: pathlib.Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, check=check)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="workflow-autonomy-red-baseline-") as td:
        replay = pathlib.Path(td) / "repo"
        shutil.copytree(
            SOURCE_ROOT / "scripts",
            replay / "scripts",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        shutil.copytree(SOURCE_ROOT / "specs", replay / "specs")

        baseline_paths = git(
            SOURCE_ROOT,
            "ls-tree",
            "-r",
            "--name-only",
            BASELINE_COMMIT,
            "scripts/gates",
        ).stdout.decode().splitlines()
        for rel in baseline_paths:
            if rel.startswith("scripts/gates/tests/"):
                continue
            payload = git(SOURCE_ROOT, "show", f"{BASELINE_COMMIT}:{rel}").stdout
            target = replay / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
            mode = git(SOURCE_ROOT, "ls-tree", BASELINE_COMMIT, rel).stdout.decode().split()[0]
            target.chmod(0o755 if mode == "100755" else 0o644)
        for name in ("autonomy", "evidence-check"):
            target = replay / "scripts/gates" / name
            shutil.copyfile(STUBS / name, target)
            target.chmod(0o755)
        restored_red_capture = replay / "scripts/gates/red-capture"
        if hashlib.sha256(restored_red_capture.read_bytes()).hexdigest() != RED_CAPTURE_SHA256:
            raise RuntimeError("baseline red-capture hash mismatch")

        git(replay, "init", "-q", ".")
        git(replay, "config", "user.email", "workflow-red-baseline@example.invalid")
        git(replay, "config", "user.name", "Workflow RED Baseline")
        git(replay, "add", "-A")
        git(replay, "commit", "-qm", "workflow autonomy RED baseline")
        git(replay, "branch", "-M", "main")

        checker = replay / "scripts/gates/tests/spec_workflow_autonomy.py"
        result = subprocess.run([sys.executable, str(checker), *sys.argv[1:]], cwd=replay, capture_output=True)
        sys.stdout.buffer.write(result.stdout)
        sys.stderr.buffer.write(result.stderr)
        return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
