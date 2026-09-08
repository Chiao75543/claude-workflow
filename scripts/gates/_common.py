"""驗證關卡共用模組。全部只用標準庫 + PyYAML。"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import subprocess
import sys

SCENARIO_ID = re.compile(r"^SC-\d+[a-z]?$")
REQUIREMENT_ID = re.compile(r"^REQ-\d+$")
NAME = re.compile(r"^[a-z0-9][a-z0-9-]*$")

COMPLETENESS_CATEGORIES = [
    "empty_boundary",
    "error_path",
    "concurrency",
    "illegal_state",
    "authorization",
    "data_migration",
]

MODES = {"6a", "6b", "6c", "6d"}


class Findings:
    """收集錯誤與警告,最後一次印出。錯誤讓退出碼非零。"""

    def __init__(self) -> None:
        self.errors: list[tuple[str, str]] = []
        self.warnings: list[tuple[str, str]] = []

    def error(self, where: str, message: str) -> None:
        self.errors.append((where, message))

    def warn(self, where: str, message: str) -> None:
        self.warnings.append((where, message))

    def report(self, title: str) -> int:
        width = max((len(w) for w, _ in self.errors + self.warnings), default=0)
        for where, message in self.errors:
            print(f"  ✘ {where.ljust(width)}  {message}")
        for where, message in self.warnings:
            print(f"  ⚠ {where.ljust(width)}  {message}")
        if self.errors:
            print(f"\n{title}: FAIL  ({len(self.errors)} 錯誤, {len(self.warnings)} 警告)")
            return 1
        print(f"{title}: PASS" + (f"  ({len(self.warnings)} 警告)" if self.warnings else ""))
        return 0


def load_spec(path: pathlib.Path) -> dict:
    import yaml  # 延後匯入:讓沒裝 pyyaml 的環境在這裡才報錯,訊息更清楚

    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        sys.exit(f"✘ 規格不是合法的 YAML: {path}\n{exc}")
    if not isinstance(data, dict):
        sys.exit(f"✘ 規格最外層必須是 mapping: {path}")
    return data


def sha256(path: pathlib.Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def scenarios(spec: dict):
    """走訪 (requirement, scenario),兩者都保證是 dict。"""
    for req in spec.get("requirements") or []:
        if not isinstance(req, dict):
            continue
        for sc in req.get("scenarios") or []:
            if isinstance(sc, dict):
                yield req, sc


def scenario_ids(spec: dict) -> set[str]:
    return {sc.get("id") for _, sc in scenarios(spec) if sc.get("id")}


def repo_root(start: pathlib.Path | None = None) -> pathlib.Path:
    """git worktree 的根。不在 git 裡就用當前目錄。"""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=start or pathlib.Path.cwd(),
            capture_output=True, text=True, check=True,
        )
        return pathlib.Path(out.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return pathlib.Path.cwd()


def sibling_worktrees(root: pathlib.Path) -> list[pathlib.Path]:
    """同一個 repo 的其他 worktree(不含自己)。B 模式的碰撞偵測靠這個。"""
    try:
        out = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            cwd=root, capture_output=True, text=True, check=True,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    paths = [pathlib.Path(line[9:]) for line in out.splitlines() if line.startswith("worktree ")]
    return [p for p in paths if p.resolve() != root.resolve() and p.exists()]


def landed(root: pathlib.Path, rel: str, branch: str = "main") -> bool:
    """規格是否已經在整合分支上。是的話它已經落地,不算在飛。

    B 模式下每個 worktree 都會 checkout 到 main 已有的規格,
    不濾掉的話已完成的功能會一直出現在「在飛」清單裡。"""
    try:
        return subprocess.run(
            ["git", "cat-file", "-e", f"{branch}:{rel}"],
            cwd=root, capture_output=True,
        ).returncode == 0
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def in_flight_specs(root: pathlib.Path, branch: str = "main") -> list[pathlib.Path]:
    """這個 worktree 裡尚未落地的規格。"""
    out = []
    for path in find_specs(root):
        rel = str(path.relative_to(root))
        if not landed(root, rel, branch):
            out.append(path)
    return out


def find_specs(root: pathlib.Path) -> list[pathlib.Path]:
    """一個 worktree 裡所有的規格檔。"""
    return sorted((root / "specs").glob("*/spec.yaml")) if (root / "specs").is_dir() else []


def evidence_dir(spec_path: pathlib.Path) -> pathlib.Path:
    return spec_path.parent / "evidence"


def write_json(path: pathlib.Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def read_json(path: pathlib.Path):
    return json.loads(path.read_text()) if path.exists() else None
