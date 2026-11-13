"""驗證關卡共用模組。全部只用標準庫 + PyYAML。"""

from __future__ import annotations

import datetime
import fnmatch
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
# 旗標 S1 由 orchestrator 依描述推定(不問人),S3 再拿 impact.files 對 pipeline.yaml 的 risk_paths 複核,
# 兩者取較嚴的(改造方案 1.3)。路徑命中不能逐卡推翻:誤中就改 risk_paths,跟豁免一樣是修規則。
RISK_FLAGS = ["permissions", "privacy", "payments", "irreversible_data", "critical_security", "core_entrypoint"]
# lite 車道不要求的關:證明測試曾紅過(G5)、測試的語意審查(G2b 的 agent 半段)、
# 可達性(G7)、獨立第二讀者(G9)。G10 對抗審查兩條車道都要。
LITE_WAIVED_GATES = {"G5", "G7"}
# 車道豁免只能落在腳本關(幾乎免費的那些)。smoke(S)與付費審查(G9/10)永遠不在車道豁免範圍 ——
# 就算有人把它們加進上面那個集合也一樣。dashboard 用這份白名單再過濾一次。
WAIVABLE_GATES = {"G0", "G1/2", "G2b", "G3", "G4", "G5", "G6", "G7"}
# chiao 明確指示的豁免(loop waive,改造方案 1.6)只收 G9/10,而且只蓋「審查沒對到現在的樹」
# (過期、沒派、派遣紀錄無效),不蓋沒處理完的 finding —— 那些有 loop decided / findings set。
# 腳本關與 smoke 不收:誤擋就修關卡規則,不是豁免。歷史上豁免某一關的「代批」全落在 G9/10。
HUMAN_WAIVABLE_GATES = {"G9/10"}
# 原因類別是固定選項:runs --yield 依類別統計,才看得出是規則錯還是別的。
WAIVE_CATEGORIES = {
    "false-block": "誤擋 —— 關卡判錯了,該檢討的是規則",
    "tool-failure": "工具故障 —— 關卡跑不出結果(額度、服務、環境)",
    "accepted-risk": "接受風險 —— 沒審到的部分看過了,照現狀出貨",
    "out-of-scope": "原因在本卡之外 —— main 或別張卡帶進來的",
}


def lane(spec: dict, config: dict) -> str:
    """"lite" 或 "full"。旗標與路徑複核取較嚴的(改造方案 1.3):
    meta.risk_flags 缺、型別不對、任一非 False → full;risk_paths 沒設或格式不對 → full;
    impact.files 命中任一類 risk_paths → full。"""
    meta = spec.get("meta")
    flags = meta.get("risk_flags") if isinstance(meta, dict) else None
    if not isinstance(flags, dict) or any(flags.get(k) is not False for k in RISK_FLAGS):
        return "full"
    return "lite" if risk_hits(spec, config) == {} else "full"


def risk_paths_problem(config: dict) -> str | None:
    """specs/pipeline.yaml 的 risk_paths 哪裡不對;沒問題回 None。
    六類都要寫(沒有就寫 []),跟 risk_flags 一樣:寫一半會讓人以為已經評估過。"""
    rules = config.get("risk_paths")
    if rules is None:
        return "沒設"
    if not isinstance(rules, dict):
        return "必須是 mapping(六類各一個路徑樣式 list)"
    problems = []
    if missing := [k for k in RISK_FLAGS if k not in rules]:
        problems.append(f"缺 {', '.join(missing)}(沒有就寫 [])")
    if unknown := [k for k in rules if k not in RISK_FLAGS]:
        problems.append(f"不認得 {', '.join(map(str, unknown))}")
    if bad := [k for k in RISK_FLAGS if k in rules and not (
            isinstance(rules[k], list) and all(isinstance(g, str) and g.strip() for g in rules[k]))]:
        problems.append(f"{', '.join(bad)} 要是路徑樣式的 list")
    return "; ".join(problems) or None


def risk_hits(spec: dict, config: dict) -> dict[str, list[str]] | None:
    """impact.files 命中 risk_paths 的檔,依類別分;沒命中的類別不列。risk_paths 有問題 → None。
    樣式是 fnmatch:* 會跨過 /,所以 src/auth/* 涵蓋底下所有層。"""
    if risk_paths_problem(config):
        return None
    files = sorted(impact_files(spec))
    # impact.files 有人寫成「A + B」「路徑(說明)」:整條和空白切開的每一段都比,寧可多中
    hits = {flag: [p for p in files
                   if any(fnmatch.fnmatchcase(t, g) for t in {p, *p.split()} for g in config["risk_paths"][flag])]
            for flag in RISK_FLAGS}
    return {flag: paths for flag, paths in hits.items() if paths}


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


def impact_files(spec: dict) -> set[str]:
    """impact.files 的路徑;每條後面可以帶「  # 說明」。"""
    impact = spec.get("impact")
    files = (impact.get("files") or []) if isinstance(impact, dict) else []
    return {f for f in (entry.split("#")[0].strip() for entry in files if isinstance(entry, str)) if f}


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


FETCH_TIMEOUT = 30


