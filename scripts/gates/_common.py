"""驗證關卡共用模組。全部只用標準庫 + PyYAML。"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import stat
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

# mode 不是單純的 schema 列舉,而是「哪個階段要收哪種證據」的契約。
# 6a/6b 在 S7 交 RED 與凍結證據;6c 到 S9b 由 build/smoke 實際驅動;
# 6d 只能人工驗收,不得被前兩種自動證據冒充。
RED_MODES = {"6a", "6b"}
SMOKE_MODES = {"6c"}
MANUAL_MODES = {"6d"}

# 兩條車道。實測 84 條 findings 有一半集中在兩張碰敏感東西的卡;其餘每張 1–9 條,
# 卻走一樣的十關。旗標沿用 profiles/codex-lean.yaml 的六個,任一為 true → full。
# 沒寫 risk_flags 的規格 **算 full**(fail closed):忘了填不能變成少過關。
RISK_FLAGS = ["permissions", "privacy", "payments", "irreversible_data", "critical_security", "core_entrypoint"]
# lite 車道不要求的關:證明測試曾紅過(G5)、測試的語意審查(G2b 的 agent 半段)、
# 可達性(G7)、獨立第二讀者(G9)。G10 對抗審查兩條車道都要。
LITE_WAIVED_GATES = {"G5", "G7"}
# 豁免只能落在腳本關(幾乎免費的那些)。smoke(S)與付費審查(G9/10)永遠不在豁免範圍 ——
# 就算有人把它們加進上面那個集合也一樣。dashboard 用這份白名單再過濾一次。
WAIVABLE_GATES = {"G0", "G1/2", "G2b", "G3", "G4", "G5", "G6", "G7"}


def lane(spec: dict) -> str:
    """"lite" 或 "full"。只看 meta.risk_flags;缺、型別不對、任一旗標非 False 都是 full。"""
    flags = (spec.get("meta") or {}).get("risk_flags")
    if not isinstance(flags, dict):
        return "full"
    if any(flags.get(k) is not False for k in RISK_FLAGS):
        return "full"
    return "lite"


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


def scenario_ids_for_modes(spec: dict, modes: set[str]) -> set[str]:
    """回傳指定驗證 mode 的 Scenario ids。未知 mode 不會落入任何集合。"""
    return {
        sc.get("id") for _, sc in scenarios(spec)
        if sc.get("id") and isinstance(sc.get("mode"), str) and sc.get("mode") in modes
    }


def invalid_scenario_modes(spec: dict) -> list[tuple[str, object]]:
    """列出未知/缺少 mode；各 gate 都要 fail closed，不能只依賴先跑 spec-lint。"""
    return [
        (str(sc.get("id") or "(無 id)"), sc.get("mode"))
        for _, sc in scenarios(spec)
        if not isinstance(sc.get("mode"), str) or sc.get("mode") not in MODES
    ]


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


def integration_branch(root: pathlib.Path) -> str:
    """整合分支名稱來自 specs/pipeline.yaml;沒設就用 main。
    寫死 main 的話,整合分支叫 develop 的專案永遠沒有規格會被判成已落地。"""
    try:
        import _config
        return str(_config.load(root).get("integration_branch") or "main")
    except Exception:  # noqa: BLE001
        return "main"


def landed(root: pathlib.Path, rel: str, branch: str | None = None) -> bool:
    """規格是否已經**以現在的內容**落在整合分支上。

    只查路徑存在是不夠的:MODIFIED 的規格在整合分支上本來就有同一路徑,
    只比存在會把它誤當已落地,碰撞偵測與狀態列表就都看不到它。
    所以比 blob hash —— 內容一模一樣才算落地。"""
    branch = branch or integration_branch(root)
    try:
        on_branch = subprocess.run(
            ["git", "rev-parse", f"{branch}:{rel}"],
            cwd=root, capture_output=True, text=True,
        )
        if on_branch.returncode != 0:
            return False
        local = subprocess.run(
            ["git", "hash-object", rel],
            cwd=root, capture_output=True, text=True, check=True,
        )
        return on_branch.stdout.strip() == local.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def in_flight_specs(root: pathlib.Path, branch: str | None = None) -> list[pathlib.Path]:
    """這個 worktree 裡尚未落地的規格。"""
    branch = branch or integration_branch(root)
    out = []
    for path in find_specs(root):
        rel = str(path.relative_to(root))
        if not landed(root, rel, branch):
            out.append(path)
    return out


def find_specs(root: pathlib.Path) -> list[pathlib.Path]:
    """一個 worktree 裡所有的規格檔。"""
    return sorted((root / "specs").glob("*/spec.yaml")) if (root / "specs").is_dir() else []


FINDING_DONE = {"void", "fixed", "accepted_risk", "added_example"}


def triage_findings(items: list) -> tuple[list, list]:
    """(還沒處理完的, 等人回答的)。findings check 與 dashboard 用同一份規則,才不會一邊算過一邊算沒過。

    「proposed」是還沒實跑重現 —— 不管哪一類(style 除外)都算沒處理完;
    對抗審查實證:ask_user 停在 proposed 時既不算 pending 也不算 asking,就這樣隱形了。"""
    pending, asking = [], []
    for i in items:
        if not isinstance(i, dict) or i.get("class") == "style":
            continue
        if i.get("status") == "proposed":
            pending.append(i)
        elif i.get("class") == "ask_user" and i.get("status") == "confirmed":
            asking.append(i)
        elif i.get("class") in ("must_fix", "overbuilt") and i.get("status") not in FINDING_DONE:
            pending.append(i)
    return pending, asking


def evidence_dir(spec_path: pathlib.Path) -> pathlib.Path:
    return spec_path.parent / "evidence"


def write_json(path: pathlib.Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def read_json(path: pathlib.Path):
    return json.loads(path.read_text()) if path.exists() else None


def _safe_read_repo_file(root: pathlib.Path, rel: str) -> tuple[bytes | None, str, str]:
    """Read a repo-relative regular file through anchored, no-follow dirfds.

    Returns (payload, status, detail), where status is ok/missing/error.  Walking
    each component with openat prevents a parent directory from being swapped to
    an external symlink between a containment check and the actual read.
    """
    rel_path = pathlib.Path(rel)
    if not rel or rel_path.is_absolute() or ".." in rel_path.parts:
        return None, "error", "路徑必須是 repo 內的相對路徑"
    nofollow = getattr(os, "O_NOFOLLOW", None)
    directory = getattr(os, "O_DIRECTORY", None)
    nonblock = getattr(os, "O_NONBLOCK", 0)
    if nofollow is None or directory is None:
        return None, "error", "平台不支援安全的 O_NOFOLLOW/O_DIRECTORY 讀取"

    current_fd = None
    file_fd = None
    try:
        current_fd = os.open(root, os.O_RDONLY | directory | nofollow)
        for part in rel_path.parts[:-1]:
            next_fd = os.open(part, os.O_RDONLY | directory | nofollow, dir_fd=current_fd)
            os.close(current_fd)
            current_fd = next_fd
        file_fd = os.open(rel_path.parts[-1], os.O_RDONLY | nofollow | nonblock, dir_fd=current_fd)
        info = os.fstat(file_fd)
        if not stat.S_ISREG(info.st_mode):
            return None, "error", "不是一般檔案"
        chunks = []
        while True:
            chunk = os.read(file_fd, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks), "ok", ""
    except FileNotFoundError as exc:
        return None, "missing", str(exc)
    except OSError as exc:
        return None, "error", str(exc)
    finally:
        if file_fd is not None:
            os.close(file_fd)
        if current_fd is not None:
            os.close(current_fd)


def spec_test_sources(root: pathlib.Path, spec_path: pathlib.Path, config: dict) -> tuple[list[dict], str, list[str]]:
    """Read the test files owned by one spec exactly once.

    Repository-wide globs are only a legacy discovery fallback.  Once RED inputs or
    a frozen tests.hash exists, those exact paths define this spec's review and
    traceability boundary; otherwise another spec reusing SC-001 can contaminate it.
    """
    ev = evidence_dir(spec_path)
    frozen = ev / "tests.hash"
    red_inputs = ev / "red-inputs.json"
    raw_paths: list[str] = []
    errors: list[str] = []
    root_resolved = root.resolve()
    frozen_rel = str(frozen.relative_to(root_resolved))
    red_inputs_rel = str(red_inputs.relative_to(root_resolved))
    frozen_payload, frozen_status, frozen_detail = _safe_read_repo_file(root_resolved, frozen_rel)

    if frozen_status != "missing":
        source = "evidence/tests.hash"
        if frozen_status == "error":
            errors.append(f"{source} 無法安全讀取: {frozen_detail}")
        else:
            try:
                lines = frozen_payload.decode().splitlines() if frozen_payload is not None else []
            except UnicodeDecodeError as exc:
                lines = []
                errors.append(f"{source} 無法讀取: {exc}")
            for line_no, line in enumerate(lines, 1):
                if not line.strip():
                    continue
                parts = line.split(None, 1)
                if len(parts) != 2 or not re.fullmatch(r"sha256:[0-9a-f]{64}", parts[0]):
                    errors.append(f"{source}:{line_no} 格式不合法")
                    continue
                raw_paths.append(parts[1].strip())
        if not raw_paths and not errors:
            errors.append(f"{source} 是空的，不能退回全域 globs")
    else:
        red_payload, red_status, red_detail = _safe_read_repo_file(root_resolved, red_inputs_rel)
        if red_status == "missing":
            red_payload = None
        source = "evidence/red-inputs.json"
        if red_status == "error":
            entries = None
            errors.append(f"{source} 無法安全讀取: {red_detail}")
        elif red_status == "ok":
            try:
                entries = json.loads(red_payload)
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                entries = None
                errors.append(f"{source} 無法讀取: {exc}")
        else:
            entries = None

    if frozen_status == "missing" and red_status != "missing":
        source = "evidence/red-inputs.json"
        if not isinstance(entries, list):
            if not errors:
                errors.append(f"{source} 最外層必須是 list")
        else:
            for index, entry in enumerate(entries, 1):
                tests = entry.get("tests") if isinstance(entry, dict) else None
                if (not isinstance(tests, list) or not tests
                        or not all(isinstance(rel, str) and rel.strip() for rel in tests)):
                    errors.append(f"{source} 第 {index} 筆 tests 必須是非空路徑 list")
                    continue
                raw_paths.extend(rel.strip() for rel in tests)
            if not raw_paths and not errors:
                errors.append(f"{source} 沒有任何測試路徑，不能退回全域 globs")
    elif frozen_status == "missing" and red_status == "missing":
        source = "pipeline tests.globs (legacy fallback)"
        for glob in config["tests"]["globs"]:
            for path in sorted(root.glob(glob)):
                if path.is_file():
                    raw_paths.append(str(path.relative_to(root)))

    sources = []
    seen_rel: set[str] = set()
    for rel in raw_paths:
        if rel in seen_rel:
            continue
        seen_rel.add(rel)
        payload, status, detail = _safe_read_repo_file(root_resolved, rel)
        if status != "ok" or payload is None:
            errors.append(f"{source} 測試檔無法安全讀取: {rel}: {detail}")
            continue
        sources.append({
            "path": root_resolved / rel,
            "rel": rel,
            "text": payload.decode(errors="ignore"),
            "sha256": "sha256:" + hashlib.sha256(payload).hexdigest(),
        })
    return sources, source, errors