def _git_out(root: pathlib.Path, *args: str) -> str | None:
    """git 的 stdout;失敗就是 None。"""
    try:
        proc = subprocess.run(["git", "-c", "core.quotePath=false", *args], cwd=root, capture_output=True, text=True)
    except OSError:
        return None
    return proc.stdout if proc.returncode == 0 else None


def fetch_integration(root: pathlib.Path) -> str | None:
    """判定落地前先把 origin 上的整合分支抓下來(worktree 共用 refs,抓一次就夠)。
    沒有 origin 就不抓;抓不到回傳警告,照用本機現有的 origin/<分支> —— 可能過期,所以要講。"""
    branch = integration_branch(root)
    if _git_out(root, "remote", "get-url", "origin") is None:
        return None
    try:
        proc = subprocess.run(["git", "fetch", "-q", "origin", f"+refs/heads/{branch}:refs/remotes/origin/{branch}"],
                              cwd=root, capture_output=True, text=True, timeout=FETCH_TIMEOUT,
                              env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    except (subprocess.TimeoutExpired, OSError) as exc:
        reason = f"{FETCH_TIMEOUT} 秒沒抓完" if isinstance(exc, subprocess.TimeoutExpired) else str(exc)
        return f"⚠ git fetch origin {branch} 失敗({reason})—— 用本機現有的 origin/{branch} 判斷,可能過期"
    if proc.returncode != 0:
        return f"⚠ git fetch origin {branch} 失敗({proc.stderr.strip()[:120]})—— 用本機現有的 origin/{branch} 判斷,可能過期"
    return None


def landing_ref(root: pathlib.Path, branch: str | None = None) -> str | None:
    """「落地」對照的 ref:merge 落在 remote 上,所以先看 origin/<整合分支>;沒有 remote 才用本機那條。
    本機的整合分支常落後(一個專案實測落後 26 個 commit),只看它會把已經 merge 的卡當成在飛。"""
    branch = branch or integration_branch(root)
    return next((ref for ref in (f"origin/{branch}", branch)
                 if _git_out(root, "rev-parse", "--verify", "-q", f"{ref}^{{commit}}") is not None), None)


def in_flight_specs(root: pathlib.Path, branch: str | None = None) -> list[pathlib.Path]:
    """這個 worktree **自己**還沒落地的規格(改造方案 1.7)。

    以前逐份比規格和整合分支上的內容。可是每個 worktree 都帶著所有卡的規格,
    開得早的 worktree 裡別張卡是舊版,對不上就被當成在飛(一個專案實測列出 205 個,實際十來個)。
    現在只看本卡自己的改動:整合分支的 merge-base → 工作樹動到的規格,含還沒 commit、還沒 add 的。
      · HEAD 已經在 origin/<整合分支> 裡 → merge-base 就是 HEAD,只剩還沒 commit 的改動
      · 剛開的 worktree 還沒 commit,HEAD 就是整合分支的尖端;只比祖先會把寫到一半的規格當成已落地
      · MODIFIED 的規格在整合分支上本來就有同一路徑,本卡改過它就在 diff 裡
    找不到整合分支、或算不出 merge-base(沒有 commit、歷史不相干)→ 全部當在飛:寧可多列,不要藏起來。"""
    specs = find_specs(root)
    own = own_changes(root, branch)
    if own is None:
        return specs
    return [path for path in specs if str(path.relative_to(root)) in own]


def own_changes(root: pathlib.Path, branch: str | None = None) -> set[str] | None:
    """本卡自己動過的 specs/ 底下的檔(相對 worktree 根):整合分支的 merge-base → 工作樹,含還沒 commit、還沒 add 的。
    找不到整合分支、或算不出 merge-base → None。"""
    ref = landing_ref(root, branch)
    mb = _git_out(root, "merge-base", "HEAD", ref) if ref else None
    if not mb:
        return None
    changed = _git_out(root, "diff", "--name-only", "--no-renames", mb.strip(), "--", "specs")
    untracked = _git_out(root, "ls-files", "--others", "--exclude-standard", "--", "specs")
    if changed is None or untracked is None:
        return None
    return set(changed.splitlines()) | set(untracked.splitlines())


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


def write_status(spec_path: pathlib.Path, stage: str, label: str, blocked_on: str | None) -> None:
    """status.json = 現在的狀態 + 追加式的 history。runs --set 與 dashboard 共用。

    history 只在「站」或「等誰」變了才追加一筆 —— dashboard 每跑一次都寫狀態,
    同一站反覆跑不該灌出一堆重複列。每站進出時間、等人佔比都從 history 算。
    status.json 在 evidence/ 底下,本來就在工作樹指紋之外(_state.EXCLUDED)。"""
    path = evidence_dir(spec_path) / "status.json"
    now = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    try:
        history = (read_json(path) or {}).get("history") or []
    except (ValueError, AttributeError):   # 壞掉的 status.json 不能讓 dashboard 在最後一步崩潰
        history = []
    last = history[-1] if history else {}
    if (last.get("stage"), last.get("blocked_on")) != (stage, blocked_on):
        history.append({"at": now, "stage": stage, "blocked_on": blocked_on})
    write_json(path, {"stage": stage, "label": label, "blocked_on": blocked_on,
                      "updated_at": now, "history": history})


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
