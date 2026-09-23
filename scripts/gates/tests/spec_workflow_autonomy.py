#!/usr/bin/env python3
"""workflow-autonomy v5 的逐 example 規格測試與 direct RED bootstrap。

每個 example 都在隔離的暫存 Git repository 準備輸入，並呼叫正式 gate CLI。
第一階段由尚未實作或尚未支援新契約的真實輸出形成 assertion RED；helper
crash、import/file missing 或 parser error 都不算 RED。

用法：
  python3 scripts/gates/tests/spec_workflow_autonomy.py
  python3 scripts/gates/tests/spec_workflow_autonomy.py --case SC-001 --example 1

退出碼：0 全部 projection 符合；1 至少一組 assertion 不符合；2 CLI 不合法。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from typing import Any


HERE = pathlib.Path(__file__).resolve().parent
SOURCE_ROOT = HERE.parents[2]
SOURCE_GATES = SOURCE_ROOT / "scripts" / "gates"
SPEC_REL = pathlib.Path("specs/workflow-autonomy/spec.yaml")
SCHEMA_DRAFT = "https://json-schema.org/draft/2020-12/schema"


def _schema_object(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "$schema": SCHEMA_DRAFT,
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def _nested_object(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    value = _schema_object(properties, required)
    value.pop("$schema")
    return value


STRING = {"type": "string"}
NONEMPTY_STRING = {"type": "string", "minLength": 1}
NULLABLE_STRING = {"oneOf": [NONEMPTY_STRING, {"type": "null"}]}
INTEGER = {"type": "integer", "minimum": 0}
BOOLEAN = {"type": "boolean"}
SHA256 = {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"}
GIT_OID = {"type": "string", "pattern": "^(?:[0-9a-f]{40}|[0-9a-f]{64})$"}
TREE_TOKEN = {"type": "string", "pattern": "^tree:(?:[0-9a-f]{40}|[0-9a-f]{64})$"}
RFC3339_SECONDS = {
    "type": "string",
    "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:Z|[+-][0-9]{2}:[0-9]{2})$",
}
NULLABLE_RFC3339_SECONDS = {"oneOf": [RFC3339_SECONDS, {"type": "null"}]}
REPO_PATH = {
    "type": "string",
    "pattern": "^(?!/)(?!.*(?:^|/)\\.\\.(?:/|$))(?!.*//)[^\\u0000\\r\\n]+$",
}
SCENARIO_ID = {"type": "string", "pattern": "^SC-[0-9]{3}[a-z]?$"}
POSIX_MODE_PATTERN = "^[0-7]{4}$"


EXPECTED_GATE_SCHEMAS: dict[str, dict[str, Any]] = {
    "config-check": _schema_object({
        "status": {"type": "string", "enum": ["passed", "rejected"]},
        "reason": NULLABLE_STRING,
        "effective_version": {"type": "integer", "enum": [0, 1]},
        "legacy_behavior_preserved": BOOLEAN,
        "models": _nested_object({"draft": NONEMPTY_STRING, "review": NONEMPTY_STRING, "build": NONEMPTY_STRING},
                                  ["draft", "review", "build"]),
        "exit_code": {"type": "integer", "enum": [0, 1, 2]},
    }, ["status", "reason", "effective_version", "legacy_behavior_preserved", "models", "exit_code"]),
    "autonomy": _schema_object({
        "schema_version": {"type": "integer", "enum": [1]},
        "operation": {"type": "string", "enum": ["plan", "complete", "verify-tests", "check", "invalid"]},
        "status": {"type": "string", "enum": ["planned", "complete", "passed", "blocked", "rejected", "conflict"]},
        "reason": NULLABLE_STRING,
        "generation": INTEGER,
        "expected_generation": {"oneOf": [INTEGER, {"type": "null"}]},
        "actual_generation": INTEGER,
        "may_continue": BOOLEAN,
        "written": BOOLEAN,
        "evidence_saved": {"oneOf": [{"type": "boolean"}, {"type": "null"}]},
        "test_contract_rebuilt": {"oneOf": [{"type": "boolean"}, {"type": "null"}]},
        "idempotent": BOOLEAN,
        "blocked_on": {"oneOf": [
            {"type": "string", "enum": ["owner", "permission", "platform", "gate"]},
            {"type": "null"},
        ]},
        "bypass_attempted": BOOLEAN,
        "required_action": {"oneOf": [
            {"type": "string", "enum": ["verify_tests"]},
            {"type": "null"},
        ]},
        "repair": {"oneOf": [{"type": "null"}, _nested_object({
            "id": NONEMPTY_STRING,
            "kind": {"type": "string", "enum": [
                "review_fix", "implementation", "evidence", "format", "frozen_test", "product_change", "permission"
            ]},
            "status": {"type": "string", "enum": ["planned", "complete", "blocked", "rejected"]},
            "files": {"type": "array", "items": REPO_PATH, "uniqueItems": True},
            "evidence": {"type": "array", "items": _nested_object({
                "path": REPO_PATH, "sha256": SHA256, "bytes": INTEGER,
                "tree_token": TREE_TOKEN,
            }, ["path", "sha256", "bytes", "tree_token"])},
            "spec_hash": SHA256,
            "scope_sources": {"type": "array", "items": _nested_object({
                "path": REPO_PATH,
                "source": {"type": "string", "enum": ["impact", "test_glob", "evidence"]},
            }, ["path", "source"])},
            "reason": NULLABLE_STRING,
            "plan_version": SHA256,
            "baseline_entries": {"type": "array", "items": _nested_object({
                "path": REPO_PATH, "mode": {"type": "string", "pattern": POSIX_MODE_PATTERN},
                "sha256": SHA256,
            }, ["path", "mode", "sha256"])},
            "baseline_worktree_token": SHA256,
            "blocked_on": {"oneOf": [
                {"type": "string", "enum": ["owner", "permission", "platform", "gate"]},
                {"type": "null"},
            ]},
            "planned_at": RFC3339_SECONDS,
            "completed_at": NULLABLE_RFC3339_SECONDS,
        }, ["id", "kind", "status", "files", "evidence", "spec_hash", "scope_sources",
            "reason", "plan_version", "baseline_entries", "baseline_worktree_token",
            "blocked_on", "planned_at", "completed_at"])]},
        "exit_code": {"type": "integer", "enum": [0, 1, 2]},
    }, ["schema_version", "operation", "status", "reason", "generation", "actual_generation",
        "expected_generation", "repair", "may_continue", "written", "evidence_saved",
        "test_contract_rebuilt", "idempotent", "blocked_on", "bypass_attempted",
        "required_action", "exit_code"]),
    "evidence-check": _schema_object({
        "schema_version": {"type": "integer", "enum": [1]},
        "status": {"type": "string", "enum": ["passed", "failed", "rejected"]},
        "reason": NULLABLE_STRING,
        "storage": {"type": "string", "enum": ["index", "commit", "unknown"]},
        "snapshot": {"oneOf": [GIT_OID, {"type": "null"}]},
        "token": {"oneOf": [SHA256, {"type": "null"}]},
        "files": {"type": "array", "items": _nested_object({
            "path": REPO_PATH, "sha256": SHA256, "source": {"type": "string", "enum": [
                "spec", "approval", "freeze", "red", "review", "smoke", "finding", "autonomy", "dashboard"
            ]}, "bytes": INTEGER,
        }, ["path", "sha256", "source", "bytes"])},
        "invalid_files": {"type": "array", "items": _nested_object({
            "path": REPO_PATH, "reason": {"type": "string", "enum": [
                "outside_repo", "symlink_or_nonregular", "missing", "empty",
                "snapshot_mismatch", "hash_mismatch"
            ]},
        }, ["path", "reason"])},
        "delivery_ready": BOOLEAN,
        "exit_code": {"type": "integer", "enum": [0, 1, 2]},
    }, ["schema_version", "status", "reason", "storage", "snapshot", "token",
        "files", "invalid_files", "delivery_ready", "exit_code"]),
    "runs": _schema_object({
        "schema_version": {"type": "integer", "enum": [1]},
        "status": {"type": "string", "enum": ["updated", "rejected", "conflict"]},
        "reason": NULLABLE_STRING,
        "generation": INTEGER,
        "pipeline_state": {"type": "string", "enum": ["running", "waiting", "blocked", "complete"]},
        "stage": {"oneOf": [
            {"type": "string", "enum": [f"S{i}" for i in range(11)]},
            {"type": "null"},
        ]},
        "next_step": {"oneOf": [
            {"type": "string", "minLength": 1, "pattern": "^[^\\r\\n]+$"},
            {"type": "null"},
        ]},
        "blocked_on": {"oneOf": [
            {"type": "string", "enum": ["owner", "permission", "platform", "gate"]},
            {"type": "null"},
        ]},
        "delivery": _nested_object({
            "state": {"type": "string", "enum": ["local", "committed", "pr_open", "merged"]},
            "ref": NULLABLE_STRING,
            "validation": {"oneOf": [
                _nested_object({"snapshot": GIT_OID, "token": SHA256}, ["snapshot", "token"]),
                {"type": "null"},
            ]},
        }, ["state", "ref", "validation"]),
        "report": _nested_object({
            "state": {"type": "string", "enum": ["pending", "sent", "denied"]},
            "reason": NULLABLE_STRING,
        }, ["state", "reason"]),
        "written": BOOLEAN,
        "owner_merge_required": BOOLEAN,
        "retry_via_other_channel": BOOLEAN,
        "updated_at": NULLABLE_RFC3339_SECONDS,
        "expected_generation": {"oneOf": [INTEGER, {"type": "null"}]},
        "actual_generation": INTEGER,
        "exit_code": {"type": "integer", "enum": [0, 1, 2]},
    }, ["schema_version", "status", "reason", "generation", "pipeline_state", "stage",
        "next_step", "blocked_on", "delivery", "report", "written",
        "owner_merge_required", "retry_via_other_channel", "updated_at",
        "expected_generation", "actual_generation", "exit_code"]),
    "red-capture": _schema_object({
        "schema_version": {"type": "integer", "enum": [1]},
        "spec_hash": SHA256,
        "generated_at": RFC3339_SECONDS,
        "runner": {"type": "string", "enum": ["static-command", "swift-testing"]},
        "marker": STRING,
        "exemptions": _nested_object({
            "SC-035": STRING,
            "SC-046": STRING,
        }, ["SC-035", "SC-046"]),
        "required_modes": {"type": "array", "items": {"type": "string", "enum": ["6a", "6b"]}},
        "deferred_smoke": {"type": "array", "items": STRING},
        "manual": {"type": "array", "items": STRING},
        "reconciliation": {"type": "array", "items": _nested_object({
            "layer": STRING, "declared_in_source": INTEGER, "reported_by_runner": INTEGER,
            "started": INTEGER, "reconciled": BOOLEAN,
        }, ["layer", "declared_in_source", "reported_by_runner", "started", "reconciled"])},
        "counts": _nested_object({
            "assertion": INTEGER, "exempt": INTEGER, "passed": INTEGER, "error": INTEGER,
            "hang": INTEGER, "compile": INTEGER, "stub_sentinel": INTEGER,
        }, ["assertion", "exempt", "passed", "error", "hang", "compile", "stub_sentinel"]),
        "tests": {"type": "array", "items": _nested_object({
            "layer": STRING,
            "scenario": NULLABLE_STRING,
            "test": STRING,
            "failure_class": {"type": "string", "enum": [
                "assertion", "exempt", "passed", "error", "hang", "compile", "stub_sentinel"
            ]},
            "message": NULLABLE_STRING,
            "red_valid": BOOLEAN,
            "legacy_parser_used": BOOLEAN,
            "behavior_preserved": BOOLEAN,
        }, ["layer", "scenario", "test", "failure_class", "message", "red_valid",
            "legacy_parser_used", "behavior_preserved"])},
        "status": {"type": "string", "enum": ["passed", "failed", "rejected"]},
        "reason": NULLABLE_STRING,
        "failure_class": {"oneOf": [
            {"type": "string", "enum": ["assertion", "passed", "error", "hang", "exempt"]},
            {"type": "null"},
        ]},
        "red_valid": BOOLEAN,
        "reused_frozen_red": BOOLEAN,
        "runner_results": {"type": "array", "items": _nested_object({
            "schema_version": {"type": "integer", "enum": [1]},
            "layer": NONEMPTY_STRING, "scenario": SCENARIO_ID,
            "example": {"type": "integer", "minimum": 1},
            "argv": {"type": "array", "items": NONEMPTY_STRING, "minItems": 1},
            "timeout_seconds": {"type": "integer", "minimum": 1},
            "exit_code": {"oneOf": [INTEGER, {"type": "null"}]},
            "failure_class": {"type": "string", "enum": ["assertion", "passed", "error", "hang", "exempt"]},
            "red_valid": BOOLEAN, "stdout_path": NULLABLE_STRING, "stderr_path": NULLABLE_STRING,
            "stdout_sha256": SHA256, "stderr_sha256": SHA256,
            "marker_lines": {"type": "array", "items": {
                "type": "string", "pattern": "^STATIC_ASSERTION:"
            }},
            "started_at": RFC3339_SECONDS, "finished_at": RFC3339_SECONDS,
            "tree_token": TREE_TOKEN,
        }, ["schema_version", "layer", "scenario", "example", "argv", "timeout_seconds",
            "exit_code", "failure_class", "red_valid", "stdout_path", "stderr_path",
            "stdout_sha256", "stderr_sha256", "marker_lines", "started_at", "finished_at",
            "tree_token"])},
        "gate_exit_code": {"type": "integer", "enum": [0, 1, 2]},
    }, ["schema_version", "spec_hash", "generated_at", "runner", "marker", "exemptions",
        "required_modes", "deferred_smoke", "manual", "reconciliation", "counts", "tests",
        "runner_results", "status", "reason", "failure_class", "red_valid",
        "reused_frozen_red", "gate_exit_code"]),
    "test-review": _schema_object({
        "schema_version": {"type": "integer", "enum": [1]},
        "status": {"type": "string", "enum": ["passed", "failed", "rejected"]},
        "reason": NULLABLE_STRING,
        "ok": BOOLEAN,
        "mechanical_only": BOOLEAN,
        "at": RFC3339_SECONDS,
        "tests": INTEGER,
        "scope_source": NONEMPTY_STRING,
        "reviewed_modes": {"type": "array", "items": {"type": "string", "enum": ["6a", "6b"]}},
        "deferred_smoke": {"type": "array", "items": STRING},
        "files": {
            "type": "object",
            "patternProperties": {REPO_PATH["pattern"]: SHA256},
            "additionalProperties": False,
        },
        "tree": TREE_TOKEN,
        "errors": {"type": "array", "items": STRING},
        "warnings": {"type": "array", "items": STRING},
        "agent": {"oneOf": [{"type": "null"}, _nested_object({
            "schema_version": {"type": "integer", "enum": [1]},
            "writer_task_ref": NONEMPTY_STRING, "reviewer_task_ref": NONEMPTY_STRING,
            "completion_ref": NONEMPTY_STRING, "tree_token": TREE_TOKEN,
            "created_at": RFC3339_SECONDS,
            "status": {"type": "string", "enum": ["passed", "blocking"]},
            "findings": {"type": "array", "items": _nested_object({
                "test": NONEMPTY_STRING, "sc": SCENARIO_ID,
                "problem": NONEMPTY_STRING, "blocking": BOOLEAN,
            }, ["test", "sc", "problem", "blocking"])},
            "before_tests": {"type": "array", "items": _nested_object(
                {"path": REPO_PATH, "sha256": SHA256}, ["path", "sha256"])},
            "after_tests": {"type": "array", "items": _nested_object(
                {"path": REPO_PATH, "sha256": SHA256}, ["path", "sha256"])},
            "assertion_weakened": BOOLEAN,
            "reviewed_examples": {"type": "array", "items": _nested_object({
                "scenario": SCENARIO_ID,
                "examples": {"type": "array", "items": {"type": "integer", "minimum": 1}, "minItems": 1},
            }, ["scenario", "examples"])},
        }, ["schema_version", "writer_task_ref", "reviewer_task_ref", "completion_ref",
            "tree_token", "created_at", "status", "findings", "before_tests", "after_tests",
            "assertion_weakened", "reviewed_examples"])]},
        "before_tests": {"type": "array", "items": _nested_object(
            {"path": REPO_PATH, "sha256": SHA256}, ["path", "sha256"])},
        "after_tests": {"type": "array", "items": _nested_object(
            {"path": REPO_PATH, "sha256": SHA256}, ["path", "sha256"])},
        "assertion_weakened": BOOLEAN,
        "reviewed_examples": {"type": "array", "items": _nested_object({
            "scenario": SCENARIO_ID,
            "examples": {"type": "array", "items": {"type": "integer", "minimum": 1}, "minItems": 1},
        }, ["scenario", "examples"])},
        "review_token": {"oneOf": [SHA256, {"type": "null"}]},
        "reviewed_at": RFC3339_SECONDS,
        "exit_code": {"type": "integer", "enum": [0, 1, 2]},
    }, ["schema_version", "status", "reason", "ok", "mechanical_only", "at", "tests",
        "scope_source", "reviewed_modes", "deferred_smoke", "files", "tree", "errors",
        "warnings", "agent", "before_tests", "after_tests", "assertion_weakened",
        "reviewed_examples", "review_token", "reviewed_at", "exit_code"]),
    "traceability": _schema_object({
        "status": {"type": "string", "enum": ["passed", "failed", "rejected"]},
        "reason": NULLABLE_STRING,
        "scenario_count": INTEGER,
        "red_required_count": INTEGER,
        "deferred_smoke_count": INTEGER,
        "manual_count": INTEGER,
        "covered_count": INTEGER,
        "scope_source": STRING,
        "test_files": {"type": "array", "items": STRING},
        "missing_scenarios": {"type": "array", "items": STRING},
        "orphan_scenarios": {"type": "array", "items": STRING},
        "exit_code": {"type": "integer", "enum": [0, 1, 2]},
    }, ["status", "reason", "scenario_count", "red_required_count",
        "deferred_smoke_count", "manual_count", "covered_count", "scope_source",
        "test_files", "missing_scenarios", "orphan_scenarios", "exit_code"]),
    "freeze-check": _schema_object({
        "status": {"type": "string", "enum": ["passed", "failed", "rejected"]},
        "reason": NULLABLE_STRING,
        "exit_code": {"type": "integer", "enum": [0, 1, 2]},
    }, ["status", "reason", "exit_code"]),
    "findings": _schema_object({
        "status": {"type": "string", "enum": ["added", "rejected", "failed", "fixed", "flipflop"]},
        "reason": NULLABLE_STRING,
        "id": NULLABLE_STRING,
        "identity": NULLABLE_STRING,
        "canonical_id": NULLABLE_STRING,
        "existing_finding_preserved": BOOLEAN,
        "fixes_preserved": BOOLEAN,
        "finding_id_reused": BOOLEAN,
        "action": {"oneOf": [
            {"type": "string", "enum": ["preserve", "reappear"]},
            {"type": "null"},
        ]},
        "result": {"oneOf": [
            {"type": "string", "enum": ["flipflop"]},
            {"type": "null"},
        ]},
        "fixes": INTEGER,
        "required_action": {"oneOf": [
            {"type": "string", "enum": ["full_rerun"]},
            {"type": "null"},
        ]},
        "gates": {"type": "array", "items": STRING},
        "may_claim_pass": BOOLEAN,
        "written": BOOLEAN,
        "invalid_files": {"type": "array", "items": _nested_object(
            {"path": STRING, "reason": {"type": "string", "enum": [
                "outside_repo", "missing", "hash_mismatch", "symlink_or_nonregular", "snapshot_mismatch"
            ]}}, ["path", "reason"])},
        "exit_code": {"type": "integer", "enum": [0, 1, 2]},
    }, ["status", "reason", "id", "identity", "canonical_id",
        "existing_finding_preserved", "fixes_preserved", "finding_id_reused",
        "action", "result", "fixes", "required_action", "gates", "may_claim_pass",
        "written", "invalid_files", "exit_code"]),
    "loop": _schema_object({
        "status": {"type": "string", "enum": ["passed", "blocked", "parked", "flipflop", "rejected"]},
        "reason": NULLABLE_STRING,
        "id": NULLABLE_STRING,
        "gate": NULLABLE_STRING,
        "fixes": INTEGER,
        "prior_redispatches": INTEGER,
        "owner_decision_required": BOOLEAN,
        "written": BOOLEAN,
        "exit_code": {"type": "integer", "enum": [0, 1, 2]},
    }, ["status", "reason", "id", "gate", "fixes", "prior_redispatches",
        "owner_decision_required", "written", "exit_code"]),
    "dashboard": _schema_object({
        "name": STRING,
        "branch": STRING,
        "scale": STRING,
        "phase": {"type": "string", "enum": ["pre-commit", "delivery"]},
        "approval_anchor": {"type": "string", "enum": [
            "committed", "pending_commit", "missing", "mismatch", "git_error"
        ]},
        "gates": {"type": "array", "items": _nested_object({
            "id": STRING, "what": STRING, "ok": BOOLEAN, "note": STRING,
        }, ["id", "what", "ok", "note"])},
        "attention": {"type": "array", "items": _nested_object({
            "tag": STRING, "title": STRING, "body": STRING, "decision": BOOLEAN,
        }, ["tag", "title", "body", "decision"])},
        "screenshots": {"type": "array", "items": STRING},
        "auto_push_ok": BOOLEAN,
        "exit_code": {"type": "integer", "enum": [0, 1]},
    }, ["name", "branch", "scale", "phase", "approval_anchor", "gates",
        "attention", "screenshots", "auto_push_ok", "exit_code"]),
    "pr-comment": _schema_object({
        "status": {"type": "string", "enum": ["passed", "blocked", "rejected"]},
        "reason": NULLABLE_STRING,
        "title": STRING,
        "markdown": STRING,
        "decisions": {"type": "array", "items": STRING},
        "auto_push_ok": BOOLEAN,
        "exit_code": {"type": "integer", "enum": [0, 1, 2]},
    }, ["status", "reason", "title", "markdown", "decisions", "auto_push_ok", "exit_code"]),
}


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _write_json(path: pathlib.Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _git(root: pathlib.Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True)


def _new_repo(base: pathlib.Path) -> pathlib.Path:
    root = base / "repo"
    shutil.copytree(
        SOURCE_ROOT / "scripts",
        root / "scripts",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    shutil.copytree(SOURCE_ROOT / "specs", root / "specs")
    _git(root, "init", "-q", ".")
    _git(root, "config", "user.email", "workflow-autonomy@example.invalid")
    _git(root, "config", "user.name", "Workflow Autonomy Fixture")
    return root


def _commit(root: pathlib.Path, message: str = "fixture") -> None:
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", message)
    _git(root, "branch", "-M", "main")


def _parse_json_output(proc: subprocess.CompletedProcess[str], exit_key: str = "exit_code") -> dict[str, Any]:
    payload: dict[str, Any] | None = None
    for line in reversed(proc.stdout.splitlines()):
        try:
            candidate = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict):
            payload = candidate
            break
    if payload is None:
        payload = {"stdout": proc.stdout, "stderr": proc.stderr}
    if exit_key in payload:
        payload["reported_exit_code"] = payload[exit_key]
    payload[exit_key] = proc.returncode
    return payload


def _gate_succeeded(item: dict[str, Any], exit_key: str = "exit_code") -> bool:
    """Sequence oracle：process 與 JSON 自報 exit 必須同為零且一致。"""
    process_exit = item.get(exit_key)
    reported_exit = item.get("reported_exit_code", process_exit)
    return process_exit == 0 and reported_exit == process_exit


def _run(root: pathlib.Path, script: str, *args: str, timeout: int = 20,
         exit_key: str = "exit_code") -> dict[str, Any]:
    try:
        proc = subprocess.run(
            [str(root / "scripts" / "gates" / script), *args],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            exit_key: 1,
            "timed_out": True,
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
        }
    return _parse_json_output(proc, exit_key)


def _run_with_index_drift(root: pathlib.Path, rel: str, script: str, *args: str) -> dict[str, Any]:
    """在 CLI 裁決期間修改並 stage 受檢檔案，使 index tree 真正改變。"""
    before_tree = _git(root, "write-tree").stdout.strip()
    errors: list[BaseException] = []
    proc = subprocess.Popen(
        [str(root / "scripts" / "gates" / script), *args],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    target = root / rel

    def mutate() -> None:
        try:
            generation = 0
            while proc.poll() is None:
                generation += 1
                target.write_text(f"indexed evidence generation {generation}\n")
                subprocess.run(["git", "add", "--", rel], cwd=root, check=True, capture_output=True)
                time.sleep(0.002)
        except BaseException as exc:  # fixture thread 必須把錯誤帶回主執行緒
            errors.append(exc)

    worker = threading.Thread(target=mutate)
    worker.start()
    stdout, stderr = proc.communicate(timeout=20)
    worker.join(timeout=1)
    if errors:
        raise errors[0]
    if _git(root, "write-tree").stdout.strip() == before_tree:
        raise AssertionError("SC-031 fixture 未在執行期間改變 index tree")
    return _parse_json_output(subprocess.CompletedProcess([], proc.returncode, stdout, stderr))


def _run_with_head_drift(root: pathlib.Path, script: str, *args: str) -> dict[str, Any]:
    """在 CLI 裁決期間建立新 HEAD commit，使 snapshot commit OID 改變。"""
    before_head = _git(root, "rev-parse", "HEAD").stdout.strip()
    errors: list[BaseException] = []
    proc = subprocess.Popen(
        [str(root / "scripts" / "gates" / script), *args],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    def mutate() -> None:
        try:
            generation = 0
            while proc.poll() is None:
                generation += 1
                subprocess.run(
                    ["git", "commit", "--allow-empty", "-qm", f"HEAD drift {generation}"],
                    cwd=root,
                    check=True,
                    capture_output=True,
                )
                time.sleep(0.002)
        except BaseException as exc:  # fixture thread 必須把錯誤帶回主執行緒
            errors.append(exc)

    worker = threading.Thread(target=mutate)
    worker.start()
    stdout, stderr = proc.communicate(timeout=20)
    worker.join(timeout=1)
    if errors:
        raise errors[0]
    if _git(root, "rev-parse", "HEAD").stdout.strip() == before_head:
        raise AssertionError("SC-053 fixture 未在執行期間建立新 HEAD commit")
    return _parse_json_output(subprocess.CompletedProcess([], proc.returncode, stdout, stderr))


def _configure(root: pathlib.Path, scenario: str, fixture: dict[str, Any]) -> None:
    pipeline = root / "specs" / "pipeline.yaml"
    config = {
        "runner": "static-command",
        "autonomy": {"version": 1},
        "tests": {
            "globs": ["scripts/gates/tests/run", "scripts/gates/tests/mutate"],
            "scenario_pattern": 'check\\(\\s*"(SC-\\d+[a-z]?)',
        },
        "reachability": {"globs": ["scripts/gates/*"]},
        "lint": "git diff --check --",
        "test": "scripts/gates/tests/run",
        "smoke": "scripts/gates/tests/run",
        "smoke_timeout": 600,
        "integration_branch": "main",
        "auto_push": True,
        "ci": "none",
        "rules_files": ["AGENTS.md"],
        "models": {"draft": "fable", "review": "fable", "build": "opus"},
    }
    if scenario == "SC-021":
        if "autonomy" not in fixture:
            config.pop("autonomy")
        else:
            config["autonomy"] = fixture["autonomy"]
    elif scenario in {"SC-022", "SC-023", "SC-040"}:
        config["autonomy"] = fixture.get("autonomy")
        if "models" in fixture:
            config["models"] = fixture["models"]
    elif scenario == "SC-039":
        # SC-039 驗證 delivery orchestration；此 spec 沒有 6c Scenario，使用
        # 無副作用 test/smoke command，避免 dashboard 反向遞迴整份 SC-039 checker。
        config["test"] = "git diff --check --"
        config["smoke"] = "git diff --check --"
    import yaml
    pipeline.write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False))


def _approval_fixture(root: pathlib.Path, scenario: str) -> None:
    ev = root / "specs" / "workflow-autonomy" / "evidence"
    if scenario == "SC-024":
        (ev / "spec.approved.yaml").unlink(missing_ok=True)
    if scenario == "SC-025":
        (ev / "spec.hash").write_text("sha256:" + "0" * 64 + "  specs/workflow-autonomy/spec.yaml\n")


def _autonomy_args(scenario: str, fixture: dict[str, Any]) -> list[str]:
    spec = str(SPEC_REL)
    if scenario == "SC-057":
        return [spec, *[str(v) for v in fixture["argv"]]]
    operation = "verify-tests" if scenario in {"SC-006", "SC-007", "SC-029", "SC-030", "SC-042", "SC-052", "SC-053"} else (
        "complete" if scenario in {"SC-005", "SC-026", "SC-027", "SC-047", "SC-058", "SC-059"} else (
            "check" if scenario in {"SC-028", "SC-041"} else "plan"
        )
    )
    args = [spec, operation]
    if operation == "check":
        return args
    args += ["--expect-generation", str(fixture.get("expect_generation", 0)), "--id", str(fixture.get("id", "R-001"))]
    if operation == "plan":
        args += ["--kind", str(fixture["kind"])]
        for path in fixture.get("files", []):
            args += ["--file", str(path)]
        if fixture.get("summary") is not None:
            args += ["--summary", str(fixture["summary"])]
    elif operation == "complete":
        for path in fixture.get("evidence", []):
            args += ["--evidence", str(path)]
    return args


def _seed_autonomy(root: pathlib.Path, scenario: str, fixture: dict[str, Any]) -> None:
    if scenario not in {"SC-005", "SC-006", "SC-007", "SC-026", "SC-027", "SC-028", "SC-029", "SC-030",
                        "SC-041", "SC-042", "SC-047", "SC-050", "SC-051", "SC-052", "SC-053", "SC-056",
                        "SC-058", "SC-059"}:
        return
    frozen = {"SC-005", "SC-006", "SC-007", "SC-029", "SC-030", "SC-042", "SC-052", "SC-053"}
    kind = "frozen_test" if scenario in frozen else "implementation"
    if scenario == "SC-047" and fixture.get("fixture_current_status") == "blocked":
        kind = "product_change"
    rid = str(fixture.get("id", "R-001"))
    seed_id = "R-001" if scenario == "SC-047" and rid == "R-999" else rid
    if scenario == "SC-050":
        kind = str(fixture["kind"])
        seed_file = str(fixture["files"][0])
    elif scenario == "SC-047" and fixture.get("fixture_current_status") == "blocked":
        seed_file = "specs/workflow-autonomy/spec.yaml"
    else:
        seed_file = "scripts/gates/tests/spec_workflow_autonomy.py" if scenario in frozen else "scripts/gates/autonomy"
    if scenario == "SC-058":
        dirty = root / str(fixture["fixture_preexisting_dirty_path"])
        dirty.parent.mkdir(parents=True, exist_ok=True)
        dirty.write_text("pre-existing dirty version 1\n")
    if scenario == "SC-059":
        outside = root / str(fixture["evidence"][0])
        outside.parent.mkdir(parents=True, exist_ok=True)
        outside.write_text("fixture evidence\n")
    if scenario == "SC-047" and fixture.get("fixture_current_status") == "blocked":
        _run(root, "autonomy", str(SPEC_REL), "plan", "--expect-generation", "0", "--id", "R-PRE",
             "--kind", "evidence", "--file", "specs/workflow-autonomy/evidence/pre.log")
        _run(root, "autonomy", str(SPEC_REL), "plan", "--expect-generation", "1", "--id", rid,
             "--kind", kind, "--file", seed_file)
    elif scenario != "SC-051":
        _run(root, "autonomy", str(SPEC_REL), "plan", "--expect-generation", "0", "--id", seed_id,
             "--kind", kind, "--file", seed_file)
    ev = root / "specs" / "workflow-autonomy" / "evidence"
    ev.mkdir(parents=True, exist_ok=True)
    requested_evidence = list(fixture.get("evidence", []))
    if scenario == "SC-047" and fixture.get("fixture_existing_completion_evidence"):
        requested_evidence = []
    for rel in requested_evidence:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("" if fixture.get("fixture_evidence") == "empty" else "fixture evidence\n")
    if scenario in {"SC-026", "SC-027"}:
        _run(root, "autonomy", str(SPEC_REL), "plan", "--expect-generation", "1", "--id", "R-PRE",
             "--kind", "evidence", "--file", "specs/workflow-autonomy/evidence/pre.log")
    elif scenario == "SC-028":
        (ev / "repro.log").write_text("fixture evidence\n")
        _run(root, "autonomy", str(SPEC_REL), "complete", "--expect-generation", "1", "--id", rid,
             "--evidence", "specs/workflow-autonomy/evidence/repro.log")
    elif scenario == "SC-041" and (fixture.get("repairs") or [{}])[0].get("status") == "blocked":
        _run(root, "autonomy", str(SPEC_REL), "plan", "--expect-generation", "1", "--id", "R-BLOCK",
             "--kind", "product_change", "--file", "specs/workflow-autonomy/spec.yaml")
    elif scenario == "SC-047":
        if fixture.get("fixture_existing_completion_evidence"):
            prior = root / fixture["fixture_existing_completion_evidence"][0]
            prior.parent.mkdir(parents=True, exist_ok=True)
            prior.write_text("prior completion\n")
            _run(root, "autonomy", str(SPEC_REL), "complete", "--expect-generation", "1", "--id", rid,
                 "--evidence", str(prior.relative_to(root)))
            for rel in fixture.get("evidence", []):
                changed = root / rel
                changed.parent.mkdir(parents=True, exist_ok=True)
                changed.write_text("fixture evidence\n")
        elif fixture.get("fixture_current_status") != "blocked":
            _run(root, "autonomy", str(SPEC_REL), "plan", "--expect-generation", "1", "--id", "R-PRE",
                 "--kind", "evidence", "--file", "specs/workflow-autonomy/evidence/pre.log")
            ledger = ev / "autonomy.json"
            if fixture.get("fixture_plan_version") == "stale" and ledger.exists():
                payload = json.loads(ledger.read_text())
                for repair in payload.get("repairs", []):
                    if repair.get("id") == rid:
                        repair["plan_version"] = "sha256:" + "0" * 64
                _write_json(ledger, payload)
    elif scenario == "SC-051":
        _run(root, "autonomy", str(SPEC_REL), "plan", "--expect-generation", "0", "--id", "R-PRE0",
             "--kind", "evidence", "--file", "specs/workflow-autonomy/evidence/pre0.log")
        _run(root, "autonomy", str(SPEC_REL), "plan", "--expect-generation", "1", "--id", "R-PRE",
             "--kind", "evidence", "--file", "specs/workflow-autonomy/evidence/pre.log")
        _run(root, "autonomy", str(SPEC_REL), "plan", "--expect-generation", "2", "--id", "R-PRE2",
             "--kind", "evidence", "--file", "specs/workflow-autonomy/evidence/pre2.log")
    if fixture.get("fixture_mutate_after_plan"):
        path = root / str(fixture["fixture_preexisting_dirty_path"])
        path.write_text("pre-existing dirty version 2\n")


def _sha_record(root: pathlib.Path, rel: str) -> dict[str, str]:
    return {"path": rel, "sha256": "sha256:" + hashlib.sha256((root / rel).read_bytes()).hexdigest()}


def _seed_frozen_artifacts(root: pathlib.Path, scenario: str, fixture: dict[str, Any]) -> None:
    if scenario not in {"SC-005", "SC-006", "SC-007", "SC-029", "SC-030", "SC-042", "SC-052", "SC-053"}:
        return
    ev = root / "specs/workflow-autonomy/evidence"
    test_rel = "scripts/gates/tests/spec_workflow_autonomy.py"
    tests = [_sha_record(root, test_rel)]
    tree_token = "tree:" + _git(root, "rev-parse", "HEAD^{tree}").stdout.strip()
    writer = "task:writer-001"
    reviewer = writer if fixture.get("fixture_review") == "same_actor" else "task:reviewer-002"
    dispatch = {
        "schema_version": 1, "writer_task_ref": writer, "reviewer_task_ref": reviewer,
        "completion_ref": "completion:review-001", "tree_token": tree_token,
        "created_at": "2026-09-14T00:00:00+08:00",
    }
    agent = dict(dispatch)
    agent.update({"status": "blocking" if fixture.get("fixture_review") == "blocking" else "passed", "findings": []})
    assertion_weakened = fixture.get("fixture_assertion") == "weakened"
    import yaml
    source = yaml.safe_load((root / SPEC_REL).read_text())
    reviewed_examples = [
        {"scenario": item["id"], "examples": list(range(1, len(item["examples"]) + 1))}
        for requirement in source["requirements"]
        for item in requirement["scenarios"]
    ]
    token_input = {
        "writer_task_ref": writer, "reviewer_task_ref": reviewer,
        "completion_ref": dispatch["completion_ref"], "tree_token": tree_token,
        "before_tests": tests, "after_tests": tests,
        "assertion_weakened": assertion_weakened, "reviewed_examples": reviewed_examples,
    }
    review_token = "sha256:" + hashlib.sha256(_canonical(token_input).encode()).hexdigest()
    review = {
        "schema_version": 1, "status": agent["status"], "before_tests": tests, "after_tests": tests,
        "assertion_weakened": assertion_weakened, "reviewed_examples": reviewed_examples,
        "review_token": review_token, "reviewed_at": "2026-09-14T00:00:01+08:00",
    }
    red_tree = "tree:" + "0" * 40 if fixture.get("fixture_red") == "stale" else tree_token
    runner_results = []
    (ev / "static-red").mkdir(parents=True, exist_ok=True)
    for reviewed in reviewed_examples:
        sid = reviewed["scenario"]
        for index in reviewed["examples"]:
            stem = f"{sid.lower()}-{index}"
            stdout_rel = f"specs/workflow-autonomy/evidence/static-red/{stem}.stdout.log"
            stderr_rel = f"specs/workflow-autonomy/evidence/static-red/{stem}.stderr.log"
            (root / stdout_rel).write_text(f"STATIC_ASSERTION: {sid} example #{index}\n")
            (root / stderr_rel).write_text("no stderr\n")
            runner_results.append({
                "schema_version": 1, "scenario": sid, "example": index,
                "argv": ["python3", test_rel, "--case", sid, "--example", str(index)],
                "timeout_seconds": 30, "exit_code": 1,
                "stdout_path": stdout_rel, "stderr_path": stderr_rel,
                "failure_class": "assertion", "marker_lines": [f"STATIC_ASSERTION: {sid} example #{index}"],
                "red_valid": True, "started_at": "2026-09-14T00:00:02+08:00",
                "finished_at": "2026-09-14T00:00:03+08:00", "tree_token": red_tree,
            })
    red = {
        "schema_version": 1,
        "spec_hash": "sha256:" + hashlib.sha256((root / SPEC_REL).read_bytes()).hexdigest(),
        "runner_results": runner_results,
        "status": "passed", "generated_at": "2026-09-14T00:00:03+08:00",
    }
    _write_json(ev / "review-dispatch.json", dispatch)
    _write_json(ev / "test-review.agent.json", agent)
    _write_json(ev / "test-review.json", review)
    _write_json(ev / "red.json", red)
    (ev / "tests.hash").write_text(f"{tests[0]['sha256']}  {test_rel}\n")

    if fixture.get("fixture_review") == "missing":
        (ev / "test-review.agent.json").unlink(missing_ok=True)
    if fixture.get("fixture_red") == "missing":
        (ev / "red.json").unlink(missing_ok=True)
    if fixture.get("fixture_tests_hash") == "missing":
        (ev / "tests.hash").unlink(missing_ok=True)
    elif fixture.get("fixture_tests_hash") == "mismatched":
        (ev / "tests.hash").write_text("sha256:" + "0" * 64 + f"  {test_rel}\n")


def _fixture_worktree_entries(root: pathlib.Path) -> list[dict[str, str]]:
    """依 autonomy plan 契約擷取完整、排序的 non-symlink regular baseline。"""
    proc = subprocess.run(
        ["git", "ls-files", "-co", "--exclude-standard", "-z"],
        cwd=root, capture_output=True, check=True,
    )
    entries = []
    for chunk in proc.stdout.split(b"\0"):
        if not chunk:
            continue
        rel = chunk.decode(errors="surrogateescape")
        path = root / rel
        try:
            info = path.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISREG(info.st_mode):
            entries.append({
                "path": rel,
                "mode": format(stat.S_IMODE(info.st_mode), "04o"),
                "sha256": "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(),
            })
    return sorted(entries, key=lambda row: row["path"])


def _fixture_request_sha(payload: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(payload).encode()).hexdigest()


def _assert_captured_baseline(
    root: pathlib.Path, baseline_entries: list[dict[str, str]],
) -> None:
    """在 simulated plan 當下重抓一次，證明 baseline 沒有漏檔或混入 symlink。"""
    if baseline_entries != _fixture_worktree_entries(root):
        raise AssertionError("delivery fixture baseline 無法在 plan 當下重算")


def _delivery_complete_request_sha(
    rid: str, evidence: list[str], spec_hash: str, plan_version: str,
) -> str:
    """complete history 的 canonical CLI request；與既定 plan payload 分離。"""
    return _fixture_request_sha({
        "id": rid, "evidence": sorted(set(evidence)),
        "spec_hash": spec_hash, "plan_version": plan_version,
    })


def _assert_delivery_seed_preconditions(
    root: pathlib.Path, ledger: dict[str, Any], baseline_entries: list[dict[str, str]],
    plan_payload: dict[str, Any], complete_evidence: list[str],
) -> None:
    """任何案例 mutation 前先證明共用合法 fixture 可機械重算。"""
    repair = ledger["repairs"][0]
    baseline_token = _fixture_request_sha(baseline_entries)
    baseline_modes_ok = bool(baseline_entries) and all(
        re.fullmatch(POSIX_MODE_PATTERN, str(row.get("mode", ""))) is not None
        for row in baseline_entries
    )
    plan_sha = _fixture_request_sha(plan_payload)
    complete_sha = _delivery_complete_request_sha(
        repair["id"], complete_evidence, repair["spec_hash"], repair["plan_version"],
    )
    tree_pattern = TREE_TOKEN["pattern"]
    expected_tree = "tree:" + _git(root, "rev-parse", "HEAD^{tree}").stdout.strip()
    evidence_rows = repair.get("evidence", [])
    evidence_ok = all(
        isinstance(row, dict)
        and re.fullmatch(tree_pattern, str(row.get("tree_token", ""))) is not None
        and row.get("tree_token") == expected_tree
        and row.get("sha256") == "sha256:" + hashlib.sha256(
            (root / str(row.get("path"))).read_bytes()
        ).hexdigest()
        and row.get("bytes") == len((root / str(row.get("path"))).read_bytes())
        for row in evidence_rows
    ) and bool(evidence_rows)
    history = ledger.get("history", [])
    if not (
        repair.get("baseline_entries") == baseline_entries
        and baseline_modes_ok
        and repair.get("baseline_worktree_token") == baseline_token
        and len(history) == 2
        and history[0].get("operation") == "plan"
        and history[0].get("request_sha256") == plan_sha
        and history[1].get("operation") == "complete"
        and history[1].get("request_sha256") == complete_sha
        and plan_sha != complete_sha
        and evidence_ok
    ):
        raise AssertionError("delivery fixture prerequisite 無法機械重算")


def _delivery_fixture(root: pathlib.Path, scenario: str, fixture: dict[str, Any]) -> str:
    ev = root / "specs" / "workflow-autonomy" / "evidence"
    files = list(fixture.get("files") or [])
    requested = fixture.get("path")
    if requested:
        files = [str(requested)]
    manifest_files = []
    generated = {
        "red.json": {"schema_version": 1, "status": "passed", "runner_results": []},
        "test-review.json": {"schema_version": 1, "status": "passed", "reviewed_examples": []},
    }
    for name, payload in generated.items():
        _write_json(ev / name, payload)
    _write_json(ev / "status.json", _status_record(int(fixture.get("status_generation", 1))))
    test_rel = "scripts/gates/tests/spec_workflow_autonomy.py"
    (ev / "tests.hash").write_text(
        "sha256:" + hashlib.sha256((root / test_rel).read_bytes()).hexdigest() + f"  {test_rel}\n"
    )
    state_roots: list[tuple[str, str]] = []
    # SC-010/012（SC-015 以 SC-012 建 committed payload）是合法交付正例；補齊
    # completed autonomy ledger、dashboard 與 findings，避免正例因缺少 v1 roots
    # 提早失敗。summary 只屬 request canonical，不落 repair。
    if scenario in {"SC-008", "SC-010", "SC-012", "SC-031"}:
        evidence_rel = "specs/workflow-autonomy/evidence/spec.hash"
        spec_hash = "sha256:" + hashlib.sha256((root / SPEC_REL).read_bytes()).hexdigest()
        evidence_bytes = (root / evidence_rel).read_bytes()
        request = {
            "id": "R-DELIVERY", "kind": "evidence", "files": [evidence_rel],
            "summary": None, "spec_hash": spec_hash,
        }
        request_sha = _fixture_request_sha(request)
        complete_evidence = [evidence_rel]
        complete_request_sha = _delivery_complete_request_sha(
            "R-DELIVERY", complete_evidence, spec_hash, request_sha,
        )
        baseline_entries = _fixture_worktree_entries(root)
        _assert_captured_baseline(root, baseline_entries)
        tree_token = "tree:" + _git(root, "rev-parse", "HEAD^{tree}").stdout.strip()
        recorded_at = "2026-09-14T00:00:00+08:00"
        _write_json(ev / "autonomy.json", {
            "schema_version": 1, "generation": 2, "spec_hash": spec_hash,
            "repairs": [{
                "id": "R-DELIVERY", "kind": "evidence", "status": "complete",
                "files": [evidence_rel], "spec_hash": spec_hash,
                "scope_sources": [{"path": evidence_rel, "source": "evidence"}],
                "blocked_on": None, "reason": None, "plan_version": request_sha,
                "baseline_entries": baseline_entries,
                "baseline_worktree_token": _fixture_request_sha(baseline_entries),
                "evidence": [{
                    "path": evidence_rel,
                    "sha256": "sha256:" + hashlib.sha256(evidence_bytes).hexdigest(),
                    "bytes": len(evidence_bytes), "tree_token": tree_token,
                }],
                "planned_at": recorded_at, "completed_at": "2026-09-14T00:00:01+08:00",
            }],
            "history": [
                {"generation": 1, "operation": "plan", "repair_id": "R-DELIVERY",
                 "request_sha256": request_sha, "result_status": "planned", "reason": None,
                 "recorded_at": recorded_at},
                {"generation": 2, "operation": "complete", "repair_id": "R-DELIVERY",
                 "request_sha256": complete_request_sha, "result_status": "complete", "reason": None,
                 "recorded_at": "2026-09-14T00:00:01+08:00"},
            ],
            "updated_at": "2026-09-14T00:00:01+08:00",
        })
        _write_json(ev / "dashboard.json", {
            "name": "workflow-autonomy", "branch": "main", "scale": "fixture",
            "phase": "delivery", "approval_anchor": "committed",
            "gates": [], "attention": [], "screenshots": [], "auto_push_ok": False,
        })
        _write_json(ev / "findings.json", {
            "items": [], "dispatched": {},
            "summary": {"proposed": 0, "void": 0, "confirmed": 0},
        })
        ledger = json.loads((ev / "autonomy.json").read_text())
        _assert_delivery_seed_preconditions(
            root, ledger, baseline_entries, request, complete_evidence,
        )
        state_roots = [
            ("specs/workflow-autonomy/evidence/autonomy.json", "autonomy"),
            ("specs/workflow-autonomy/evidence/findings.json", "finding"),
        ]
    roots = [
        (str(SPEC_REL), "spec"),
        ("specs/workflow-autonomy/evidence/spec.approved.yaml", "approval"),
        ("specs/workflow-autonomy/evidence/approval.json", "approval"),
        ("specs/workflow-autonomy/evidence/spec.hash", "freeze"),
        ("specs/workflow-autonomy/evidence/tests.hash", "freeze"),
        ("specs/workflow-autonomy/evidence/red.json", "red"),
        ("specs/workflow-autonomy/evidence/test-review.json", "review"),
        *state_roots,
    ]
    for rel, source in roots:
        payload = (root / rel).read_bytes()
        manifest_files.append({
            "path": rel,
            "sha256": "sha256:" + hashlib.sha256(payload).hexdigest(),
            "source": source,
        })
    for rel in files:
        if rel.startswith("../"):
            manifest_files.append({"path": rel, "sha256": "sha256:" + "0" * 64, "source": "red"})
            continue
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if scenario == "SC-008":
            payload = b"worktree-only ignored evidence\n"
            target.write_bytes(payload)
        elif fixture.get("exists") is False or not fixture.get("tracked", True):
            payload = None
        elif fixture.get("fixture_file_type") == "symlink":
            target.symlink_to(root / "specs" / "pipeline.yaml")
            payload = None
        else:
            payload = b"" if fixture.get("bytes") == 0 else b"evidence\n"
            target.write_bytes(payload)
        digest = "sha256:" + hashlib.sha256(payload or b"expected old bytes").hexdigest()
        if fixture.get("fingerprint_current") is False:
            digest = "sha256:" + hashlib.sha256(b"stale bytes").hexdigest()
        manifest_files.append({"path": rel, "sha256": digest, "source": "red"})
    if scenario == "SC-008":
        (root / ".git/info/exclude").write_text("\n".join(files) + "\n")
    if scenario == "SC-043":
        manifest_files = []
    _write_json(ev / "delivery.json", {
        "schema_version": 1,
        "spec_hash": "sha256:" + hashlib.sha256((root / SPEC_REL).read_bytes()).hexdigest(),
        "approval_commit": _git(root, "rev-parse", "HEAD").stdout.strip(),
        "approval_tree": _git(root, "rev-parse", "HEAD^{tree}").stdout.strip(),
        "files": manifest_files,
    })
    return "--commit" if scenario in {"SC-011", "SC-012"} else "--index"


def _status_args(fixture: dict[str, Any]) -> list[str]:
    flags = {
        "pipeline_state": "--pipeline-state", "stage": "--stage", "next_step": "--next-step",
        "blocked_on": "--blocked-on", "delivery_state": "--delivery-state", "delivery_ref": "--delivery-ref",
        "report_state": "--report-state", "report_reason": "--report-reason",
        "fixture_committed_evidence_token": "--committed-evidence-token",
    }
    args = ["--set", str(SPEC_REL), "--expect-generation", str(fixture["expect_generation"])]
    for key, flag in flags.items():
        if key in fixture and fixture[key] is not None:
            value = fixture[key]
            args += [flag, str(value).lower() if isinstance(value, bool) else str(value)]
    return args


def _status_record(generation: int) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "generation": generation,
        "pipeline_state": "waiting",
        "stage": "S7",
        "next_step": "fixture",
        "blocked_on": None,
        "delivery": {"state": "local", "ref": None, "validation": None},
        "report": {"state": "pending", "reason": None},
        "updated_at": "2026-09-14T00:00:00+08:00",
    }


def _static_fixture(root: pathlib.Path, scenario: str, example: int, fixture: dict[str, Any]) -> None:
    import yaml
    ev = root / "specs/workflow-autonomy/evidence"
    ev.joinpath("red.json").unlink(missing_ok=True)
    source = yaml.safe_load((root / SPEC_REL).read_text())
    selected = None
    for req in source["requirements"]:
        for item in req["scenarios"]:
            if item["id"] == scenario:
                selected = dict(item)
                break
    if selected is None:
        raise AssertionError(scenario)
    if scenario == "SC-019":
        selected["examples"] = [selected["examples"][0], selected["examples"][0]]
    else:
        selected["examples"] = [selected["examples"][example - 1]]
    mini = {
        "meta": {"name": "workflow-autonomy", "ticket": None, "capability": "static", "change_type": "MODIFIED"},
        "why": "static command fixture",
        "what": {"changes": ["static fixture"], "non_goals": ["no product change"]},
        "impact": {"files": ["checker.py"], "call_sites": "isolated test fixture"},
        "requirements": [{
            "id": "REQ-001", "statement": "Fixture SHALL check one static contract",
            "completeness": {
                "empty_boundary": [scenario], "error_path": [scenario],
                "concurrency": "N/A — isolated process", "illegal_state": [scenario],
                "authorization": "N/A — local fixture", "data_migration": "N/A — no data",
            },
            "scenarios": [selected],
        }],
        "tasks": [{"done": False, "text": "static fixture"}],
    }
    (root / SPEC_REL).write_text(yaml.safe_dump(mini, allow_unicode=True, sort_keys=False))
    checker = root / "checker.py"
    if fixture.get("timed_out"):
        checker.write_text("import time\ntime.sleep(5)\n")
    else:
        output = str(fixture.get("output", ""))
        code = int(fixture.get("exit_code", 1))
        checker.write_text(f"import sys\nprint({output!r})\nraise SystemExit({code})\n")
    checks = [{"scenario": scenario, "examples": fixture.get("checked_examples", [1])}]
    entry = {
        "layer": "workflow-autonomy", "runner": "static-command",
        "argv": ["python3", "checker.py"], "timeout_seconds": int(fixture.get("timeout_seconds", 30)),
        "tests": ["checker.py"], "checks": checks,
    }
    if scenario == "SC-034" and example == 1:
        entry.update({"argv": [], "checks": []})
    if scenario == "SC-034" and example == 3:
        entry["checks"] = [{"scenario": "SC-999", "examples": [1]}]
    if scenario == "SC-034" and example == 4:
        entry["checks"] = [{"scenario": scenario, "examples": [0]}]
    if scenario == "SC-055":
        (root / "policy.json").write_text("{}\n")
        checker.write_text(
            "import json\n"
            "def assertThat(actual, expected): return actual == expected\n"
            "def check(name, ok): return ok\n"
            f"check(\"{scenario} static dependency fixture\", "
            f"assertThat({selected['examples'][0]['out']!r}, {selected['examples'][0]['out']!r}))\n"
            "json.load(open('policy.json'))\n"
        )
    elif scenario == "SC-035":
        (root / "policy.json").write_text("{}\n")
        checker.write_text(
            "def assertThat(actual, expected): return actual == expected\n"
            "def check(name, ok): return ok\n"
            f"check(\"{scenario} reviewed static contract\", "
            f"assertThat({selected['examples'][0]['out']!r}, {selected['examples'][0]['out']!r}))\n"
        )
        entry["tests"] = ["checker.py", "policy.json"]
    if scenario == "SC-020":
        swift = root / "static-swift.log"
        swift.write_text(
            '◇ Test "SC-020 legacy parser" started.\n'
            '✘ Test "SC-020 legacy parser" recorded an issue at T.swift:1:1: '
            'Expectation failed: 1 == 2\n'
            '✘ Test "SC-020 legacy parser" failed after 0.001 seconds with 1 issue.\n'
            'Test run with 1 test in 1 suite failed after 0.001 seconds with 1 issue.\n'
        )
        checker.write_text('@Test("SC-020 legacy parser")\n')
        entry = {"layer": "workflow-autonomy", "output": str(swift), "tests": ["checker.py"]}
        _configure(root, "static", {})
        pipeline = root / "specs/pipeline.yaml"
        pipeline.write_text(pipeline.read_text().replace("runner: static-command", "runner: swift-testing"))
    _write_json(root / "specs/workflow-autonomy/evidence/red-inputs.json", [entry])
    (ev / "spec.hash").write_text(
        "sha256:" + hashlib.sha256((root / SPEC_REL).read_bytes()).hexdigest() + f"  {SPEC_REL}\n"
    )
    if scenario == "SC-035":
        (ev / "tests.hash").write_text("".join(
            "sha256:" + hashlib.sha256((root / rel).read_bytes()).hexdigest() + f"  {rel}\n"
            for rel in entry["tests"]
        ))


def _finding_fixture(root: pathlib.Path, scenario: str, fixture: dict[str, Any]) -> list[str]:
    ev = root / "specs/workflow-autonomy/evidence"
    repro = ev / "repro.json"
    repro_exit = int(fixture.get("fixture_repro_exit", 1))
    repro_inputs: list[dict[str, str]] = []
    if scenario == "SC-038":
        changed = str(fixture["changed_files"][0])
        repro_inputs = [_sha_record(root, changed)]
    _write_json(repro, {
        "schema_version": 1, "argv": ["python3", "-c", f"raise SystemExit({repro_exit})"],
        "path_indices": [], "cwd": ".", "stdin_sha256": None, "environment": {}, "inputs": repro_inputs,
    })
    item = {
        "id": "F-7", "gate": "G10", "class": "must_fix", "kind": "must_fix", "check": "SC-037",
        "location": "scripts/gates/_common.py:1", "title": "fixture", "repro": str(repro.relative_to(root)),
        "repro_json": str(repro.relative_to(root)), "status": "fixed", "fixes": int(fixture.get("fixture_fixes", 1)),
    }
    _write_json(ev / "findings.json", {"items": [item], "dispatched": {}, "summary": {}})
    if scenario == "SC-038":
        changed = root / str(fixture["changed_files"][0])
        changed.write_text(changed.read_text() + "\n# changed after finding capture\n")
    if scenario == "SC-045":
        if fixture.get("requested_action") == "redispatch":
            state = {
                "findings": {},
                "redispatch": {str(fixture["gate"]): int(fixture["prior_redispatches"])},
                "requested_action": {"kind": "redispatch", "gate": str(fixture["gate"])},
            }
        else:
            finding_id = str(fixture.get("id", "F-7"))
            state = {
                "findings": {
                    finding_id: {
                        "fixes": int(fixture["fixes"]), "status": "open", "history": [],
                        "requested_action": "fix",
                    }
                },
                "redispatch": {},
                "requested_action": {"kind": "fix", "id": finding_id},
            }
        _write_json(ev / "loop.json", state)
        return [str(SPEC_REL)]
    if scenario in {"SC-044", "SC-049"}:
        requested = str(fixture.get("requested_id", "F-99"))
        requested_repro = repro
        if scenario == "SC-049":
            requested_repro = ev / "different-repro.json"
            _write_json(requested_repro, {
                "schema_version": 1, "argv": ["python3", "-c", "raise SystemExit(2)"],
                "path_indices": [], "cwd": ".", "stdin_sha256": None, "environment": {}, "inputs": [],
            })
        return [str(SPEC_REL), "add", "--id", requested, "--kind", "must_fix", "--check", "SC-037",
                "--location", "scripts/gates/_common.py:1", "--repro-json", str(requested_repro.relative_to(root))]
    return [str(SPEC_REL), "revalidate", "--id", str(fixture.get("id", "F-7"))]


def _approval_source_anchor(candidate: pathlib.Path) -> tuple[str, str]:
    approval_paths = (
        "specs/workflow-autonomy/evidence/spec.approved.yaml",
        "specs/workflow-autonomy/evidence/spec.hash",
        "specs/workflow-autonomy/evidence/approval.json",
    )
    expected = {rel: (candidate / rel).read_bytes() for rel in approval_paths}
    commits = _git(SOURCE_ROOT, "rev-list", "HEAD").stdout.splitlines()
    for commit in commits:
        matched = True
        for rel in approval_paths:
            blob = subprocess.run(
                ["git", "show", f"{commit}:{rel}"],
                cwd=SOURCE_ROOT,
                capture_output=True,
            )
            mode = _git(SOURCE_ROOT, "ls-tree", commit, rel).stdout.split()
            if blob.returncode != 0 or blob.stdout != expected[rel] or not mode or mode[0] != "100644":
                matched = False
                break
        if matched:
            return commit, _git(SOURCE_ROOT, "rev-parse", f"{commit}^{{tree}}").stdout.strip()
    raise AssertionError("找不到與 candidate approval 三件組一致的 committed source anchor")


def _baseline_repo(
    candidate: pathlib.Path,
    source_commit: str,
    source_tree: str,
) -> tuple[pathlib.Path, pathlib.Path]:
    actual_tree = _git(SOURCE_ROOT, "rev-parse", f"{source_commit}^{{tree}}").stdout.strip()
    if actual_tree != source_tree:
        raise AssertionError("approval source_tree 與 source_commit 不一致")
    for rel in (
        "specs/workflow-autonomy/evidence/spec.approved.yaml",
        "specs/workflow-autonomy/evidence/spec.hash",
        "specs/workflow-autonomy/evidence/approval.json",
    ):
        blob = subprocess.run(
            ["git", "show", f"{source_commit}:{rel}"], cwd=SOURCE_ROOT, capture_output=True, check=True
        ).stdout
        if blob != (candidate / rel).read_bytes():
            raise AssertionError(f"approval source_tree blob 不一致：{rel}")
    baseline = candidate.parent / "baseline"
    shutil.copytree(candidate, baseline, ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"))
    _git(baseline, "init", "-q", ".")
    _git(baseline, "config", "user.email", "workflow-baseline@example.invalid")
    _git(baseline, "config", "user.name", "Workflow Baseline Fixture")
    _commit(baseline, "paired fixture")
    baseline_gates = candidate.parent / "baseline-gates"
    shutil.copytree(
        SOURCE_GATES,
        baseline_gates,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    tracked = {
        rel for rel in _git(
            SOURCE_ROOT, "ls-tree", "-r", "--name-only", source_commit, "scripts/gates"
        ).stdout.splitlines()
        if rel
    }
    current = {
        "scripts/gates/" + path.relative_to(baseline_gates).as_posix()
        for path in baseline_gates.rglob("*")
        if path.is_file() or path.is_symlink()
    }
    for rel in sorted(current - tracked):
        (baseline_gates / pathlib.Path(rel).relative_to("scripts/gates")).unlink(missing_ok=True)
    for rel in sorted(tracked):
        payload = subprocess.run(
            ["git", "show", f"{source_commit}:{rel}"], cwd=SOURCE_ROOT, capture_output=True, check=True
        ).stdout
        target = baseline_gates / pathlib.Path(rel).relative_to("scripts/gates")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        mode = _git(SOURCE_ROOT, "ls-tree", source_commit, rel).stdout.split()[0]
        target.chmod(0o755 if mode == "100755" else 0o644)
    return baseline, baseline_gates


def _prepare_legacy_repo(root: pathlib.Path) -> None:
    import yaml
    pipeline = yaml.safe_load((root / "specs/pipeline.yaml").read_text())
    pipeline["runner"] = "swift-testing"
    pipeline["autonomy"] = {"version": 0}
    pipeline["tests"]["globs"] = ["legacy.swift"]
    pipeline["tests"]["scenario_pattern"] = '@Test\\(\\s*"(SC-\\d+[a-z]?)'
    pipeline["lint"] = "git diff --check --"
    pipeline["test"] = "git diff --check --"
    pipeline["smoke"] = "git diff --check --"
    (root / "specs/pipeline.yaml").write_text(yaml.safe_dump(pipeline, allow_unicode=True, sort_keys=False))
    source = yaml.safe_load((root / SPEC_REL).read_text())
    test_lines: list[str] = []
    output_lines: list[str] = []
    count = 0
    for req in source["requirements"]:
        for scenario in req["scenarios"]:
            sid = scenario["id"]
            for index, example in enumerate(scenario["examples"], 1):
                count += 1
                name = f"{sid} legacy example {index}"
                test_lines.append(f'@Test("{name}")')
                test_lines.append(f'func legacy{count}() {{ #expect({example["out"]!r} == ["not implemented"]) }}')
                output_lines.append(f'◇ Test "{name}" started.')
                output_lines.append(
                    f'✘ Test "{name}" recorded an issue at legacy.swift:{count}:1: '
                    'Expectation failed: approved projection != not implemented'
                )
                output_lines.append(f'✘ Test "{name}" failed after 0.001 seconds with 1 issue.')
    output_lines.append(f"Test run with {count} tests in 1 suite failed after 0.001 seconds with {count} issues.")
    (root / "legacy.swift").write_text("\n".join(test_lines) + "\n")
    raw = root / "legacy-red.log"
    raw.write_text("\n".join(output_lines) + "\n")
    _write_json(root / "specs/workflow-autonomy/evidence/red-inputs.json", [{
        "layer": "workflow-autonomy", "output": str(raw), "tests": ["legacy.swift"],
    }])
    ev = root / "specs/workflow-autonomy/evidence"
    (ev / "tests.hash").write_text(
        "sha256:" + hashlib.sha256((root / "legacy.swift").read_bytes()).hexdigest() + "  legacy.swift\n"
    )
    (ev / "spec.hash").write_text(
        "sha256:" + hashlib.sha256((root / SPEC_REL).read_bytes()).hexdigest() + f"  {SPEC_REL}\n"
    )


def _normalize_legacy(text: str, root: pathlib.Path) -> str:
    text = text.replace(str(root), "<TEMP_ROOT>")
    return re.sub(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?[+-]\d{2}:\d{2}", "<RFC3339>", text)


def _side_effects(root: pathlib.Path) -> dict[str, Any]:
    """取得相對於 fixture commit 的可比較 Git/file side effects。"""
    status = _git(root, "status", "--porcelain=v1", "--untracked-files=all").stdout.splitlines()
    files: dict[str, dict[str, Any]] = {}
    for row in status:
        rel = row[3:]
        if " -> " in rel:
            rel = rel.split(" -> ", 1)[1]
        path = root / rel
        if path.is_symlink():
            files[rel] = {"kind": "symlink", "target": str(path.readlink())}
        elif path.is_file():
            payload = path.read_bytes()
            try:
                normalized = _normalize_legacy(payload.decode(), root).encode()
            except UnicodeDecodeError:
                normalized = payload
            files[rel] = {
                "kind": "file",
                "sha256": "sha256:" + hashlib.sha256(normalized).hexdigest(),
                "bytes": len(normalized),
            }
        else:
            files[rel] = {"kind": "absent"}
    return {"status": [row[:2] + " " + row[3:] for row in status], "files": files}


def _side_effect_delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    changed: dict[str, Any] = {}
    paths = set(before["files"]) | set(after["files"])
    for rel in sorted(paths):
        old = before["files"].get(rel)
        new = after["files"].get(rel)
        if old != new:
            changed[rel] = {"before": old, "after": new}
    return {"changed_files": changed}


def _e2e_actual(root: pathlib.Path, scenario: str) -> dict[str, Any]:
    """只彙整正式命令和 Git 的可觀察結果；不將 fixture 期望值寫回 actual。"""
    steps: list[dict[str, Any]] = []

    def step(script: str, *args: str, exit_key: str = "exit_code") -> dict[str, Any]:
        argv = [str(root / "scripts/gates" / script), *args]
        env = dict(os.environ)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        proc = subprocess.run(
            argv, cwd=root, capture_output=True, text=True,
            timeout=120 if script in {"red-capture", "dashboard"} else 60,
            env=env,
        )
        steps.append({
            "argv": argv,
            "exit": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        })
        return _parse_json_output(proc, exit_key)

    def evidence_step(storage: str) -> dict[str, Any]:
        before = _evidence_tree_snapshot(root / "specs/workflow-autonomy/evidence")
        result = step("evidence-check", str(SPEC_REL), storage)
        after = _evidence_tree_snapshot(root / "specs/workflow-autonomy/evidence")
        result["read_only"] = before == after
        return result

    def git_step(*args: str) -> subprocess.CompletedProcess[str]:
        argv = ["git", *args]
        proc = subprocess.run(argv, cwd=root, capture_output=True, text=True)
        steps.append({
            "argv": argv,
            "exit": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        })
        return proc

    def git_blob_matches(ref: str, raw_path: pathlib.Path) -> bool:
        """以 Git snapshot 的原始 bytes 對照 worktree raw artifact，並保存命令。"""
        argv = ["git", "show", ref]
        proc = subprocess.run(argv, cwd=root, capture_output=True)
        steps.append({
            "argv": argv,
            "exit": proc.returncode,
            "stdout": proc.stdout.decode(errors="replace"),
            "stderr": proc.stderr.decode(errors="replace"),
        })
        return proc.returncode == 0 and raw_path.is_file() and proc.stdout == raw_path.read_bytes()

    def includes_empty_static_stream(result: dict[str, Any], rel: str) -> bool:
        empty_digest = "sha256:" + hashlib.sha256(b"").hexdigest()
        return any(
            isinstance(row, dict)
            and row.get("path") == rel
            and row.get("bytes") == 0
            and row.get("sha256") == empty_digest
            for row in result.get("files", [])
        )

    def save_steps() -> None:
        _write_json(root / "specs/workflow-autonomy/evidence/e2e-commands.json", {
            "schema_version": 1,
            "scenario": scenario,
            "steps": steps,
        })

    if scenario == "SC-046":
        source_commit, source_tree = _approval_source_anchor(root)
        baseline, baseline_gates = _baseline_repo(root, source_commit, source_tree)
        _prepare_legacy_repo(root)
        _prepare_legacy_repo(baseline)
        before = (root / "specs/workflow-autonomy/evidence/autonomy.json").exists()
        commands = [
            ("config-check", (".",)),
            ("red-capture", (str(SPEC_REL),)),
            ("test-review", (str(SPEC_REL), "--mechanical-only")),
            ("traceability", (str(SPEC_REL),)),
            ("freeze-check", (str(SPEC_REL),)),
            ("findings", (str(SPEC_REL), "check")),
            ("loop", (str(SPEC_REL), "check")),
            ("dashboard", (str(SPEC_REL),)),
            ("runs", ()),
        ]
        comparisons: list[dict[str, Any]] = []
        status_exit = 2
        for script, args in commands:
            pair: dict[str, Any] = {"command": script}
            for label, repo, gates in (
                ("candidate", root, root / "scripts/gates"),
                ("baseline", baseline, baseline_gates),
            ):
                argv = [str(gates / script), *args]
                before_effects = _side_effects(repo)
                env = dict(os.environ)
                env["PYTHONDONTWRITEBYTECODE"] = "1"
                proc = subprocess.run(
                    argv, cwd=repo, capture_output=True, text=True, timeout=120, env=env
                )
                after_effects = _side_effects(repo)
                pair[label] = {
                    "argv": argv,
                    "exit": proc.returncode,
                    "stdout": proc.stdout,
                    "stderr": proc.stderr,
                    "side_effects": {
                        "before_status": before_effects["status"],
                        "after_status": after_effects["status"],
                        "delta": _side_effect_delta(before_effects, after_effects),
                    },
                }
                if label == "candidate" and script == "runs":
                    status_exit = proc.returncode
            candidate = pair["candidate"]
            oracle = pair["baseline"]
            pair["matches"] = (
                candidate["exit"] == oracle["exit"]
                and _normalize_legacy(candidate["stdout"], root)
                == _normalize_legacy(oracle["stdout"], baseline)
                and _normalize_legacy(candidate["stderr"], root)
                == _normalize_legacy(oracle["stderr"], baseline)
                and candidate["side_effects"]["delta"] == oracle["side_effects"]["delta"]
            )
            comparisons.append(pair)
        steps.extend(comparisons)
        red_path = root / "specs/workflow-autonomy/evidence/red.json"
        red_payload = json.loads(red_path.read_text()) if red_path.exists() else {}
        after = (root / "specs/workflow-autonomy/evidence/autonomy.json").exists()
        differences = sum(not pair["matches"] for pair in comparisons)
        save_steps()
        return {
            "legacy_parser_used": red_payload.get("runner") == "swift-testing",
            "autonomy_ledger_created": (not before) and after,
            "legacy_status_readable": status_exit == 0,
            "baseline_commands_compared": len(comparisons),
            "unapproved_differences": differences,
            "exit_code": 0 if differences == 0 else 1,
            "steps": steps,
        }

    config = step("config-check", ".")
    if config.get("status") != "passed" or not _gate_succeeded(config):
        save_steps()
        return {"exit_code": 1, "failed_step": "config-check", "steps": steps, "remote_actions": []}
    plan = step("autonomy", str(SPEC_REL), "plan", "--expect-generation", "0", "--id", "R-001",
                "--kind", "implementation", "--file", "scripts/gates/autonomy")
    if plan.get("status") != "planned" or not _gate_succeeded(plan):
        save_steps()
        return {"exit_code": 1, "failed_step": "autonomy plan", "steps": steps, "remote_actions": []}
    repro = root / "specs/workflow-autonomy/evidence/repro.log"
    repro.write_text("e2e evidence\n")
    complete = step("autonomy", str(SPEC_REL), "complete", "--expect-generation", "1", "--id", "R-001",
                    "--evidence", str(repro.relative_to(root)))
    if complete.get("status") != "complete" or not _gate_succeeded(complete):
        save_steps()
        return {"exit_code": 1, "failed_step": "autonomy complete", "steps": steps, "remote_actions": []}
    checked = step("autonomy", str(SPEC_REL), "check")
    if checked.get("status") != "passed" or not _gate_succeeded(checked):
        save_steps()
        return {"exit_code": 1, "failed_step": "autonomy check", "steps": steps, "remote_actions": []}
    red = step("red-capture", str(SPEC_REL), exit_key="gate_exit_code")
    review = step("test-review", str(SPEC_REL))
    trace = step("traceability", str(SPEC_REL))
    frozen = step("freeze-check", str(SPEC_REL))
    if not _gate_succeeded(red, "gate_exit_code") or any(not _gate_succeeded(item) for item in (review, trace, frozen)):
        save_steps()
        return {"exit_code": 1, "failed_step": "test evidence", "steps": steps, "remote_actions": []}
    smoke = step("smoke", str(SPEC_REL))
    g9 = step("findings", str(SPEC_REL), "dispatched", "--gate", "G9", "--status", "completed")
    g10 = step("findings", str(SPEC_REL), "dispatched", "--gate", "G10", "--status", "completed")
    if any(not _gate_succeeded(item) for item in (smoke, g9, g10)):
        save_steps()
        return {"exit_code": 1, "failed_step": "smoke/findings", "steps": steps, "remote_actions": []}
    local_status = step("runs", "--set", str(SPEC_REL), "--expect-generation", "0",
                        "--pipeline-state", "complete", "--stage", "S10", "--next-step", "commit",
                        "--delivery-state", "local")
    staged = git_step("add", "--", "specs/pipeline.yaml", "specs/workflow-autonomy")
    pre_commit_dashboard = step("dashboard", str(SPEC_REL), "--pre-commit")
    dashboard_staged = git_step(
        "add", "--", "specs/workflow-autonomy/evidence/dashboard.html",
        "specs/workflow-autonomy/evidence/dashboard.json",
    )
    index_tree = git_step("write-tree")
    index_oid = index_tree.stdout.strip()
    index_check = evidence_step("--index")
    empty_stream_rel = "specs/workflow-autonomy/evidence/static-red/entry-001.stderr.log"
    empty_stream_raw = root / empty_stream_rel
    red_payload = json.loads(
        (root / "specs/workflow-autonomy/evidence/red.json").read_text()
    )
    empty_stream_referenced = any(
        isinstance(row, dict) and row.get("stderr_path") == empty_stream_rel
        for row in red_payload.get("runner_results", [])
    )
    index_empty_included = includes_empty_static_stream(index_check, empty_stream_rel)
    index_empty_byte_exact = git_blob_matches(f":{empty_stream_rel}", empty_stream_raw)
    if index_check.get("status") != "passed" or not _gate_succeeded(index_check):
        save_steps()
        return {"exit_code": 1, "failed_step": "evidence-check --index", "steps": steps, "remote_actions": []}
    committed = git_step(
        "-c", "user.name=WorkflowFixture", "-c", "user.email=fixture@example.invalid",
        "commit", "-m", "workflow-autonomy-fixture",
    )
    head = git_step("rev-parse", "HEAD")
    head_oid = head.stdout.strip()
    commit_check = evidence_step("--commit")
    commit_empty_included = includes_empty_static_stream(commit_check, empty_stream_rel)
    commit_empty_byte_exact = git_blob_matches(f"HEAD:{empty_stream_rel}", empty_stream_raw)
    token = str(commit_check.get("token"))
    delivered = step("runs", "--set", str(SPEC_REL), "--expect-generation", "1", "--next-step", "pr_ready",
                     "--delivery-state", "committed", "--committed-evidence-token", token)
    delivery_dashboard = step("dashboard", str(SPEC_REL))
    restaged = git_step(
        "add", "--", "specs/workflow-autonomy/evidence/status.json",
        "specs/workflow-autonomy/evidence/dashboard.html",
        "specs/workflow-autonomy/evidence/dashboard.json",
    )
    rechecked = evidence_step("--index")
    rechecked_empty_included = includes_empty_static_stream(rechecked, empty_stream_rel)
    rechecked_empty_byte_exact = git_blob_matches(f":{empty_stream_rel}", empty_stream_raw)
    amended = git_step(
        "-c", "user.name=WorkflowFixture", "-c", "user.email=fixture@example.invalid",
        "commit", "--amend", "--no-edit",
    )
    final_commit = evidence_step("--commit")
    final_empty_included = includes_empty_static_stream(final_commit, empty_stream_rel)
    final_empty_byte_exact = git_blob_matches(f"HEAD:{empty_stream_rel}", empty_stream_raw)
    manifest = json.loads((root / "specs/workflow-autonomy/evidence/delivery.json").read_text())
    declared_paths = {str(row.get("path")) for row in manifest.get("files", []) if isinstance(row, dict)}
    direct_roots = {
        "specs/workflow-autonomy/evidence/delivery.json",
        "specs/workflow-autonomy/evidence/status.json",
        "specs/workflow-autonomy/evidence/dashboard.json",
    }
    final_paths = {
        str(row.get("path")) for row in final_commit.get("files", []) if isinstance(row, dict)
    }
    save_steps()
    return {
        "plan": plan.get("status"),
        "repair": complete.get("status"),
        "verify": checked.get("status"),
        "index_check": index_check.get("status"),
        "commit_check": commit_check.get("status"),
        "dashboard_root_created": (root / "specs/workflow-autonomy/evidence/dashboard.json").is_file(),
        "findings_root_created": (root / "specs/workflow-autonomy/evidence/findings.json").is_file(),
        "direct_roots_not_in_manifest": direct_roots.isdisjoint(declared_paths),
        "final_direct_roots_present": direct_roots <= final_paths,
        "token_stable_across_status_dashboard_amend": (
            bool(token) and token == rechecked.get("token") == final_commit.get("token")
        ),
        "evidence_check_read_only": all(
            item.get("read_only") is True for item in (index_check, commit_check, rechecked, final_commit)
        ),
        "empty_static_stream_included": empty_stream_referenced and all((
            index_empty_included,
            commit_empty_included,
            rechecked_empty_included,
            final_empty_included,
        )),
        "empty_static_stream_byte_exact": all((
            index_empty_byte_exact,
            commit_empty_byte_exact,
            rechecked_empty_byte_exact,
            final_empty_byte_exact,
        )),
        "ledger_schema": complete.get("schema_version"),
        "status_schema": local_status.get("schema_version"),
        "index_tree_oid_valid": len(index_oid) == 40 and all(c in "0123456789abcdef" for c in index_oid),
        "head_commit_oid_valid": len(head_oid) == 40 and all(c in "0123456789abcdef" for c in head_oid),
        "oids_distinct": index_oid != head_oid,
        "pr_ready": delivered.get("delivery", {}).get("state") == "committed" and final_commit.get("delivery_ready") is True,
        "remote_actions": [],
        "exit_code": 0 if all(_gate_succeeded(item) for item in (
            config, plan, complete, checked, review, trace, frozen, smoke, g9, g10,
            local_status, pre_commit_dashboard, index_check, commit_check, delivered,
            delivery_dashboard, rechecked, final_commit,
        )) and _gate_succeeded(red, "gate_exit_code") and all(
            item.returncode == 0 for item in (
                staged, dashboard_staged, index_tree, committed, head, restaged, amended,
            )
        )
        else 1,
        "steps": steps,
    }


def _actual(scenario: str, example: int, fixture: dict[str, Any]) -> dict[str, Any]:
    """只從隔離 repo 內正式 CLI 的 stdout、exit 與 artifacts 取得 actual。"""
    with tempfile.TemporaryDirectory(prefix=f"workflow-{scenario.lower()}-") as td:
        root = _new_repo(pathlib.Path(td))
        _configure(root, scenario, fixture)
        _approval_fixture(root, scenario)
        if scenario == "SC-039":
            repro = root / "specs/workflow-autonomy/evidence/repro.log"
            repro.parent.mkdir(parents=True, exist_ok=True)
            repro.write_text("e2e evidence\n")
        if scenario in {"SC-026", "SC-028", "SC-058"} or (
            scenario == "SC-047" and example == 4
        ):
            repro = root / "specs/workflow-autonomy/evidence/repro.log"
            repro.parent.mkdir(parents=True, exist_ok=True)
            repro.write_text("prior completion\n" if scenario == "SC-047" else "fixture evidence\n")
        if scenario == "SC-011":
            ev = root / "specs/workflow-autonomy/evidence"
            for name in (
                "delivery.json", "status.json", "tests.hash", "red.json", "test-review.json",
                "smoke.json", "findings.json", "autonomy.json", "dashboard.json",
            ):
                (ev / name).unlink(missing_ok=True)
        _commit(root)

        if scenario in {"SC-021", "SC-022", "SC-023", "SC-040"}:
            return _run(root, "config-check", ".")

        if scenario in {"SC-001", "SC-002", "SC-003", "SC-004", "SC-005", "SC-006", "SC-007", "SC-024",
                        "SC-025", "SC-026", "SC-027", "SC-028", "SC-029", "SC-030", "SC-041", "SC-042",
                        "SC-047", "SC-050", "SC-051", "SC-052", "SC-053", "SC-056", "SC-057", "SC-058", "SC-059"}:
            _seed_autonomy(root, scenario, fixture)
            _seed_frozen_artifacts(root, scenario, fixture)
            if scenario == "SC-053":
                return _run_with_head_drift(root, "autonomy", *_autonomy_args(scenario, fixture))
            return _run(root, "autonomy", *_autonomy_args(scenario, fixture))

        if scenario == "SC-009":
            tests_hash = root / "specs/workflow-autonomy/evidence/tests.hash"
            tests_hash.write_text("sha256:" + "0" * 64 + "  scripts/gates/tests/run\n")
            return _run(root, "freeze-check", str(SPEC_REL))

        if scenario in {"SC-008", "SC-010", "SC-011", "SC-012", "SC-031", "SC-043"}:
            if scenario == "SC-011":
                head_delivery = subprocess.run(
                    ["git", "cat-file", "-e", "HEAD:specs/workflow-autonomy/evidence/delivery.json"],
                    cwd=root,
                    capture_output=True,
                )
                if head_delivery.returncode == 0:
                    raise AssertionError("SC-011 fixture 的初始 HEAD 不得含 delivery evidence")
            mode = _delivery_fixture(root, scenario, fixture)
            _git(root, "add", "-A")
            if scenario == "SC-008":
                for rel in fixture["files"]:
                    ignored = subprocess.run(["git", "check-ignore", "-q", rel], cwd=root)
                    indexed = subprocess.run(
                        ["git", "ls-files", "--error-unmatch", "--", rel],
                        cwd=root,
                        capture_output=True,
                    )
                    if not (root / rel).is_file() or ignored.returncode != 0 or indexed.returncode == 0:
                        raise AssertionError(f"SC-008 fixture 不是 worktree-only ignored regular file: {rel}")
            if scenario == "SC-011":
                indexed_delivery = _git(
                    root, "ls-files", "--stage", "--", "specs/workflow-autonomy/evidence/delivery.json"
                ).stdout.strip()
                if not indexed_delivery:
                    raise AssertionError("SC-011 fixture 的完整 delivery evidence 未進 index")
            if mode == "--commit" and fixture.get("evidence_in_head") is not False:
                _git(root, "commit", "-qm", "delivery evidence")
            if fixture.get("fixture_snapshot_changed_before_decision"):
                drift_rel = str(fixture.get("path") or fixture["files"][0])
                return _run_with_index_drift(root, drift_rel, "evidence-check", str(SPEC_REL), mode)
            return _run(root, "evidence-check", str(SPEC_REL), mode)

        if scenario in {"SC-013", "SC-014", "SC-015", "SC-032", "SC-048"}:
            ev = root / "specs/workflow-autonomy/evidence"
            if scenario == "SC-015":
                _delivery_fixture(root, "SC-012", {
                    "evidence_in_head": True,
                    "status_generation": int(fixture["expect_generation"]),
                })
                _git(root, "add", "-A")
                _git(root, "commit", "-qm", "committed evidence token fixture")
                checked = _run(root, "evidence-check", str(SPEC_REL), "--commit")
                fixture = dict(fixture)
                fixture["fixture_committed_evidence_token"] = checked.get("token", "missing-token")
            if fixture.get("fixture_status_schema") == "legacy_or_absent":
                (ev / "status.json").unlink(missing_ok=True)
            elif fixture.get("fixture_actual_generation") is not None:
                _write_json(ev / "status.json", _status_record(int(fixture["fixture_actual_generation"])))
            elif fixture.get("expect_generation", 0) > 0:
                _write_json(ev / "status.json", _status_record(int(fixture["expect_generation"])))
            return _run(root, "runs", *_status_args(fixture))

        if scenario in {"SC-016", "SC-017", "SC-018", "SC-019", "SC-020", "SC-033", "SC-034", "SC-054"}:
            _static_fixture(root, scenario, example, fixture)
            result = _run(root, "red-capture", str(SPEC_REL), exit_key="gate_exit_code")
            red = root / "specs/workflow-autonomy/evidence/red.json"
            if red.exists():
                payload = json.loads(red.read_text())
                rows = payload.get("runner_results") or payload.get("tests") or []
                if rows:
                    result.update(rows[0])
                if payload.get("status") is not None:
                    result.setdefault("status", payload["status"])
                if payload.get("reason") is not None:
                    result.setdefault("reason", payload["reason"])
            return result

        if scenario in {"SC-035", "SC-055"}:
            _static_fixture(root, scenario, example, fixture)
            review = _run(root, "test-review", str(SPEC_REL), "--mechanical-only")
            if scenario == "SC-055":
                review["gate_exit_code"] = review["exit_code"]
                return review
            trace = _run(root, "traceability", str(SPEC_REL))
            frozen = _run(root, "freeze-check", str(SPEC_REL))
            return {
                "test_review": "passed" if review["exit_code"] == 0 else "failed",
                "traceability": "passed" if trace["exit_code"] == 0 else "failed",
                "tests_hash_current": frozen["exit_code"] == 0,
                "gate_exit_code": max(review["exit_code"], trace["exit_code"], frozen["exit_code"]),
                "exit_code": max(review["exit_code"], trace["exit_code"], frozen["exit_code"]),
            }

        if scenario in {"SC-036", "SC-037", "SC-038", "SC-044", "SC-045", "SC-049"}:
            args = _finding_fixture(root, scenario, fixture)
            script = "loop" if scenario == "SC-045" else "findings"
            if script == "findings" and len(args) >= 2 and args[1] in {"add", "revalidate"}:
                args = [args[1], args[0], *args[2:]]
            return _run(root, script, *args)

        if scenario in {"SC-039", "SC-046"}:
            return _e2e_actual(root, scenario)

        raise AssertionError(f"沒有正式 CLI fixture：{scenario}")


def _detail(scenario: str, example: int, expected: dict[str, Any], actual: dict[str, Any]) -> str:
    return (
        f"STATIC_ASSERTION: {scenario} example #{example} "
        f"expected={_canonical(expected)} actual={_canonical(actual)}"
    )


def _approved_sc039_commands() -> list[str]:
    """從 approved snapshot 取出 SC-039 的逐字命令清單。"""
    import yaml
    approved = yaml.safe_load(
        (SOURCE_ROOT / "specs/workflow-autonomy/evidence/spec.approved.yaml").read_text()
    )
    for requirement in approved.get("requirements") or []:
        for scenario in requirement.get("scenarios") or []:
            if scenario.get("id") == "SC-039":
                commands = scenario["examples"][0]["in"]["commands"]
                if not isinstance(commands, list) or not all(isinstance(item, str) for item in commands):
                    raise AssertionError("SC-039 approved commands schema 無效")
                return commands
    raise AssertionError("SC-039 approved commands 不存在")


def _case_name(scenario: str, example: int, fixture: dict[str, Any], action: str) -> str:
    """讓 harness 名稱本身完整呈現 approved given/when/then。"""
    import yaml
    approved = yaml.safe_load(
        (SOURCE_ROOT / "specs/workflow-autonomy/evidence/spec.approved.yaml").read_text()
    )
    for requirement in approved["requirements"]:
        for item in requirement["scenarios"]:
            if item["id"] == scenario:
                expected = item["examples"][example - 1]["out"]
                return (
                    f" given={_canonical(fixture)} when={action} "
                    f"then={_canonical(expected)}"
                )
    raise AssertionError(f"approved example 不存在：{scenario}#{example}")


def assertThat(actual: dict[str, Any], expected: dict[str, Any]) -> bool:
    """保留全部 failure，讓 direct bootstrap 能逐 example 對帳。"""
    def matches(got: Any, wanted: Any) -> bool:
        if isinstance(wanted, dict):
            if not isinstance(got, dict):
                return False
            for exit_key in ("exit_code", "gate_exit_code"):
                if exit_key in wanted and "reported_exit_code" in got:
                    if got["reported_exit_code"] != wanted[exit_key]:
                        return False
            return all(key in got and matches(got[key], value) for key, value in wanted.items())
        if isinstance(wanted, list):
            return isinstance(got, list) and len(got) == len(wanted) and all(
                matches(left, right) for left, right in zip(got, wanted)
            )
        return got == wanted

    return matches(actual, expected)


def _verify_comparator_exit_guards() -> None:
    """process exit 正確但 JSON 自報錯誤時，projection 必須維持 RED。"""
    for exit_key in ("exit_code", "gate_exit_code"):
        actual = {exit_key: 0, "reported_exit_code": 1}
        expected = {exit_key: 0}
        if assertThat(actual, expected):
            raise AssertionError(f"comparator 接受錯誤的 JSON 自報 {exit_key}")


def register(check: Callable[[str, bool, str], None], only: tuple[str, int] | None = None) -> int:
    """把 59 SC／85 examples 註冊進既有 harness；回傳實際執行數。"""
    _verify_comparator_exit_guards()
    selected = 0

    if only is None or only == ('SC-021', 1):
        selected += 1
        fixture = {'autonomy_key_present': False}
        actual = _actual('SC-021', 1, fixture)
        check("SC-021" + _case_name("SC-021", 1, fixture, "check_config"), assertThat(actual, {'status': 'passed', 'effective_version': 0, 'legacy_behavior_preserved': True, 'exit_code': 0}),
              _detail('SC-021', 1, {'status': 'passed', 'effective_version': 0, 'legacy_behavior_preserved': True, 'exit_code': 0}, actual))

    if only is None or only == ('SC-021', 2):
        selected += 1
        fixture = {'autonomy': {'version': 0}}
        actual = _actual('SC-021', 2, fixture)
        check("SC-021" + _case_name("SC-021", 2, fixture, "check_config"), assertThat(actual, {'status': 'passed', 'effective_version': 0, 'legacy_behavior_preserved': True, 'exit_code': 0}),
              _detail('SC-021', 2, {'status': 'passed', 'effective_version': 0, 'legacy_behavior_preserved': True, 'exit_code': 0}, actual))

    if only is None or only == ('SC-022', 1):
        selected += 1
        fixture = {'autonomy': {'version': 1}, 'models': {'draft': 'fable', 'review': 'fable', 'build': 'opus'}}
        actual = _actual('SC-022', 1, fixture)
        check("SC-022" + _case_name("SC-022", 1, fixture, "check_config"), assertThat(actual, {'status': 'passed', 'effective_version': 1, 'models': {'draft': 'fable', 'review': 'fable', 'build': 'opus'}, 'exit_code': 0}),
              _detail('SC-022', 1, {'status': 'passed', 'effective_version': 1, 'models': {'draft': 'fable', 'review': 'fable', 'build': 'opus'}, 'exit_code': 0}, actual))

    if only is None or only == ('SC-023', 1):
        selected += 1
        fixture = {'autonomy': {'version': 2}}
        actual = _actual('SC-023', 1, fixture)
        check("SC-023" + _case_name("SC-023", 1, fixture, "check_config"), assertThat(actual, {'status': 'rejected', 'reason': 'unsupported_autonomy_version', 'exit_code': 1}),
              _detail('SC-023', 1, {'status': 'rejected', 'reason': 'unsupported_autonomy_version', 'exit_code': 1}, actual))

    if only is None or only == ('SC-040', 1):
        selected += 1
        fixture = {'autonomy': None}
        actual = _actual('SC-040', 1, fixture)
        check("SC-040" + _case_name("SC-040", 1, fixture, "check_config"), assertThat(actual, {'status': 'rejected', 'reason': 'invalid_autonomy_schema', 'exit_code': 2}),
              _detail('SC-040', 1, {'status': 'rejected', 'reason': 'invalid_autonomy_schema', 'exit_code': 2}, actual))

    if only is None or only == ('SC-040', 2):
        selected += 1
        fixture = {'autonomy': {'version': 'one'}}
        actual = _actual('SC-040', 2, fixture)
        check("SC-040" + _case_name("SC-040", 2, fixture, "check_config"), assertThat(actual, {'status': 'rejected', 'reason': 'invalid_autonomy_schema', 'exit_code': 2}),
              _detail('SC-040', 2, {'status': 'rejected', 'reason': 'invalid_autonomy_schema', 'exit_code': 2}, actual))

    if only is None or only == ('SC-001', 1):
        selected += 1
        fixture = {'expect_generation': 0, 'id': 'R-001', 'kind': 'review_fix', 'files': ['scripts/gates/autonomy']}
        actual = _actual('SC-001', 1, fixture)
        check("SC-001" + _case_name("SC-001", 1, fixture, "plan_repair"), assertThat(actual, {'status': 'planned', 'blocked_on': None, 'may_continue': True, 'exit_code': 0}),
              _detail('SC-001', 1, {'status': 'planned', 'blocked_on': None, 'may_continue': True, 'exit_code': 0}, actual))

    if only is None or only == ('SC-001', 2):
        selected += 1
        fixture = {'expect_generation': 0, 'id': 'R-002', 'kind': 'implementation', 'files': ['scripts/gates/evidence-check']}
        actual = _actual('SC-001', 2, fixture)
        check("SC-001" + _case_name("SC-001", 2, fixture, "plan_repair"), assertThat(actual, {'status': 'planned', 'blocked_on': None, 'may_continue': True, 'exit_code': 0}),
              _detail('SC-001', 2, {'status': 'planned', 'blocked_on': None, 'may_continue': True, 'exit_code': 0}, actual))

    if only is None or only == ('SC-001', 3):
        selected += 1
        fixture = {'expect_generation': 0, 'id': 'R-003', 'kind': 'evidence', 'files': ['specs/workflow-autonomy/evidence/red.json']}
        actual = _actual('SC-001', 3, fixture)
        check("SC-001" + _case_name("SC-001", 3, fixture, "plan_repair"), assertThat(actual, {'status': 'planned', 'blocked_on': None, 'may_continue': True, 'exit_code': 0}),
              _detail('SC-001', 3, {'status': 'planned', 'blocked_on': None, 'may_continue': True, 'exit_code': 0}, actual))

    if only is None or only == ('SC-001', 4):
        selected += 1
        fixture = {'expect_generation': 0, 'id': 'R-004', 'kind': 'format', 'files': ['scripts/gates/tests/run']}
        actual = _actual('SC-001', 4, fixture)
        check("SC-001" + _case_name("SC-001", 4, fixture, "plan_repair"), assertThat(actual, {'status': 'planned', 'blocked_on': None, 'may_continue': True, 'exit_code': 0}),
              _detail('SC-001', 4, {'status': 'planned', 'blocked_on': None, 'may_continue': True, 'exit_code': 0}, actual))

    if only is None or only == ('SC-002', 1):
        selected += 1
        fixture = {'expect_generation': 0, 'id': 'R-001', 'kind': 'review_fix', 'files': ['unrelated/Product.swift']}
        actual = _actual('SC-002', 1, fixture)
        check("SC-002" + _case_name("SC-002", 1, fixture, "plan_repair"), assertThat(actual, {'status': 'rejected', 'reason': 'outside_approved_scope', 'exit_code': 1}),
              _detail('SC-002', 1, {'status': 'rejected', 'reason': 'outside_approved_scope', 'exit_code': 1}, actual))

    if only is None or only == ('SC-002', 2):
        selected += 1
        fixture = {'expect_generation': 0, 'id': 'R-001', 'kind': 'review_fix', 'files': ['scripts/gates/autonomy', 'unrelated/Product.swift']}
        actual = _actual('SC-002', 2, fixture)
        check("SC-002" + _case_name("SC-002", 2, fixture, "plan_repair"), assertThat(actual, {'status': 'rejected', 'reason': 'outside_approved_scope', 'exit_code': 1}),
              _detail('SC-002', 2, {'status': 'rejected', 'reason': 'outside_approved_scope', 'exit_code': 1}, actual))

    if only is None or only == ('SC-002', 3):
        selected += 1
        fixture = {'expect_generation': 0, 'id': 'R-001', 'kind': 'review_fix', 'files': ['../outside.py']}
        actual = _actual('SC-002', 3, fixture)
        check("SC-002" + _case_name("SC-002", 3, fixture, "plan_repair"), assertThat(actual, {'status': 'rejected', 'reason': 'outside_approved_scope', 'exit_code': 1}),
              _detail('SC-002', 3, {'status': 'rejected', 'reason': 'outside_approved_scope', 'exit_code': 1}, actual))

    if only is None or only == ('SC-002', 4):
        selected += 1
        fixture = {'expect_generation': 0, 'id': 'R-001', 'kind': 'review_fix', 'files': ['/tmp/outside.py']}
        actual = _actual('SC-002', 4, fixture)
        check("SC-002" + _case_name("SC-002", 4, fixture, "plan_repair"), assertThat(actual, {'status': 'rejected', 'reason': 'outside_approved_scope', 'exit_code': 1}),
              _detail('SC-002', 4, {'status': 'rejected', 'reason': 'outside_approved_scope', 'exit_code': 1}, actual))

    if only is None or only == ('SC-003', 1):
        selected += 1
        fixture = {'expect_generation': 0, 'id': 'R-001', 'kind': 'product_change', 'files': ['specs/workflow-autonomy/spec.yaml'], 'summary': 'change_expected_output'}
        actual = _actual('SC-003', 1, fixture)
        check("SC-003" + _case_name("SC-003", 1, fixture, "plan_repair"), assertThat(actual, {'status': 'blocked', 'blocked_on': 'owner', 'may_continue': False, 'exit_code': 1}),
              _detail('SC-003', 1, {'status': 'blocked', 'blocked_on': 'owner', 'may_continue': False, 'exit_code': 1}, actual))

    if only is None or only == ('SC-004', 1):
        selected += 1
        fixture = {'expect_generation': 0, 'id': 'R-001', 'kind': 'permission', 'files': ['scripts/gates/tests/run'], 'summary': 'required_test_command_permission_denied'}
        actual = _actual('SC-004', 1, fixture)
        check("SC-004" + _case_name("SC-004", 1, fixture, "plan_repair"), assertThat(actual, {'status': 'blocked', 'blocked_on': 'permission', 'bypass_attempted': False, 'exit_code': 1}),
              _detail('SC-004', 1, {'status': 'blocked', 'blocked_on': 'permission', 'bypass_attempted': False, 'exit_code': 1}, actual))

    if only is None or only == ('SC-024', 1):
        selected += 1
        fixture = {'expect_generation': 0, 'id': 'R-001', 'kind': 'implementation', 'files': ['scripts/gates/autonomy'], 'fixture_approved_snapshot': 'missing'}
        actual = _actual('SC-024', 1, fixture)
        check("SC-024" + _case_name("SC-024", 1, fixture, "plan_repair"), assertThat(actual, {'status': 'rejected', 'reason': 'missing_approved_snapshot', 'may_continue': False, 'exit_code': 1}),
              _detail('SC-024', 1, {'status': 'rejected', 'reason': 'missing_approved_snapshot', 'may_continue': False, 'exit_code': 1}, actual))

    if only is None or only == ('SC-025', 1):
        selected += 1
        fixture = {'expect_generation': 0, 'id': 'R-001', 'kind': 'review_fix', 'files': ['scripts/gates/autonomy'], 'fixture_spec_hash': 'drifted'}
        actual = _actual('SC-025', 1, fixture)
        check("SC-025" + _case_name("SC-025", 1, fixture, "plan_repair"), assertThat(actual, {'status': 'rejected', 'reason': 'spec_hash_mismatch', 'may_continue': False, 'exit_code': 1}),
              _detail('SC-025', 1, {'status': 'rejected', 'reason': 'spec_hash_mismatch', 'may_continue': False, 'exit_code': 1}, actual))

    if only is None or only == ('SC-026', 1):
        selected += 1
        fixture = {'expect_generation': 2, 'id': 'R-001', 'evidence': ['specs/workflow-autonomy/evidence/repro.log'], 'fixture_plan_version': 'current'}
        actual = _actual('SC-026', 1, fixture)
        check("SC-026" + _case_name("SC-026", 1, fixture, "complete_repair"), assertThat(actual, {'status': 'complete', 'evidence_saved': True, 'exit_code': 0}),
              _detail('SC-026', 1, {'status': 'complete', 'evidence_saved': True, 'exit_code': 0}, actual))

    if only is None or only == ('SC-027', 1):
        selected += 1
        fixture = {'expect_generation': 2, 'id': 'R-001', 'evidence': ['specs/workflow-autonomy/evidence/empty.log'], 'fixture_evidence': 'empty'}
        actual = _actual('SC-027', 1, fixture)
        check("SC-027" + _case_name("SC-027", 1, fixture, "complete_repair"), assertThat(actual, {'status': 'rejected', 'reason': 'invalid_completion_evidence', 'exit_code': 1}),
              _detail('SC-027', 1, {'status': 'rejected', 'reason': 'invalid_completion_evidence', 'exit_code': 1}, actual))

    if only is None or only == ('SC-028', 1):
        selected += 1
        fixture = {'repairs': [{'id': 'R-001', 'status': 'complete'}], 'blockers': []}
        actual = _actual('SC-028', 1, fixture)
        check("SC-028" + _case_name("SC-028", 1, fixture, "check_autonomy"), assertThat(actual, {'status': 'passed', 'may_continue': True, 'exit_code': 0}),
              _detail('SC-028', 1, {'status': 'passed', 'may_continue': True, 'exit_code': 0}, actual))

    if only is None or only == ('SC-041', 1):
        selected += 1
        fixture = {'repairs': [{'id': 'R-001', 'status': 'blocked', 'blocked_on': 'owner'}]}
        actual = _actual('SC-041', 1, fixture)
        check("SC-041" + _case_name("SC-041", 1, fixture, "check_autonomy"), assertThat(actual, {'status': 'blocked', 'may_continue': False, 'exit_code': 1}),
              _detail('SC-041', 1, {'status': 'blocked', 'may_continue': False, 'exit_code': 1}, actual))

    if only is None or only == ('SC-041', 2):
        selected += 1
        fixture = {'repairs': [{'id': 'R-002', 'status': 'planned', 'blocked_on': None}]}
        actual = _actual('SC-041', 2, fixture)
        check("SC-041" + _case_name("SC-041", 2, fixture, "check_autonomy"), assertThat(actual, {'status': 'blocked', 'may_continue': False, 'exit_code': 1}),
              _detail('SC-041', 2, {'status': 'blocked', 'may_continue': False, 'exit_code': 1}, actual))

    if only is None or only == ('SC-047', 1):
        selected += 1
        fixture = {'expect_generation': 2, 'id': 'R-999', 'evidence': ['specs/workflow-autonomy/evidence/repro.log'], 'fixture_existing_ids': ['R-001']}
        actual = _actual('SC-047', 1, fixture)
        check("SC-047" + _case_name("SC-047", 1, fixture, "complete_repair"), assertThat(actual, {'status': 'rejected', 'reason': 'invalid_repair_transition', 'written': False, 'exit_code': 1}),
              _detail('SC-047', 1, {'status': 'rejected', 'reason': 'invalid_repair_transition', 'written': False, 'exit_code': 1}, actual))

    if only is None or only == ('SC-047', 2):
        selected += 1
        fixture = {'expect_generation': 2, 'id': 'R-001', 'evidence': ['specs/workflow-autonomy/evidence/repro.log'], 'fixture_current_status': 'blocked'}
        actual = _actual('SC-047', 2, fixture)
        check("SC-047" + _case_name("SC-047", 2, fixture, "complete_repair"), assertThat(actual, {'status': 'rejected', 'reason': 'invalid_repair_transition', 'written': False, 'exit_code': 1}),
              _detail('SC-047', 2, {'status': 'rejected', 'reason': 'invalid_repair_transition', 'written': False, 'exit_code': 1}, actual))

    if only is None or only == ('SC-047', 3):
        selected += 1
        fixture = {'expect_generation': 2, 'id': 'R-001', 'evidence': ['specs/workflow-autonomy/evidence/repro.log'], 'fixture_plan_version': 'stale'}
        actual = _actual('SC-047', 3, fixture)
        check("SC-047" + _case_name("SC-047", 3, fixture, "complete_repair"), assertThat(actual, {'status': 'rejected', 'reason': 'invalid_repair_transition', 'written': False, 'exit_code': 1}),
              _detail('SC-047', 3, {'status': 'rejected', 'reason': 'invalid_repair_transition', 'written': False, 'exit_code': 1}, actual))

    if only is None or only == ('SC-047', 4):
        selected += 1
        fixture = {'expect_generation': 2, 'id': 'R-001', 'evidence': ['specs/workflow-autonomy/evidence/other.log'], 'fixture_existing_completion_evidence': ['specs/workflow-autonomy/evidence/repro.log']}
        actual = _actual('SC-047', 4, fixture)
        check("SC-047" + _case_name("SC-047", 4, fixture, "complete_repair"), assertThat(actual, {'status': 'rejected', 'reason': 'invalid_repair_transition', 'written': False, 'exit_code': 1}),
              _detail('SC-047', 4, {'status': 'rejected', 'reason': 'invalid_repair_transition', 'written': False, 'exit_code': 1}, actual))

    if only is None or only == ('SC-050', 1):
        selected += 1
        fixture = {'expect_generation': 0, 'id': 'R-001', 'kind': 'review_fix', 'files': ['scripts/gates/autonomy'], 'fixture_existing_request': 'identical'}
        actual = _actual('SC-050', 1, fixture)
        check("SC-050" + _case_name("SC-050", 1, fixture, "plan_repair"), assertThat(actual, {'status': 'planned', 'idempotent': True, 'generation': 1, 'exit_code': 0}),
              _detail('SC-050', 1, {'status': 'planned', 'idempotent': True, 'generation': 1, 'exit_code': 0}, actual))

    if only is None or only == ('SC-056', 1):
        selected += 1
        fixture = {'expect_generation': 1, 'id': 'R-001', 'kind': 'implementation', 'files': ['scripts/gates/evidence-check'], 'fixture_existing_request': 'different'}
        actual = _actual('SC-056', 1, fixture)
        check("SC-056" + _case_name("SC-056", 1, fixture, "plan_repair"), assertThat(actual, {'status': 'rejected', 'reason': 'repair_id_conflict', 'written': False, 'generation': 1, 'exit_code': 1}),
              _detail('SC-056', 1, {'status': 'rejected', 'reason': 'repair_id_conflict', 'written': False, 'generation': 1, 'exit_code': 1}, actual))

    if only is None or only == ('SC-057', 1):
        selected += 1
        fixture = {'argv': ['plan', '--expect-generation', '0', '--id', 'R-001', '--kind', 'review_fix']}
        actual = _actual('SC-057', 1, fixture)
        check("SC-057" + _case_name("SC-057", 1, fixture, "plan_repair"), assertThat(actual, {'status': 'rejected', 'reason': 'invalid_cli', 'written': False, 'exit_code': 2}),
              _detail('SC-057', 1, {'status': 'rejected', 'reason': 'invalid_cli', 'written': False, 'exit_code': 2}, actual))

    if only is None or only == ('SC-051', 1):
        selected += 1
        fixture = {'expect_generation': 2, 'id': 'R-002', 'kind': 'implementation', 'files': ['scripts/gates/autonomy'], 'fixture_actual_generation': 3}
        actual = _actual('SC-051', 1, fixture)
        check("SC-051" + _case_name("SC-051", 1, fixture, "plan_repair"), assertThat(actual, {'status': 'conflict', 'expected_generation': 2, 'actual_generation': 3, 'written': False, 'exit_code': 1}),
              _detail('SC-051', 1, {'status': 'conflict', 'expected_generation': 2, 'actual_generation': 3, 'written': False, 'exit_code': 1}, actual))

    if only is None or only == ('SC-058', 1):
        selected += 1
        fixture = {'expect_generation': 1, 'id': 'R-001', 'evidence': ['specs/workflow-autonomy/evidence/repro.log'], 'fixture_preexisting_dirty_path': 'docs/preexisting.md', 'fixture_mutate_after_plan': True}
        actual = _actual('SC-058', 1, fixture)
        check("SC-058" + _case_name("SC-058", 1, fixture, "complete_repair"), assertThat(actual, {'status': 'rejected', 'reason': 'changed_path_outside_repair', 'written': False, 'exit_code': 1}),
              _detail('SC-058', 1, {'status': 'rejected', 'reason': 'changed_path_outside_repair', 'written': False, 'exit_code': 1}, actual))

    if only is None or only == ('SC-059', 1):
        selected += 1
        fixture = {'expect_generation': 1, 'id': 'R-001', 'evidence': ['unrelated/changed.py']}
        actual = _actual('SC-059', 1, fixture)
        check("SC-059" + _case_name("SC-059", 1, fixture, "complete_repair"), assertThat(actual, {'status': 'rejected', 'reason': 'invalid_completion_evidence', 'written': False, 'exit_code': 1}),
              _detail('SC-059', 1, {'status': 'rejected', 'reason': 'invalid_completion_evidence', 'written': False, 'exit_code': 1}, actual))

    if only is None or only == ('SC-005', 1):
        selected += 1
        fixture = {'expect_generation': 1, 'id': 'R-001', 'kind': 'frozen_test', 'action': 'complete', 'evidence': ['review.json']}
        actual = _actual('SC-005', 1, fixture)
        check("SC-005" + _case_name("SC-005", 1, fixture, "complete_repair"), assertThat(actual, {'status': 'rejected', 'required_action': 'verify_tests', 'exit_code': 1}),
              _detail('SC-005', 1, {'status': 'rejected', 'required_action': 'verify_tests', 'exit_code': 1}, actual))

    if only is None or only == ('SC-005', 2):
        selected += 1
        fixture = {'expect_generation': 1, 'id': 'R-001', 'fixture_review': 'missing', 'fixture_red': 'fresh', 'fixture_tests_hash': 'current'}
        actual = _actual('SC-005', 2, fixture)
        check("SC-005" + _case_name("SC-005", 2, fixture, "complete_repair"), assertThat(actual, {'status': 'rejected', 'required_action': 'verify_tests', 'exit_code': 1}),
              _detail('SC-005', 2, {'status': 'rejected', 'required_action': 'verify_tests', 'exit_code': 1}, actual))

    if only is None or only == ('SC-005', 3):
        selected += 1
        fixture = {'expect_generation': 1, 'id': 'R-001', 'fixture_review': 'pass', 'fixture_red': 'missing', 'fixture_tests_hash': 'current'}
        actual = _actual('SC-005', 3, fixture)
        check("SC-005" + _case_name("SC-005", 3, fixture, "complete_repair"), assertThat(actual, {'status': 'rejected', 'required_action': 'verify_tests', 'exit_code': 1}),
              _detail('SC-005', 3, {'status': 'rejected', 'required_action': 'verify_tests', 'exit_code': 1}, actual))

    if only is None or only == ('SC-005', 4):
        selected += 1
        fixture = {'expect_generation': 1, 'id': 'R-001', 'fixture_review': 'pass', 'fixture_red': 'fresh', 'fixture_tests_hash': 'missing'}
        actual = _actual('SC-005', 4, fixture)
        check("SC-005" + _case_name("SC-005", 4, fixture, "complete_repair"), assertThat(actual, {'status': 'rejected', 'required_action': 'verify_tests', 'exit_code': 1}),
              _detail('SC-005', 4, {'status': 'rejected', 'required_action': 'verify_tests', 'exit_code': 1}, actual))

    if only is None or only == ('SC-006', 1):
        selected += 1
        fixture = {'expect_generation': 1, 'id': 'R-001', 'fixture_review': 'independent_pass', 'fixture_assertion': 'preserved', 'fixture_red': 'fresh', 'fixture_tests_hash': 'current'}
        actual = _actual('SC-006', 1, fixture)
        check("SC-006" + _case_name("SC-006", 1, fixture, "verify_tests"), assertThat(actual, {'status': 'complete', 'test_contract_rebuilt': True, 'exit_code': 0}),
              _detail('SC-006', 1, {'status': 'complete', 'test_contract_rebuilt': True, 'exit_code': 0}, actual))

    if only is None or only == ('SC-007', 1):
        selected += 1
        fixture = {'expect_generation': 1, 'id': 'R-001', 'fixture_review': 'blocking', 'fixture_assertion': 'preserved'}
        actual = _actual('SC-007', 1, fixture)
        check("SC-007" + _case_name("SC-007", 1, fixture, "verify_tests"), assertThat(actual, {'status': 'rejected', 'test_contract_rebuilt': False, 'exit_code': 1}),
              _detail('SC-007', 1, {'status': 'rejected', 'test_contract_rebuilt': False, 'exit_code': 1}, actual))

    if only is None or only == ('SC-029', 1):
        selected += 1
        fixture = {'expect_generation': 1, 'id': 'R-001', 'fixture_review': 'independent_pass', 'fixture_red': 'stale', 'fixture_tests_hash': 'current'}
        actual = _actual('SC-029', 1, fixture)
        check("SC-029" + _case_name("SC-029", 1, fixture, "verify_tests"), assertThat(actual, {'status': 'rejected', 'reason': 'stale_red_evidence', 'test_contract_rebuilt': False, 'exit_code': 1}),
              _detail('SC-029', 1, {'status': 'rejected', 'reason': 'stale_red_evidence', 'test_contract_rebuilt': False, 'exit_code': 1}, actual))

    if only is None or only == ('SC-030', 1):
        selected += 1
        fixture = {'expect_generation': 1, 'id': 'R-001', 'fixture_review': 'same_actor', 'fixture_assertion': 'preserved'}
        actual = _actual('SC-030', 1, fixture)
        check("SC-030" + _case_name("SC-030", 1, fixture, "verify_tests"), assertThat(actual, {'status': 'rejected', 'reason': 'invalid_independent_review', 'test_contract_rebuilt': False, 'exit_code': 1}),
              _detail('SC-030', 1, {'status': 'rejected', 'reason': 'invalid_independent_review', 'test_contract_rebuilt': False, 'exit_code': 1}, actual))

    if only is None or only == ('SC-042', 1):
        selected += 1
        fixture = {'expect_generation': 1, 'id': 'R-001', 'fixture_review': 'independent_pass', 'fixture_assertion': 'weakened'}
        actual = _actual('SC-042', 1, fixture)
        check("SC-042" + _case_name("SC-042", 1, fixture, "verify_tests"), assertThat(actual, {'status': 'rejected', 'reason': 'assertion_weakened', 'test_contract_rebuilt': False, 'exit_code': 1}),
              _detail('SC-042', 1, {'status': 'rejected', 'reason': 'assertion_weakened', 'test_contract_rebuilt': False, 'exit_code': 1}, actual))

    if only is None or only == ('SC-052', 1):
        selected += 1
        fixture = {'expect_generation': 1, 'id': 'R-001', 'fixture_review': 'independent_pass', 'fixture_red': 'fresh', 'fixture_tests_hash': 'mismatched'}
        actual = _actual('SC-052', 1, fixture)
        check("SC-052" + _case_name("SC-052", 1, fixture, "verify_tests"), assertThat(actual, {'status': 'rejected', 'reason': 'tests_hash_mismatch', 'test_contract_rebuilt': False, 'exit_code': 1}),
              _detail('SC-052', 1, {'status': 'rejected', 'reason': 'tests_hash_mismatch', 'test_contract_rebuilt': False, 'exit_code': 1}, actual))

    if only is None or only == ('SC-053', 1):
        selected += 1
        fixture = {'expect_generation': 1, 'id': 'R-001', 'fixture_review': 'independent_pass', 'fixture_red': 'fresh', 'fixture_tests_hash': 'current', 'fixture_final_snapshot': 'drifted'}
        actual = _actual('SC-053', 1, fixture)
        check("SC-053" + _case_name("SC-053", 1, fixture, "verify_tests"), assertThat(actual, {'status': 'rejected', 'reason': 'snapshot_drift', 'test_contract_rebuilt': False, 'exit_code': 1}),
              _detail('SC-053', 1, {'status': 'rejected', 'reason': 'snapshot_drift', 'test_contract_rebuilt': False, 'exit_code': 1}, actual))

    if only is None or only == ('SC-008', 1):
        selected += 1
        fixture = {'files': ['domain.log', 'data.log', 'view.log', 'integration.log'], 'tracked': False}
        actual = _actual('SC-008', 1, fixture)
        check("SC-008" + _case_name("SC-008", 1, fixture, "check_index_evidence"), assertThat(actual, {'status': 'failed', 'files': [], 'invalid_files': [{'path': 'data.log', 'reason': 'missing'}, {'path': 'domain.log', 'reason': 'missing'}, {'path': 'integration.log', 'reason': 'missing'}, {'path': 'view.log', 'reason': 'missing'}], 'exit_code': 1}),
              _detail('SC-008', 1, {'status': 'failed', 'files': [], 'invalid_files': [{'path': 'data.log', 'reason': 'missing'}, {'path': 'domain.log', 'reason': 'missing'}, {'path': 'integration.log', 'reason': 'missing'}, {'path': 'view.log', 'reason': 'missing'}], 'exit_code': 1}, actual))

    if only is None or only == ('SC-009', 1):
        selected += 1
        fixture = {'frozen_hash': 'before_format', 'current_hash': 'after_format'}
        actual = _actual('SC-009', 1, fixture)
        check("SC-009" + _case_name("SC-009", 1, fixture, "verify_frozen_tests"), assertThat(actual, {'status': 'failed', 'reason': 'fingerprint_mismatch', 'exit_code': 1}),
              _detail('SC-009', 1, {'status': 'failed', 'reason': 'fingerprint_mismatch', 'exit_code': 1}, actual))

    if only is None or only == ('SC-010', 1):
        selected += 1
        fixture = {'tracked': True, 'index_matches_worktree': True}
        actual = _actual('SC-010', 1, fixture)
        check("SC-010" + _case_name("SC-010", 1, fixture, "check_index_evidence"), assertThat(actual, {'status': 'passed', 'storage': 'index', 'exit_code': 0}),
              _detail('SC-010', 1, {'status': 'passed', 'storage': 'index', 'exit_code': 0}, actual))

    if only is None or only == ('SC-011', 1):
        selected += 1
        fixture = {'gates_green': True, 'evidence_in_head': False}
        actual = _actual('SC-011', 1, fixture)
        check("SC-011" + _case_name("SC-011", 1, fixture, "check_committed_evidence"), assertThat(actual, {'status': 'failed', 'delivery_ready': False, 'exit_code': 1}),
              _detail('SC-011', 1, {'status': 'failed', 'delivery_ready': False, 'exit_code': 1}, actual))

    if only is None or only == ('SC-012', 1):
        selected += 1
        fixture = {'evidence_in_head': True, 'head_matches_worktree': True}
        actual = _actual('SC-012', 1, fixture)
        check("SC-012" + _case_name("SC-012", 1, fixture, "check_committed_evidence"), assertThat(actual, {'status': 'passed', 'delivery_ready': True, 'exit_code': 0}),
              _detail('SC-012', 1, {'status': 'passed', 'delivery_ready': True, 'exit_code': 0}, actual))

    if only is None or only == ('SC-031', 1):
        selected += 1
        fixture = {'path': 'specs/workflow-autonomy/evidence/missing.log', 'exists': False}
        actual = _actual('SC-031', 1, fixture)
        check("SC-031" + _case_name("SC-031", 1, fixture, "check_delivery_evidence"), assertThat(actual, {'status': 'failed', 'invalid_files': [{'path': 'specs/workflow-autonomy/evidence/missing.log', 'reason': 'missing'}], 'exit_code': 1}),
              _detail('SC-031', 1, {'status': 'failed', 'invalid_files': [{'path': 'specs/workflow-autonomy/evidence/missing.log', 'reason': 'missing'}], 'exit_code': 1}, actual))

    if only is None or only == ('SC-031', 2):
        selected += 1
        fixture = {'path': 'specs/workflow-autonomy/evidence/empty.log', 'bytes': 0}
        actual = _actual('SC-031', 2, fixture)
        check("SC-031" + _case_name("SC-031", 2, fixture, "check_delivery_evidence"), assertThat(actual, {'status': 'failed', 'invalid_files': [{'path': 'specs/workflow-autonomy/evidence/empty.log', 'reason': 'empty'}], 'exit_code': 1}),
              _detail('SC-031', 2, {'status': 'failed', 'invalid_files': [{'path': 'specs/workflow-autonomy/evidence/empty.log', 'reason': 'empty'}], 'exit_code': 1}, actual))

    if only is None or only == ('SC-031', 3):
        selected += 1
        fixture = {'path': 'specs/workflow-autonomy/evidence/stale.log', 'fingerprint_current': False}
        actual = _actual('SC-031', 3, fixture)
        check("SC-031" + _case_name("SC-031", 3, fixture, "check_delivery_evidence"), assertThat(actual, {'status': 'failed', 'invalid_files': [{'path': 'specs/workflow-autonomy/evidence/stale.log', 'reason': 'hash_mismatch'}], 'exit_code': 1}),
              _detail('SC-031', 3, {'status': 'failed', 'invalid_files': [{'path': 'specs/workflow-autonomy/evidence/stale.log', 'reason': 'hash_mismatch'}], 'exit_code': 1}, actual))

    if only is None or only == ('SC-031', 4):
        selected += 1
        fixture = {'path': '../outside.log', 'inside_repo': False}
        actual = _actual('SC-031', 4, fixture)
        check("SC-031" + _case_name("SC-031", 4, fixture, "check_delivery_evidence"), assertThat(actual, {'status': 'failed', 'invalid_files': [{'path': '../outside.log', 'reason': 'outside_repo'}], 'exit_code': 1}),
              _detail('SC-031', 4, {'status': 'failed', 'invalid_files': [{'path': '../outside.log', 'reason': 'outside_repo'}], 'exit_code': 1}, actual))

    if only is None or only == ('SC-031', 5):
        selected += 1
        fixture = {'path': 'specs/workflow-autonomy/evidence/link.log', 'fixture_file_type': 'symlink'}
        actual = _actual('SC-031', 5, fixture)
        check("SC-031" + _case_name("SC-031", 5, fixture, "check_delivery_evidence"), assertThat(actual, {'status': 'failed', 'invalid_files': [{'path': 'specs/workflow-autonomy/evidence/link.log', 'reason': 'symlink_or_nonregular'}], 'exit_code': 1}),
              _detail('SC-031', 5, {'status': 'failed', 'invalid_files': [{'path': 'specs/workflow-autonomy/evidence/link.log', 'reason': 'symlink_or_nonregular'}], 'exit_code': 1}, actual))

    if only is None or only == ('SC-031', 6):
        selected += 1
        fixture = {'path': 'specs/workflow-autonomy/evidence/drift.log', 'fixture_snapshot_changed_before_decision': True}
        actual = _actual('SC-031', 6, fixture)
        check("SC-031" + _case_name("SC-031", 6, fixture, "check_delivery_evidence"), assertThat(actual, {'status': 'failed', 'invalid_files': [{'path': 'specs/workflow-autonomy/evidence/drift.log', 'reason': 'snapshot_mismatch'}], 'exit_code': 1}),
              _detail('SC-031', 6, {'status': 'failed', 'invalid_files': [{'path': 'specs/workflow-autonomy/evidence/drift.log', 'reason': 'snapshot_mismatch'}], 'exit_code': 1}, actual))

    if only is None or only == ('SC-043', 1):
        selected += 1
        fixture = {'manifest_files': [], 'referenced_files': []}
        actual = _actual('SC-043', 1, fixture)
        check("SC-043" + _case_name("SC-043", 1, fixture, "check_delivery_evidence"), assertThat(actual, {'status': 'failed', 'reason': 'empty_delivery_set', 'exit_code': 1}),
              _detail('SC-043', 1, {'status': 'failed', 'reason': 'empty_delivery_set', 'exit_code': 1}, actual))

    if only is None or only == ('SC-013', 1):
        selected += 1
        fixture = {'expect_generation': 0, 'pipeline_state': 'running', 'stage': 'S8', 'next_step': 'run_tests', 'delivery_state': 'local', 'report_state': 'pending', 'fixture_status_schema': 'legacy_or_absent'}
        actual = _actual('SC-013', 1, fixture)
        check("SC-013" + _case_name("SC-013", 1, fixture, "set_status"), assertThat(actual, {'schema_version': 1, 'generation': 1, 'pipeline_state': 'running', 'stage': 'S8', 'next_step': 'run_tests', 'blocked_on': None, 'delivery': {'state': 'local', 'ref': None}, 'report': {'state': 'pending', 'reason': None}, 'exit_code': 0}),
              _detail('SC-013', 1, {'schema_version': 1, 'generation': 1, 'pipeline_state': 'running', 'stage': 'S8', 'next_step': 'run_tests', 'blocked_on': None, 'delivery': {'state': 'local', 'ref': None}, 'report': {'state': 'pending', 'reason': None}, 'exit_code': 0}, actual))

    if only is None or only == ('SC-014', 1):
        selected += 1
        fixture = {'expect_generation': 4, 'pipeline_state': 'running', 'blocked_on': None, 'report_state': 'denied', 'report_reason': 'platform_denied'}
        actual = _actual('SC-014', 1, fixture)
        check("SC-014" + _case_name("SC-014", 1, fixture, "set_status"), assertThat(actual, {'pipeline_state': 'running', 'blocked_on': None, 'delivery': {'state': 'local', 'ref': None}, 'report': {'state': 'denied', 'reason': 'platform_denied'}, 'retry_via_other_channel': False, 'exit_code': 0}),
              _detail('SC-014', 1, {'pipeline_state': 'running', 'blocked_on': None, 'delivery': {'state': 'local', 'ref': None}, 'report': {'state': 'denied', 'reason': 'platform_denied'}, 'retry_via_other_channel': False, 'exit_code': 0}, actual))

    if only is None or only == ('SC-015', 1):
        selected += 1
        fixture = {'expect_generation': 5, 'delivery_state': 'pr_open', 'delivery_ref': 'https://github.example/pull/17', 'fixture_committed_evidence_token': 'generated_from_payload', 'fixture_token_matches_head': True}
        actual = _actual('SC-015', 1, fixture)
        check("SC-015" + _case_name("SC-015", 1, fixture, "set_delivery_status"), assertThat(actual, {'delivery': {'state': 'pr_open', 'ref': 'https://github.example/pull/17'}, 'owner_merge_required': True, 'exit_code': 0}),
              _detail('SC-015', 1, {'delivery': {'state': 'pr_open', 'ref': 'https://github.example/pull/17'}, 'owner_merge_required': True, 'exit_code': 0}, actual))

    if only is None or only == ('SC-032', 1):
        selected += 1
        fixture = {'expect_generation': 1, 'pipeline_state': 'flying', 'delivery_state': 'local'}
        actual = _actual('SC-032', 1, fixture)
        check("SC-032" + _case_name("SC-032", 1, fixture, "set_status"), assertThat(actual, {'status': 'rejected', 'reason': 'invalid_status_schema', 'written': False, 'exit_code': 2}),
              _detail('SC-032', 1, {'status': 'rejected', 'reason': 'invalid_status_schema', 'written': False, 'exit_code': 2}, actual))

    if only is None or only == ('SC-032', 2):
        selected += 1
        fixture = {'expect_generation': 1, 'pipeline_state': 'waiting', 'delivery_state': 'pr_open', 'delivery_ref': None}
        actual = _actual('SC-032', 2, fixture)
        check("SC-032" + _case_name("SC-032", 2, fixture, "set_status"), assertThat(actual, {'status': 'rejected', 'reason': 'invalid_status_schema', 'written': False, 'exit_code': 2}),
              _detail('SC-032', 2, {'status': 'rejected', 'reason': 'invalid_status_schema', 'written': False, 'exit_code': 2}, actual))

    if only is None or only == ('SC-048', 1):
        selected += 1
        fixture = {'expect_generation': 5, 'pipeline_state': 'waiting', 'fixture_actual_generation': 6}
        actual = _actual('SC-048', 1, fixture)
        check("SC-048" + _case_name("SC-048", 1, fixture, "set_status"), assertThat(actual, {'status': 'conflict', 'expected_generation': 5, 'actual_generation': 6, 'written': False, 'exit_code': 1}),
              _detail('SC-048', 1, {'status': 'conflict', 'expected_generation': 5, 'actual_generation': 6, 'written': False, 'exit_code': 1}, actual))

    if only is None or only == ('SC-016', 1):
        selected += 1
        fixture = {'argv': ['python3', 'checker.py'], 'exit_code': 1, 'output': 'STATIC_ASSERTION: expected blocked'}
        actual = _actual('SC-016', 1, fixture)
        check("SC-016" + _case_name("SC-016", 1, fixture, "capture_red"), assertThat(actual, {'failure_class': 'assertion', 'red_valid': True, 'gate_exit_code': 0}),
              _detail('SC-016', 1, {'failure_class': 'assertion', 'red_valid': True, 'gate_exit_code': 0}, actual))

    if only is None or only == ('SC-017', 1):
        selected += 1
        fixture = {'argv': ['python3', 'checker.py'], 'exit_code': 0}
        actual = _actual('SC-017', 1, fixture)
        check("SC-017" + _case_name("SC-017", 1, fixture, "capture_red"), assertThat(actual, {'failure_class': 'passed', 'red_valid': False, 'gate_exit_code': 1}),
              _detail('SC-017', 1, {'failure_class': 'passed', 'red_valid': False, 'gate_exit_code': 1}, actual))

    if only is None or only == ('SC-018', 1):
        selected += 1
        fixture = {'argv': ['python3', 'checker.py'], 'exit_code': 2}
        actual = _actual('SC-018', 1, fixture)
        check("SC-018" + _case_name("SC-018", 1, fixture, "capture_red"), assertThat(actual, {'failure_class': 'error', 'red_valid': False, 'gate_exit_code': 1}),
              _detail('SC-018', 1, {'failure_class': 'error', 'red_valid': False, 'gate_exit_code': 1}, actual))

    if only is None or only == ('SC-019', 1):
        selected += 1
        fixture = {'approved_examples': [1, 2], 'checked_examples': [1]}
        actual = _actual('SC-019', 1, fixture)
        check("SC-019" + _case_name("SC-019", 1, fixture, "capture_red"), assertThat(actual, {'status': 'failed', 'reason': 'missing_example_check', 'gate_exit_code': 1}),
              _detail('SC-019', 1, {'status': 'failed', 'reason': 'missing_example_check', 'gate_exit_code': 1}, actual))

    if only is None or only == ('SC-020', 1):
        selected += 1
        fixture = {'pipeline_runner': 'swift_testing', 'entry_runner': None}
        actual = _actual('SC-020', 1, fixture)
        check("SC-020" + _case_name("SC-020", 1, fixture, "capture_red"), assertThat(actual, {'legacy_parser_used': True, 'behavior_preserved': True, 'gate_exit_code': 0}),
              _detail('SC-020', 1, {'legacy_parser_used': True, 'behavior_preserved': True, 'gate_exit_code': 0}, actual))

    if only is None or only == ('SC-033', 1):
        selected += 1
        fixture = {'argv': ['python3', 'checker.py'], 'timeout_seconds': 1, 'timed_out': True}
        actual = _actual('SC-033', 1, fixture)
        check("SC-033" + _case_name("SC-033", 1, fixture, "capture_red"), assertThat(actual, {'failure_class': 'hang', 'red_valid': False, 'gate_exit_code': 1}),
              _detail('SC-033', 1, {'failure_class': 'hang', 'red_valid': False, 'gate_exit_code': 1}, actual))

    if only is None or only == ('SC-034', 1):
        selected += 1
        fixture = {'argv': [], 'timeout_seconds': 30, 'checks': []}
        actual = _actual('SC-034', 1, fixture)
        check("SC-034" + _case_name("SC-034", 1, fixture, "capture_red"), assertThat(actual, {'status': 'rejected', 'reason': 'invalid_static_schema', 'gate_exit_code': 2}),
              _detail('SC-034', 1, {'status': 'rejected', 'reason': 'invalid_static_schema', 'gate_exit_code': 2}, actual))

    if only is None or only == ('SC-034', 2):
        selected += 1
        fixture = {'approved_examples': [1, 2], 'checked_examples': [1, 1]}
        actual = _actual('SC-034', 2, fixture)
        check("SC-034" + _case_name("SC-034", 2, fixture, "capture_red"), assertThat(actual, {'status': 'rejected', 'reason': 'invalid_static_schema', 'gate_exit_code': 2}),
              _detail('SC-034', 2, {'status': 'rejected', 'reason': 'invalid_static_schema', 'gate_exit_code': 2}, actual))

    if only is None or only == ('SC-034', 3):
        selected += 1
        fixture = {'approved_scenarios': ['SC-016'], 'checked_scenarios': ['SC-999']}
        actual = _actual('SC-034', 3, fixture)
        check("SC-034" + _case_name("SC-034", 3, fixture, "capture_red"), assertThat(actual, {'status': 'rejected', 'reason': 'invalid_static_schema', 'gate_exit_code': 2}),
              _detail('SC-034', 3, {'status': 'rejected', 'reason': 'invalid_static_schema', 'gate_exit_code': 2}, actual))

    if only is None or only == ('SC-034', 4):
        selected += 1
        fixture = {'approved_examples': [1], 'checked_examples': [0]}
        actual = _actual('SC-034', 4, fixture)
        check("SC-034" + _case_name("SC-034", 4, fixture, "capture_red"), assertThat(actual, {'status': 'rejected', 'reason': 'invalid_static_schema', 'gate_exit_code': 2}),
              _detail('SC-034', 4, {'status': 'rejected', 'reason': 'invalid_static_schema', 'gate_exit_code': 2}, actual))

    if only is None or only == ('SC-035', 1):
        selected += 1
        fixture = {'tests': ['checker.py', 'policy.json'], 'checks': [{'scenario': 'SC-016', 'examples': [1]}]}
        actual = _actual('SC-035', 1, fixture)
        check("SC-035" + _case_name("SC-035", 1, fixture, "verify_static_contract"), assertThat(actual, {'test_review': 'passed', 'traceability': 'passed', 'tests_hash_current': True, 'exit_code': 0}),
              _detail('SC-035', 1, {'test_review': 'passed', 'traceability': 'passed', 'tests_hash_current': True, 'exit_code': 0}, actual))

    if only is None or only == ('SC-054', 1):
        selected += 1
        fixture = {'argv': ['python3', 'checker.py'], 'exit_code': 1, 'output': 'prefix STATIC_ASSERTION: not-at-line-start'}
        actual = _actual('SC-054', 1, fixture)
        check("SC-054" + _case_name("SC-054", 1, fixture, "capture_red"), assertThat(actual, {'failure_class': 'error', 'red_valid': False, 'gate_exit_code': 1}),
              _detail('SC-054', 1, {'failure_class': 'error', 'red_valid': False, 'gate_exit_code': 1}, actual))

    if only is None or only == ('SC-054', 2):
        selected += 1
        fixture = {'argv': ['python3', 'checker.py'], 'exit_code': 1, 'output': 'static_assertion: wrong-case'}
        actual = _actual('SC-054', 2, fixture)
        check("SC-054" + _case_name("SC-054", 2, fixture, "capture_red"), assertThat(actual, {'failure_class': 'error', 'red_valid': False, 'gate_exit_code': 1}),
              _detail('SC-054', 2, {'failure_class': 'error', 'red_valid': False, 'gate_exit_code': 1}, actual))

    if only is None or only == ('SC-055', 1):
        selected += 1
        fixture = {'argv': ['python3', 'checker.py'], 'tests': ['checker.py'], 'fixture_manifest_imports': ['policy.json']}
        actual = _actual('SC-055', 1, fixture)
        check("SC-055" + _case_name("SC-055", 1, fixture, "verify_static_contract"), assertThat(actual, {'status': 'rejected', 'reason': 'undeclared_static_dependency', 'gate_exit_code': 1}),
              _detail('SC-055', 1, {'status': 'rejected', 'reason': 'undeclared_static_dependency', 'gate_exit_code': 1}, actual))

    if only is None or only == ('SC-036', 1):
        selected += 1
        fixture = {'id': 'F-7', 'fixture_ledger_status': 'fixed', 'fixture_fixes': 1, 'fixture_repro_exit': 0}
        actual = _actual('SC-036', 1, fixture)
        check("SC-036" + _case_name("SC-036", 1, fixture, "plan_revalidation"), assertThat(actual, {'id': 'F-7', 'status': 'fixed', 'action': 'preserve', 'fixes': 1, 'exit_code': 0}),
              _detail('SC-036', 1, {'id': 'F-7', 'status': 'fixed', 'action': 'preserve', 'fixes': 1, 'exit_code': 0}, actual))

    if only is None or only == ('SC-037', 1):
        selected += 1
        fixture = {'id': 'F-7', 'fixture_ledger_status': 'fixed', 'fixture_fixes': 1, 'fixture_repro_exit': 1}
        actual = _actual('SC-037', 1, fixture)
        check("SC-037" + _case_name("SC-037", 1, fixture, "plan_revalidation"), assertThat(actual, {'id': 'F-7', 'finding_id_reused': True, 'action': 'reappear', 'result': 'flipflop', 'fixes': 1, 'exit_code': 1}),
              _detail('SC-037', 1, {'id': 'F-7', 'finding_id_reused': True, 'action': 'reappear', 'result': 'flipflop', 'fixes': 1, 'exit_code': 1}, actual))

    if only is None or only == ('SC-038', 1):
        selected += 1
        fixture = {'changed_files': ['scripts/gates/_common.py'], 'dependency_map': 'unknown'}
        actual = _actual('SC-038', 1, fixture)
        check("SC-038" + _case_name("SC-038", 1, fixture, "plan_revalidation"), assertThat(actual, {'required_action': 'full_rerun', 'gates': ['G0-G7', 'smoke', 'G9', 'G10'], 'may_claim_pass': False, 'exit_code': 1}),
              _detail('SC-038', 1, {'required_action': 'full_rerun', 'gates': ['G0-G7', 'smoke', 'G9', 'G10'], 'may_claim_pass': False, 'exit_code': 1}, actual))

    if only is None or only == ('SC-044', 1):
        selected += 1
        fixture = {'requested_id': 'F-99', 'canonical_id': 'F-7', 'identity_same': True, 'title_changed': True}
        actual = _actual('SC-044', 1, fixture)
        check("SC-044" + _case_name("SC-044", 1, fixture, "add_finding"), assertThat(actual, {'status': 'rejected', 'canonical_id': 'F-7', 'fixes_preserved': True, 'exit_code': 1}),
              _detail('SC-044', 1, {'status': 'rejected', 'canonical_id': 'F-7', 'fixes_preserved': True, 'exit_code': 1}, actual))

    if only is None or only == ('SC-045', 1):
        selected += 1
        fixture = {'id': 'F-7', 'fixes': 2, 'requested_action': 'fix'}
        actual = _actual('SC-045', 1, fixture)
        check("SC-045" + _case_name("SC-045", 1, fixture, "advance_review_loop"), assertThat(actual, {'id': 'F-7', 'status': 'parked', 'fixes': 2, 'owner_decision_required': True, 'exit_code': 1}),
              _detail('SC-045', 1, {'id': 'F-7', 'status': 'parked', 'fixes': 2, 'owner_decision_required': True, 'exit_code': 1}, actual))

    if only is None or only == ('SC-045', 2):
        selected += 1
        fixture = {'gate': 'G10', 'prior_redispatches': 1, 'requested_action': 'redispatch'}
        actual = _actual('SC-045', 2, fixture)
        check("SC-045" + _case_name("SC-045", 2, fixture, "advance_review_loop"), assertThat(actual, {'gate': 'G10', 'status': 'blocked', 'prior_redispatches': 1, 'owner_decision_required': True, 'exit_code': 1}),
              _detail('SC-045', 2, {'gate': 'G10', 'status': 'blocked', 'prior_redispatches': 1, 'owner_decision_required': True, 'exit_code': 1}, actual))

    if only is None or only == ('SC-049', 1):
        selected += 1
        fixture = {'requested_id': 'F-7', 'fixture_existing_identity': 'identity_a', 'fixture_requested_identity': 'identity_b'}
        actual = _actual('SC-049', 1, fixture)
        check("SC-049" + _case_name("SC-049", 1, fixture, "add_finding"), assertThat(actual, {'status': 'rejected', 'reason': 'finding_id_conflict', 'existing_finding_preserved': True, 'exit_code': 1}),
              _detail('SC-049', 1, {'status': 'rejected', 'reason': 'finding_id_conflict', 'existing_finding_preserved': True, 'exit_code': 1}, actual))

    if only is None or only == ('SC-039', 1):
        selected += 1
        fixture = {'commands': _approved_sc039_commands()}
        actual = _actual('SC-039', 1, fixture)
        expected = {'plan': 'planned', 'repair': 'complete', 'verify': 'passed', 'index_check': 'passed', 'commit_check': 'passed', 'dashboard_root_created': True, 'findings_root_created': True, 'empty_static_stream_included': True, 'empty_static_stream_byte_exact': True, 'ledger_schema': 1, 'status_schema': 1, 'index_tree_oid_valid': True, 'head_commit_oid_valid': True, 'oids_distinct': True, 'pr_ready': True, 'remote_actions': [], 'exit_code': 0}
        check("SC-039" + _case_name("SC-039", 1, fixture, "run_delivery_sequence"), assertThat(actual, expected),
              _detail('SC-039', 1, expected, actual))

    if only is None or only == ('SC-046', 1):
        selected += 1
        fixture = {'autonomy': {'version': 0}, 'runner': 'swift-testing', 'per_entry_override': None, 'oracle_sequence': 'design_v0_fixed_nine_commands'}
        actual = _actual('SC-046', 1, fixture)
        check("SC-046" + _case_name("SC-046", 1, fixture, "run_legacy_delivery_sequence"), assertThat(actual, {'legacy_parser_used': True, 'autonomy_ledger_created': False, 'legacy_status_readable': True, 'baseline_commands_compared': 9, 'unapproved_differences': 0, 'exit_code': 0}),
              _detail('SC-046', 1, {'legacy_parser_used': True, 'autonomy_ledger_created': False, 'legacy_status_readable': True, 'baseline_commands_compared': 9, 'unapproved_differences': 0, 'exit_code': 0}, actual))

    return selected


def _adversarial_repo(base: pathlib.Path, scenario: str = "SC-012") -> pathlib.Path:
    root = _new_repo(base)
    _configure(root, scenario, {})
    _approval_fixture(root, scenario)
    _commit(root, "adversarial fixture")
    return root


def _expected_rejection(reason: str = "invalid_cli", code: int = 2) -> dict[str, Any]:
    return {"status": "rejected", "reason": reason, "exit_code": code}


def _prepare_manifest_repo(base: pathlib.Path) -> pathlib.Path:
    root = _adversarial_repo(base)
    _delivery_fixture(root, "SC-010", {})
    _git(root, "add", "-A")
    return root


def _manifest_mutation(base: pathlib.Path, mutation: str) -> dict[str, Any]:
    root = _prepare_manifest_repo(base)
    ev = root / "specs/workflow-autonomy/evidence"
    if mutation == "missing_manifest":
        (ev / "delivery.json").unlink(missing_ok=True)
        _git(root, "add", "-A")
        return _run(root, "evidence-check", str(SPEC_REL), "--index")
    path = ev / "delivery.json"
    manifest = json.loads(path.read_text())
    if mutation == "missing_required_root":
        manifest["files"] = [row for row in manifest["files"] if row.get("path") != str(SPEC_REL)]
    elif mutation == "wrong_spec_hash":
        manifest["spec_hash"] = "sha256:" + "0" * 64
    elif mutation == "wrong_approval_anchor":
        manifest["approval_commit"] = "0" * 40
        manifest["approval_tree"] = "0" * 40
    elif mutation == "status_inconsistent":
        _write_json(ev / "status.json", {
            **_status_record(1),
            "pipeline_state": "complete",
            "delivery": {"state": "pr_open", "ref": None, "validation": None},
        })
        payload = (ev / "status.json").read_bytes()
        manifest["files"].append({
            "path": "specs/workflow-autonomy/evidence/status.json",
            "sha256": "sha256:" + hashlib.sha256(payload).hexdigest(),
            "source": "autonomy",
        })
    elif mutation == "missing_red_reference":
        raw_rel = "specs/workflow-autonomy/evidence/static-red/adversarial.stdout.log"
        raw = root / raw_rel
        raw.parent.mkdir(parents=True, exist_ok=True)
        raw.write_bytes(b"STATIC_ASSERTION: adversarial\n")
        red = json.loads((ev / "red.json").read_text())
        red["runner_results"] = [{
            "scenario": "SC-016", "example": 1, "red_valid": True,
            "stdout_path": raw_rel,
            "stderr_path": "specs/workflow-autonomy/evidence/static-red/adversarial.stderr.log",
        }]
        _write_json(ev / "red.json", red)
        red_bytes = (ev / "red.json").read_bytes()
        for row in manifest["files"]:
            if row.get("path") == "specs/workflow-autonomy/evidence/red.json":
                row["sha256"] = "sha256:" + hashlib.sha256(red_bytes).hexdigest()
    _write_json(path, manifest)
    _git(root, "add", "-A")
    return _run(root, "evidence-check", str(SPEC_REL), "--index")


def _empty_stream_guard(base: pathlib.Path, authorized: bool, valid_red: bool) -> dict[str, Any]:
    root = _prepare_manifest_repo(base)
    ev = root / "specs/workflow-autonomy/evidence"
    raw_rel = (
        "specs/workflow-autonomy/evidence/static-red/entry-001.stderr.log"
        if authorized else "specs/workflow-autonomy/evidence/ordinary-empty.log"
    )
    raw = root / raw_rel
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_bytes(b"")
    stdout_rel = "specs/workflow-autonomy/evidence/static-red/entry-001.stdout.log"
    (root / stdout_rel).write_text("STATIC_ASSERTION: SC-016 example #1\n")
    _delivery_fixture(root, "SC-012", {"files": []})
    red = {
        "schema_version": 1,
        "status": "passed" if valid_red else "failed",
        "spec_hash": "sha256:" + hashlib.sha256((root / SPEC_REL).read_bytes()).hexdigest(),
        "runner_results": [{
            "schema_version": 1, "scenario": "SC-016", "example": 1,
            "exit_code": 1, "failure_class": "assertion", "red_valid": valid_red,
            "stdout_path": stdout_rel, "stderr_path": raw_rel,
            "stdout_sha256": "sha256:" + hashlib.sha256((root / stdout_rel).read_bytes()).hexdigest(),
            "stderr_sha256": "sha256:" + hashlib.sha256(b"").hexdigest(),
        }],
    }
    _write_json(ev / "red.json", red)
    manifest_path = ev / "delivery.json"
    manifest = json.loads(manifest_path.read_text())
    red_bytes = (ev / "red.json").read_bytes()
    for row in manifest["files"]:
        if row.get("path") == "specs/workflow-autonomy/evidence/red.json":
            row["sha256"] = "sha256:" + hashlib.sha256(red_bytes).hexdigest()
    manifest["files"].append({
        "path": raw_rel,
        "sha256": "sha256:" + hashlib.sha256(b"").hexdigest(),
        "source": "red",
    })
    _write_json(manifest_path, manifest)
    _git(root, "add", "-A")
    return _run(root, "evidence-check", str(SPEC_REL), "--index")


def _optional_delivery_root_guard(base: pathlib.Path, name: str) -> dict[str, Any]:
    """從合法 v1 fixture 單點移除一個適用 root 與 manifest row。"""
    root = _prepare_manifest_repo(base)
    ev = root / "specs/workflow-autonomy/evidence"
    (ev / name).unlink()
    manifest_path = ev / "delivery.json"
    manifest = json.loads(manifest_path.read_text())
    rel = f"specs/workflow-autonomy/evidence/{name}"
    manifest["files"] = [row for row in manifest["files"] if row.get("path") != rel]
    _write_json(manifest_path, manifest)
    _git(root, "add", "-A")
    return _run(root, "evidence-check", str(SPEC_REL), "--index")


def _missing_v1_roots_guard(base: pathlib.Path) -> dict[str, Any]:
    root = _prepare_manifest_repo(base)
    ev = root / "specs/workflow-autonomy/evidence"
    names = {"autonomy.json", "dashboard.json", "findings.json"}
    for name in names:
        (ev / name).unlink()
    manifest_path = ev / "delivery.json"
    manifest = json.loads(manifest_path.read_text())
    removed = {f"specs/workflow-autonomy/evidence/{name}" for name in names}
    manifest["files"] = [row for row in manifest["files"] if row.get("path") not in removed]
    _write_json(manifest_path, manifest)
    _git(root, "add", "-A")
    return _run(root, "evidence-check", str(SPEC_REL), "--index")


def _missing_status_root_guard(base: pathlib.Path) -> dict[str, Any]:
    root = _prepare_manifest_repo(base)
    (root / "specs/workflow-autonomy/evidence/status.json").unlink()
    _git(root, "add", "-A")
    return _run(root, "evidence-check", str(SPEC_REL), "--index")


def _smoke_mode_root_guard(base: pathlib.Path) -> dict[str, Any]:
    root = _new_repo(base)
    _configure(root, "SC-011", {})
    import yaml
    spec_path = root / SPEC_REL
    approved_path = root / "specs/workflow-autonomy/evidence/spec.approved.yaml"
    spec = yaml.safe_load(spec_path.read_text())
    spec["requirements"][0]["scenarios"][0]["mode"] = "6c"
    payload = yaml.safe_dump(spec, allow_unicode=True, sort_keys=False)
    spec_path.write_text(payload)
    approved_path.write_text(payload)
    digest = "sha256:" + hashlib.sha256(spec_path.read_bytes()).hexdigest()
    ev = root / "specs/workflow-autonomy/evidence"
    (ev / "spec.hash").write_text(f"{digest}  {SPEC_REL}\n")
    approval = json.loads((ev / "approval.json").read_text())
    approval["approved_spec_sha256"] = digest
    _write_json(ev / "approval.json", approval)
    _write_json(ev / "smoke.json", {"schema_version": 1, "status": "passed"})
    _commit(root, "approved 6c fixture")
    _delivery_fixture(root, "SC-010", {})
    _git(root, "add", "-A")
    return _run(root, "evidence-check", str(SPEC_REL), "--index")


def _approval_semantics_guard(base: pathlib.Path, mutation: str) -> dict[str, Any]:
    """讓無效 approval 自身成為 committed anchor，避免先被 anchor drift 擋住。"""
    root = _new_repo(base)
    _configure(root, "SC-011", {})
    approval_path = root / "specs/workflow-autonomy/evidence/approval.json"
    approval = json.loads(approval_path.read_text())
    if mutation == "missing_hash":
        approval.pop("approved_spec_sha256", None)
    elif mutation == "wrong_hash":
        approval["approved_spec_sha256"] = "sha256:" + "0" * 64
    else:
        approval["approved_at"] = "not-rfc3339"
    _write_json(approval_path, approval)
    _commit(root, "invalid approval anchor fixture")
    _delivery_fixture(root, "SC-010", {})
    _git(root, "add", "-A")
    return _run(root, "evidence-check", str(SPEC_REL), "--index")


def _manifest_worktree_drift_guard(base: pathlib.Path) -> dict[str, Any]:
    root = _prepare_manifest_repo(base)
    manifest = root / "specs/workflow-autonomy/evidence/delivery.json"
    manifest.write_bytes(manifest.read_bytes() + b" ")
    return _run(root, "evidence-check", str(SPEC_REL), "--index")


def _red_stream_shape_guard(base: pathlib.Path, shape: str) -> dict[str, Any]:
    root = _prepare_manifest_repo(base)
    ev = root / "specs/workflow-autonomy/evidence"
    stdout_rel = "specs/workflow-autonomy/evidence/static-red/shape.stdout.log"
    stderr_rel = "specs/workflow-autonomy/evidence/static-red/shape.stderr.log"
    stdout = root / stdout_rel
    stderr = root / stderr_rel
    stdout.parent.mkdir(parents=True, exist_ok=True)
    stdout.write_bytes(b"" if shape == "double_empty" else b"runner exited without marker\n")
    stderr.write_bytes(b"")
    red = {
        "schema_version": 1,
        "status": "passed",
        "spec_hash": "sha256:" + hashlib.sha256((root / SPEC_REL).read_bytes()).hexdigest(),
        "runner_results": [{
            "schema_version": 1, "scenario": "SC-016", "example": 1,
            "exit_code": 1, "failure_class": "assertion", "red_valid": True,
            "stdout_path": stdout_rel, "stderr_path": stderr_rel,
            "stdout_sha256": "sha256:" + hashlib.sha256(stdout.read_bytes()).hexdigest(),
            "stderr_sha256": "sha256:" + hashlib.sha256(stderr.read_bytes()).hexdigest(),
        }],
    }
    _write_json(ev / "red.json", red)
    manifest_path = ev / "delivery.json"
    manifest = json.loads(manifest_path.read_text())
    for row in manifest["files"]:
        if row.get("path") == "specs/workflow-autonomy/evidence/red.json":
            row["sha256"] = "sha256:" + hashlib.sha256((ev / "red.json").read_bytes()).hexdigest()
    for rel in (stdout_rel, stderr_rel):
        manifest["files"].append({
            "path": rel,
            "sha256": "sha256:" + hashlib.sha256((root / rel).read_bytes()).hexdigest(),
            "source": "red",
        })
    _write_json(manifest_path, manifest)
    _git(root, "add", "-A")
    return _run(root, "evidence-check", str(SPEC_REL), "--index")


def _dashboard_inputs_guard(base: pathlib.Path) -> dict[str, Any]:
    root = _adversarial_repo(base)
    ev = root / "specs/workflow-autonomy/evidence"
    for name in ("autonomy.json", "status.json", "delivery.json"):
        (ev / name).unlink(missing_ok=True)
    proc = subprocess.run(
        [str(root / "scripts/gates/dashboard"), str(root / SPEC_REL)],
        cwd=root, capture_output=True, text=True,
    )
    payload = json.loads((ev / "dashboard.json").read_text()) if (ev / "dashboard.json").is_file() else {}
    notes = "\n".join(str(row.get("note", "")) for row in payload.get("gates") or [])
    required = [
        name for name in ("autonomy.json", "status.json", "delivery.json", "evidence-check")
        if name in notes
    ]
    return {"exit_code": proc.returncode, "auto_push_ok": payload.get("auto_push_ok"),
            "required_inputs_reported": required}


def _pr_comment_missing_inputs_guard(base: pathlib.Path) -> dict[str, Any]:
    root = _adversarial_repo(base)
    ev = root / "specs/workflow-autonomy/evidence"
    for name in ("autonomy.json", "status.json", "delivery.json"):
        (ev / name).unlink(missing_ok=True)
    _write_json(ev / "dashboard.json", {
        "name": "workflow-autonomy", "branch": "fixture", "scale": "fixture",
        "auto_push_ok": True, "gates": [], "attention": [],
    })
    return _run(root, "pr-comment", str(SPEC_REL), "--check")


def _test_review_agent_guard(base: pathlib.Path, weakened: bool) -> dict[str, Any]:
    root = _adversarial_repo(base)
    fixture = {"fixture_review": "independent", "fixture_assertion": "strong"}
    _seed_frozen_artifacts(root, "SC-006", fixture)
    agent_path = root / "specs/workflow-autonomy/evidence/test-review.agent.json"
    agent = json.loads(agent_path.read_text())
    tests = [_sha_record(root, "scripts/gates/tests/spec_workflow_autonomy.py")]
    agent["before_tests"] = [] if weakened else tests
    agent["after_tests"] = tests
    agent["assertion_weakened"] = weakened
    _write_json(agent_path, agent)
    return _run(root, "test-review", str(SPEC_REL))


def _valid_review_agent(root: pathlib.Path) -> pathlib.Path:
    fixture = {"fixture_review": "independent", "fixture_assertion": "strong"}
    _seed_frozen_artifacts(root, "SC-006", fixture)
    ev = root / "specs/workflow-autonomy/evidence"
    agent_path = ev / "test-review.agent.json"
    agent = json.loads(agent_path.read_text())
    after = [_sha_record(root, "scripts/gates/tests/spec_workflow_autonomy.py")]
    before = [{"path": after[0]["path"], "sha256": "sha256:" + "0" * 64}]
    import yaml
    approved = yaml.safe_load((root / "specs/workflow-autonomy/evidence/spec.approved.yaml").read_text())
    reviewed = [
        {"scenario": item["id"], "examples": list(range(1, len(item["examples"]) + 1))}
        for req in approved["requirements"] for item in req["scenarios"]
    ]
    reviewed.sort(key=lambda row: row["scenario"])
    agent.update({
        "before_tests": before, "after_tests": after,
        "assertion_weakened": False, "reviewed_examples": reviewed,
    })
    _write_json(agent_path, agent)
    return agent_path


def _review_contract_guard(base: pathlib.Path, mutation: str) -> dict[str, Any]:
    root = _adversarial_repo(base)
    agent_path = _valid_review_agent(root)
    ev = root / "specs/workflow-autonomy/evidence"
    if mutation == "dispatch_mismatch":
        agent = json.loads(agent_path.read_text())
        agent["completion_ref"] = "completion:mismatched"
        _write_json(agent_path, agent)
    elif mutation == "reviewed_examples":
        agent = json.loads(agent_path.read_text())
        agent["reviewed_examples"] = agent["reviewed_examples"][:-1]
        _write_json(agent_path, agent)
    elif mutation == "red_raw_reference":
        red_path = ev / "red.json"
        red = json.loads(red_path.read_text())
        red["runner_results"][0]["stdout_sha256"] = "sha256:" + "0" * 64
        _write_json(red_path, red)
    return _run(root, "test-review", str(SPEC_REL))


def _freeze_review_guard(base: pathlib.Path, mutation: str) -> dict[str, Any]:
    root = _adversarial_repo(base)
    _valid_review_agent(root)
    reviewed = _run(root, "test-review", str(SPEC_REL))
    ev = root / "specs/workflow-autonomy/evidence"
    review_path = ev / "test-review.json"
    review = json.loads(review_path.read_text())
    if mutation in {"missing_test", "reviewed_examples"}:
        if mutation == "missing_test":
            review["after_tests"] = [{
                "path": "scripts/gates/tests/does-not-exist.py",
                "sha256": "sha256:" + "0" * 64,
            }]
        else:
            review["reviewed_examples"] = review["reviewed_examples"][:-1]
        agent = review.get("agent") or {}
        token_input = {
            "writer_task_ref": agent.get("writer_task_ref"),
            "reviewer_task_ref": agent.get("reviewer_task_ref"),
            "completion_ref": agent.get("completion_ref"),
            "tree_token": agent.get("tree_token"),
            "before_tests": review.get("before_tests"),
            "after_tests": review.get("after_tests"),
            "assertion_weakened": review.get("assertion_weakened"),
            "reviewed_examples": review.get("reviewed_examples"),
        }
        review["review_token"] = "sha256:" + hashlib.sha256(_canonical(token_input).encode()).hexdigest()
        _write_json(review_path, review)
    else:
        dispatch_path = ev / "review-dispatch.json"
        dispatch = json.loads(dispatch_path.read_text())
        dispatch["completion_ref"] = "completion:changed-after-review"
        _write_json(dispatch_path, dispatch)
    token = str(json.loads(review_path.read_text()).get("review_token"))
    if reviewed.get("exit_code") != 0:
        return reviewed
    return _run(root, "freeze-check", str(SPEC_REL), "--replace-tests-hash", token)


def _review_token_guard(base: pathlib.Path) -> dict[str, Any]:
    root = _adversarial_repo(base)
    fixture = {"fixture_review": "independent", "fixture_assertion": "strong"}
    _seed_autonomy(root, "SC-006", fixture)
    _seed_frozen_artifacts(root, "SC-006", fixture)
    review_path = root / "specs/workflow-autonomy/evidence/test-review.json"
    review = json.loads(review_path.read_text())
    review["review_token"] = "sha256:" + "0" * 64
    _write_json(review_path, review)
    return _run(root, "autonomy", str(SPEC_REL), "verify-tests", "--expect-generation", "1", "--id", "R-001")


def _committed_red_reuse_guard(base: pathlib.Path) -> dict[str, Any]:
    root = _adversarial_repo(base)
    fixture = {"fixture_review": "independent", "fixture_assertion": "strong"}
    _seed_frozen_artifacts(root, "SC-006", fixture)
    ev = root / "specs/workflow-autonomy/evidence"
    red = json.loads((ev / "red.json").read_text())
    checks: dict[str, list[int]] = {}
    for row in red["runner_results"]:
        checks.setdefault(row["scenario"], []).append(row["example"])
    _write_json(ev / "red-inputs.json", [{
        "layer": "workflow-autonomy", "runner": "static-command",
        "argv": ["python3", "scripts/gates/tests/spec_workflow_autonomy.py"],
        "timeout_seconds": 120,
        "tests": ["scripts/gates/tests/spec_workflow_autonomy.py"],
        "checks": [{"scenario": sid, "examples": sorted(examples)} for sid, examples in sorted(checks.items())],
    }])
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "committed frozen RED")
    raw = root / red["runner_results"][0]["stdout_path"]
    raw.write_bytes(raw.read_bytes() + b"tampered after commit\n")
    return _run(root, "red-capture", str(SPEC_REL), exit_key="gate_exit_code")


def _binary_static_guard(base: pathlib.Path) -> dict[str, Any]:
    root = _adversarial_repo(base)
    _static_fixture(root, "SC-054", 1, {
        "exit_code": 1,
        "output": "STATIC_ASSERTION: SC-054 example #1",
        "checked_examples": [1],
    })
    (root / "checker.py").write_text(
        "import sys\nsys.stdout.buffer.write(b'\\xffSTATIC_ASSERTION: SC-054 example #1\\n')\nraise SystemExit(1)\n"
    )
    result = _run(root, "red-capture", str(SPEC_REL), exit_key="gate_exit_code")
    crashed = "UnicodeDecodeError" in str(result.get("stderr", ""))
    return {
        "failure_class": "unicode_crash" if crashed else result.get("failure_class"),
        "gate_exit_code": result["gate_exit_code"],
        "red_valid": result.get("red_valid", False),
    }


def _findings_repro_guard(base: pathlib.Path, mutation: str) -> dict[str, Any]:
    root = _adversarial_repo(base)
    _finding_fixture(root, "SC-036", {"fixture_repro_exit": 0})
    ev = root / "specs/workflow-autonomy/evidence"
    repro_path = ev / "repro.json"
    repro = json.loads(repro_path.read_text())
    repro["argv"] = [sys.executable, "-c", "raise SystemExit(0)"]
    if mutation == "outside_cwd":
        repro["cwd"] = ".."
    elif mutation == "path_indices":
        repro["path_indices"] = [99]
    elif mutation == "environment":
        repro["environment"] = {"PYTHONPATH": "../outside"}
    elif mutation == "outside_input":
        outside = root.parent / "outside-input.txt"
        outside.write_text("outside\n")
        repro["inputs"] = [{
            "path": "../outside-input.txt",
            "sha256": "sha256:" + hashlib.sha256(outside.read_bytes()).hexdigest(),
        }]
    elif mutation == "snapshot_drift":
        target = root / "scripts/gates/_common.py"
        repro["inputs"] = [_sha_record(root, "scripts/gates/_common.py")]
        repro["argv"] = [sys.executable, "-c", f"from pathlib import Path; Path({str(target)!r}).write_text('drift\\n')"]
    _write_json(repro_path, repro)
    return _run(root, "findings", "revalidate", str(SPEC_REL), "--id", "F-7")


def _autonomy_guard(base: pathlib.Path, mutation: str) -> dict[str, Any]:
    root = _adversarial_repo(base)
    if mutation == "verify_delta":
        fixture = {"fixture_review": "independent", "fixture_assertion": "strong"}
        _seed_autonomy(root, "SC-006", fixture)
        _seed_frozen_artifacts(root, "SC-006", fixture)
        target = root / "scripts/gates/tests/run"
        target.write_text(target.read_text() + "\n# changed outside frozen repair\n")
        return _run(root, "autonomy", str(SPEC_REL), "verify-tests", "--expect-generation", "1", "--id", "R-001")
    ev = root / "specs/workflow-autonomy/evidence"
    evidence = ev / "repro.log"
    if mutation != "untracked_snapshot":
        evidence.write_text("completion evidence v1\n")
        _git(root, "add", "--", str(evidence.relative_to(root)))
        _git(root, "commit", "-qm", "fixed completion evidence snapshot")
    _run(root, "autonomy", str(SPEC_REL), "plan", "--expect-generation", "0", "--id", "R-001",
         "--kind", "implementation", "--file", "scripts/gates/autonomy")
    if mutation == "untracked_snapshot":
        evidence.write_text("completion evidence v1\n")
    if mutation == "undeclared_delta":
        (ev / "unapproved-extra.log").write_text("unapproved evidence delta\n")
    if mutation == "static_red_delta":
        static = ev / "static-red/unapproved.log"
        static.parent.mkdir(parents=True, exist_ok=True)
        static.write_text("unapproved static evidence delta\n")
    first = _run(root, "autonomy", str(SPEC_REL), "complete", "--expect-generation", "1", "--id", "R-001",
                 "--evidence", str(evidence.relative_to(root)))
    if mutation in {"untracked_snapshot", "undeclared_delta", "static_red_delta"}:
        return first
    if mutation in {"replay_content", "check_content"}:
        evidence.write_text("completion evidence v2\n")
    if mutation == "replay_content":
        return _run(root, "autonomy", str(SPEC_REL), "complete", "--expect-generation", "2", "--id", "R-001",
                    "--evidence", str(evidence.relative_to(root)))
    if mutation == "check_content":
        return _run(root, "autonomy", str(SPEC_REL), "check")
    ledger_path = ev / "autonomy.json"
    ledger = json.loads(ledger_path.read_text())
    row = ledger["repairs"][0]["evidence"][0]
    if mutation == "ledger_hash":
        row["sha256"] = "sha256:" + "0" * 64
    elif mutation == "ledger_tree":
        row["tree_token"] = "tree:" + "0" * 40
    elif mutation == "ledger_metadata":
        row.pop("tree_token", None)
        row.pop("mode", None)
        row.pop("git_blob", None)
    elif mutation == "ledger_blob":
        row["git_blob"] = "0" * 40
    elif mutation == "ledger_mode":
        row["mode"] = "120000"
    elif mutation == "ledger_spec_hash":
        ledger["spec_hash"] = "sha256:" + "0" * 64
    elif mutation == "empty_content":
        evidence.write_bytes(b"")
    _write_json(ledger_path, ledger)
    return _run(root, "autonomy", str(SPEC_REL), "check")


def _freeze_replace_guard(base: pathlib.Path, valid: bool) -> dict[str, Any]:
    root = _adversarial_repo(base)
    review = _run(root, "test-review", str(SPEC_REL))
    review_payload = json.loads((root / "specs/workflow-autonomy/evidence/test-review.json").read_text())
    token = str(review_payload.get("review_token")) if valid else "sha256:" + "0" * 64
    return _run(root, "freeze-check", str(SPEC_REL), "--replace-tests-hash", token)


def _v0_mutation_guard(base: pathlib.Path) -> dict[str, Any]:
    root = _adversarial_repo(base)
    pipeline = root / "specs/pipeline.yaml"
    pipeline.write_text(pipeline.read_text().replace("version: 1", "version: 0"))
    repro = root / "specs/workflow-autonomy/evidence/repro-v0.json"
    _write_json(repro, {
        "schema_version": 1, "argv": [sys.executable, "-c", "raise SystemExit(1)"],
        "path_indices": [], "cwd": ".", "stdin_sha256": None, "environment": {}, "inputs": [],
    })
    return _run(root, "findings", str(SPEC_REL), "add", "--id", "F-V0", "--kind", "must_fix",
                "--check", "SC-037", "--location", "scripts/gates/_common.py:1",
                "--repro-json", str(repro.relative_to(root)))


def _cli_matrix_guard(base: pathlib.Path, schema: bool) -> dict[str, Any]:
    root = _adversarial_repo(base)
    gates = [
        "config-check", "autonomy", "evidence-check", "runs", "red-capture", "test-review",
        "traceability", "freeze-check", "findings", "loop", "dashboard", "pr-comment",
    ]
    results = []
    for gate in gates:
        args = ["--schema"] if schema else ["--definitely-unknown"]
        proc = subprocess.run([str(root / "scripts/gates" / gate), *args], cwd=root, capture_output=True, text=True)
        parsed = None
        try:
            parsed = json.loads(proc.stdout)
        except json.JSONDecodeError:
            pass
        canonical_stdout = parsed is not None and proc.stdout == _canonical(parsed) + "\n"
        results.append({"gate": gate, "exit": proc.returncode, "json": parsed, "canonical": canonical_stdout})
    if schema:
        passed = all(
            row["exit"] == 0
            and row["canonical"]
            and _canonical(row["json"]) == _canonical(EXPECTED_GATE_SCHEMAS[row["gate"]])
            for row in results
        )
        return {"status": "passed" if passed else "failed", "exit_code": 0 if passed else 1, "results": results}
    rejected = all(
        row["exit"] == 2 and isinstance(row["json"], dict)
        and row["json"].get("status") == "rejected"
        and row["json"].get("reason") == "invalid_cli"
        and row["json"].get("exit_code") == 2
        for row in results
    )
    return {"status": "rejected" if rejected else "passed", "reason": "invalid_cli" if rejected else None,
            "exit_code": 2 if rejected else 0, "results": results}


def _findings_argv_order_guard(base: pathlib.Path) -> dict[str, Any]:
    root = _adversarial_repo(base)
    args = _finding_fixture(root, "SC-044", {"requested_id": "F-99"})
    # 核准的固定順序是 findings add <spec>；其餘 flags 沿用既有 SC-044 fixture。
    return _run(root, "findings", "add", args[0], *args[2:])


def _findings_revalidate_order_guard(base: pathlib.Path) -> dict[str, Any]:
    root = _adversarial_repo(base)
    _finding_fixture(root, "SC-036", {"fixture_repro_exit": 0})
    return _run(root, "findings", "revalidate", str(SPEC_REL), "--id", "F-7")


def _findings_add_contract_guard(base: pathlib.Path, mutation: str) -> dict[str, Any]:
    root = _adversarial_repo(base)
    ev = root / "specs/workflow-autonomy/evidence"
    repro_rel = "specs/workflow-autonomy/evidence/add-repro.json"
    repro_path = root / repro_rel
    repro = {
        "schema_version": 1,
        "argv": ["python3", "-c", "raise SystemExit(1)"],
        "path_indices": [],
        "cwd": ".",
        "stdin_sha256": None,
        "environment": {},
        "inputs": [],
    }
    location = "scripts/gates/_common.py:1"
    trailing: list[str] = []
    if mutation == "schema":
        repro["schema_version"] = 2
    elif mutation == "argv":
        repro["argv"] = []
    elif mutation == "path_indices":
        repro["path_indices"] = [99]
    elif mutation == "cwd":
        repro["cwd"] = ".."
    elif mutation == "stdin":
        repro["stdin_sha256"] = "not-a-sha256"
    elif mutation == "environment":
        repro["environment"] = {"SECRET": "leak"}
    elif mutation == "input":
        repro["inputs"] = [{"path": "../outside", "sha256": "sha256:" + "0" * 64}]
    elif mutation == "symlink":
        link = ev / "linked-dir"
        link.symlink_to(root / "scripts/gates", target_is_directory=True)
        linked_input = link / "_common.py"
        repro["inputs"] = [{"path": str(linked_input.relative_to(root)),
                            "sha256": _sha_record(root, "scripts/gates/_common.py")["sha256"]}]
    elif mutation == "location":
        location = "scripts/gates/_common.py"
    elif mutation == "trailing":
        trailing = ["--unexpected", "value"]
    _write_json(repro_path, repro)
    return _run(
        root, "findings", "add", str(SPEC_REL),
        "--id", "F-CONTRACT", "--kind", "must_fix", "--check", "SC-038",
        "--location", location, "--repro-json", repro_rel, *trailing,
    )


def _runs_contract_guard(base: pathlib.Path, mutation: str) -> dict[str, Any]:
    root = _adversarial_repo(base)
    ev = root / "specs/workflow-autonomy/evidence"
    before = _evidence_tree_snapshot(ev)
    if mutation == "version0":
        pipeline = root / "specs/pipeline.yaml"
        pipeline.write_text(pipeline.read_text().replace("version: 1", "version: 0"))
        result = _run(
            root, "runs", "--set", str(SPEC_REL), "--expect-generation", "0",
            "--pipeline-state", "waiting",
        )
    elif mutation == "unknown_nested":
        result = _run(
            root, "runs", "--set", str(SPEC_REL), "--expect-generation", "0",
            "--pipeline-state", "waiting", "--unexpected", "value",
        )
    elif mutation == "trailing_positional":
        result = _run(
            root, "runs", "--set", str(SPEC_REL), "--expect-generation", "0",
            "--pipeline-state", "waiting", "unexpected-positional",
        )
    else:
        result = _run(
            root, "runs", "--set", str(SPEC_REL), "--expect-generation", "0",
            "--delivery-state", "merged", "--delivery-ref", "",
        )
    after = _evidence_tree_snapshot(ev)
    result["evidence_delta"] = [
        {"path": rel, "before": before.get(rel), "after": after.get(rel)}
        for rel in sorted(set(before) | set(after))
        if before.get(rel) != after.get(rel)
    ]
    return result


def _evidence_tree_snapshot(root: pathlib.Path) -> dict[str, dict[str, Any]]:
    """完整保存 evidence tree，讓新增、刪除、覆寫與型別/mode 漂移都可見。"""
    rows: dict[str, dict[str, Any]] = {}
    if not root.exists():
        return rows
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        info = path.lstat()
        mode = format(stat.S_IMODE(info.st_mode), "04o")
        if stat.S_ISREG(info.st_mode):
            payload = path.read_bytes()
            rows[rel] = {
                "type": "file", "mode": mode, "bytes": len(payload),
                "sha256": "sha256:" + hashlib.sha256(payload).hexdigest(),
            }
        elif stat.S_ISDIR(info.st_mode):
            rows[rel] = {"type": "directory", "mode": mode}
        elif stat.S_ISLNK(info.st_mode):
            payload = os.fsencode(os.readlink(path))
            rows[rel] = {
                "type": "symlink", "mode": mode, "bytes": len(payload),
                "sha256": "sha256:" + hashlib.sha256(payload).hexdigest(),
            }
        else:
            rows[rel] = {"type": "other", "mode": mode}
    return rows


def _process_report_guard(base: pathlib.Path) -> dict[str, Any]:
    root = _adversarial_repo(base)
    real = root / "scripts/gates/config-check.real"
    gate = root / "scripts/gates/config-check"
    gate.rename(real)
    gate.write_text(
        "#!/usr/bin/env python3\n"
        "import json,subprocess,sys\n"
        "p=subprocess.run([sys.argv[0]+'.real',*sys.argv[1:]],capture_output=True,text=True)\n"
        "lines=p.stdout.splitlines()\n"
        "for i in range(len(lines)-1,-1,-1):\n"
        " try:\n  d=json.loads(lines[i]); d['exit_code']=1; lines[i]=json.dumps(d); break\n"
        " except json.JSONDecodeError: pass\n"
        "print('\\n'.join(lines))\nraise SystemExit(0)\n"
    )
    gate.chmod(0o755)
    gate_result = _run(root, "config-check", ".")
    accepted = _gate_succeeded(gate_result)
    return {
        "status": "passed" if accepted else "blocked",
        "may_continue": accepted,
        "exit_code": 0 if accepted else 1,
        "steps": [{
            "argv": [str(gate), "."],
            "process_exit": gate_result.get("exit_code"),
            "reported_exit": gate_result.get("reported_exit_code"),
        }],
    }


def _autonomy_post_ledger_commit_guard(base: pathlib.Path) -> dict[str, Any]:
    """完成後提交 ledger 不得讓已保存的 evidence snapshot 自我失效。"""
    root = _adversarial_repo(base)
    ev = root / "specs/workflow-autonomy/evidence"
    evidence = ev / "repro.log"
    evidence.write_text("committed completion evidence\n")
    _git(root, "add", "--", str(evidence.relative_to(root)))
    _git(root, "commit", "-qm", "fixed evidence snapshot")
    plan = _run(
        root, "autonomy", str(SPEC_REL), "plan", "--expect-generation", "0",
        "--id", "R-LEDGER", "--kind", "implementation", "--file", "scripts/gates/autonomy",
    )
    complete = _run(
        root, "autonomy", str(SPEC_REL), "complete", "--expect-generation", "1",
        "--id", "R-LEDGER", "--evidence", str(evidence.relative_to(root)),
    )
    before_commit = _run(root, "autonomy", str(SPEC_REL), "check")
    ledger_rel = "specs/workflow-autonomy/evidence/autonomy.json"
    _git(root, "add", "--", ledger_rel)
    _git(root, "commit", "-qm", "commit autonomy ledger")
    after_commit = _run(root, "autonomy", str(SPEC_REL), "check")
    all_ok = all(_gate_succeeded(row) for row in (plan, complete, before_commit, after_commit))
    return {
        "plan": plan.get("status"),
        "complete": complete.get("status"),
        "before_ledger_commit": before_commit.get("status"),
        "after_ledger_commit": after_commit.get("status"),
        "may_continue": after_commit.get("may_continue"),
        "exit_code": 0 if all_ok else 1,
    }


def _approval_required_field_guard(base: pathlib.Path, field: str) -> dict[str, Any]:
    """讓只缺一個 required approval 欄位的文件成為 committed anchor。"""
    root = _new_repo(base)
    _configure(root, "SC-011", {})
    approval_path = root / "specs/workflow-autonomy/evidence/approval.json"
    approval = json.loads(approval_path.read_text())
    approval.pop(field, None)
    _write_json(approval_path, approval)
    _commit(root, f"approval missing {field}")
    _delivery_fixture(root, "SC-010", {})
    _git(root, "add", "-A")
    return _run(root, "evidence-check", str(SPEC_REL), "--index")


def _incomplete_status_guard(base: pathlib.Path) -> dict[str, Any]:
    """Manifest 合法且宣告 status；唯一缺陷是 status schema 不完整。"""
    root = _prepare_manifest_repo(base)
    ev = root / "specs/workflow-autonomy/evidence"
    status_path = ev / "status.json"
    _write_json(status_path, {
        "schema_version": 1,
        "pipeline_state": "waiting", "stage": "S7", "next_step": "fixture",
        "blocked_on": None,
        "delivery": {"state": "local"},
        "report": {"state": "pending"},
        "extra": "must be rejected",
    })
    # status 是 evidence-check 的固定 snapshot root，不是 manifest.files row。
    # 保持 manifest 不變，讓唯一缺陷落在 status 自身 schema。
    _git(root, "add", "-A")
    return _run(root, "evidence-check", str(SPEC_REL), "--index")


def _manifest_omits_red_references_guard(base: pathlib.Path) -> dict[str, Any]:
    """Raw streams 與 RED metadata 都合法，但 manifest 刻意漏列兩個 reference。"""
    root = _prepare_manifest_repo(base)
    ev = root / "specs/workflow-autonomy/evidence"
    stdout_rel = "specs/workflow-autonomy/evidence/static-red/undeclared.stdout.log"
    stderr_rel = "specs/workflow-autonomy/evidence/static-red/undeclared.stderr.log"
    stdout_path, stderr_path = root / stdout_rel, root / stderr_rel
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_path.write_text("STATIC_ASSERTION: SC-016 example #1\n")
    stderr_path.write_text("assertion detail\n")
    red_path = ev / "red.json"
    red = {
        "schema_version": 1,
        "status": "passed",
        "spec_hash": "sha256:" + hashlib.sha256((root / SPEC_REL).read_bytes()).hexdigest(),
        "runner_results": [{
            "schema_version": 1, "scenario": "SC-016", "example": 1,
            "exit_code": 1, "failure_class": "assertion", "red_valid": True,
            "stdout_path": stdout_rel, "stderr_path": stderr_rel,
            "stdout_sha256": "sha256:" + hashlib.sha256(stdout_path.read_bytes()).hexdigest(),
            "stderr_sha256": "sha256:" + hashlib.sha256(stderr_path.read_bytes()).hexdigest(),
        }],
    }
    _write_json(red_path, red)
    manifest_path = ev / "delivery.json"
    manifest = json.loads(manifest_path.read_text())
    for row in manifest["files"]:
        if row.get("path") == red_path.relative_to(root).as_posix():
            row["sha256"] = "sha256:" + hashlib.sha256(red_path.read_bytes()).hexdigest()
    # 兩個 raw 檔真實存在且被 index 收錄，但 manifest.files 刻意不宣告。
    _write_json(manifest_path, manifest)
    _git(root, "add", "-A")
    return _run(root, "evidence-check", str(SPEC_REL), "--index")


def _seed_well_formed_red(root: pathlib.Path) -> pathlib.Path:
    """補齊 seed raw hashes，建立 mutation 前可驗證的 RED。"""
    ev = root / "specs/workflow-autonomy/evidence"
    red_path = ev / "red.json"
    red = json.loads(red_path.read_text())
    for row in red.get("runner_results") or []:
        for side in ("stdout", "stderr"):
            raw = root / str(row[f"{side}_path"])
            row[f"{side}_sha256"] = "sha256:" + hashlib.sha256(raw.read_bytes()).hexdigest()
    _write_json(red_path, red)
    return red_path


def _mutate_red_passed_without_raw_hashes(root: pathlib.Path) -> None:
    red_path = root / "specs/workflow-autonomy/evidence/red.json"
    red = json.loads(red_path.read_text())
    for row in red.get("runner_results") or []:
        row["exit_code"] = 0
        row["failure_class"] = "passed"
        row["red_valid"] = True
        row.pop("stdout_sha256", None)
        row.pop("stderr_sha256", None)
    _write_json(red_path, red)


def _invalid_red_review_guard(base: pathlib.Path) -> dict[str, Any]:
    root = _adversarial_repo(base)
    _valid_review_agent(root)
    _seed_well_formed_red(root)
    _mutate_red_passed_without_raw_hashes(root)
    return _run(root, "test-review", str(SPEC_REL))


def _invalid_red_freeze_guard(base: pathlib.Path) -> dict[str, Any]:
    root = _adversarial_repo(base)
    agent_path = _valid_review_agent(root)
    _seed_well_formed_red(root)
    review_path = root / "specs/workflow-autonomy/evidence/test-review.json"
    agent = json.loads(agent_path.read_text())
    review = json.loads(review_path.read_text())
    review.update({
        "status": "passed", "agent": agent,
        "before_tests": agent["before_tests"], "after_tests": agent["after_tests"],
        "assertion_weakened": False, "reviewed_examples": agent["reviewed_examples"],
    })
    token_input = {
        key: agent[key] for key in (
            "writer_task_ref", "reviewer_task_ref", "completion_ref", "tree_token",
            "before_tests", "after_tests", "assertion_weakened", "reviewed_examples",
        )
    }
    review["review_token"] = "sha256:" + hashlib.sha256(_canonical(token_input).encode()).hexdigest()
    _write_json(review_path, review)
    token = str(review["review_token"])
    _mutate_red_passed_without_raw_hashes(root)
    return _run(root, "freeze-check", str(SPEC_REL), "--replace-tests-hash", token)


def _invalid_red_delivery_guard(base: pathlib.Path) -> dict[str, Any]:
    root = _prepare_manifest_repo(base)
    ev = root / "specs/workflow-autonomy/evidence"
    stdout_rel = "specs/workflow-autonomy/evidence/static-red/passed.stdout.log"
    stderr_rel = "specs/workflow-autonomy/evidence/static-red/passed.stderr.log"
    (root / stdout_rel).parent.mkdir(parents=True, exist_ok=True)
    (root / stdout_rel).write_text("STATIC_ASSERTION: SC-016 example #1\n")
    (root / stderr_rel).write_text("assertion detail\n")
    red_path = ev / "red.json"
    _write_json(red_path, {
        "schema_version": 1,
        "status": "passed",
        "spec_hash": "sha256:" + hashlib.sha256((root / SPEC_REL).read_bytes()).hexdigest(),
        "runner_results": [{
            "schema_version": 1, "scenario": "SC-016", "example": 1,
            "exit_code": 0, "failure_class": "passed", "red_valid": True,
            "stdout_path": stdout_rel, "stderr_path": stderr_rel,
        }],
    })
    manifest_path = ev / "delivery.json"
    manifest = json.loads(manifest_path.read_text())
    for row in manifest["files"]:
        if row.get("path") == red_path.relative_to(root).as_posix():
            row["sha256"] = "sha256:" + hashlib.sha256(red_path.read_bytes()).hexdigest()
    for rel in (stdout_rel, stderr_rel):
        manifest["files"].append({
            "path": rel,
            "sha256": "sha256:" + hashlib.sha256((root / rel).read_bytes()).hexdigest(),
            "source": "red",
        })
    _write_json(manifest_path, manifest)
    _git(root, "add", "-A")
    return _run(root, "evidence-check", str(SPEC_REL), "--index")


def _sc039_required_producers_guard(base: pathlib.Path) -> dict[str, Any]:
    """由空的衍生 roots 起跑核准序列，禁止借用 source workspace 預存輸出。"""
    root = _new_repo(base)
    _configure(root, "SC-039", {})
    _approval_fixture(root, "SC-039")
    ev = root / "specs/workflow-autonomy/evidence"
    # 四個 sequence-produced roots 一律不借用 source workspace 預存檔。
    for name in ("delivery.json", "status.json", "dashboard.json", "findings.json"):
        (ev / name).unlink(missing_ok=True)
    repro = ev / "repro.log"
    repro.write_text("e2e evidence\n")
    # 隔離 repo 沒有 approval anchor 的歷史；只在 fixture 副本把 frozen
    # baseline helper 的 source 指回真實 source Git repo，仍實跑同一 checker/gates。
    baseline_helper = root / "scripts/gates/tests/workflow_autonomy_red_baseline.py"
    baseline_helper.write_text(baseline_helper.read_text().replace(
        "SOURCE_ROOT = HERE.parents[2]",
        f"SOURCE_ROOT = pathlib.Path({str(SOURCE_ROOT)!r})",
    ))
    invocation_log = base / "evidence-check-invocations.jsonl"
    evidence_gate = root / "scripts/gates/evidence-check"
    evidence_real = root / "scripts/gates/evidence-check.real"
    evidence_gate.rename(evidence_real)
    evidence_gate.write_text(
        "#!/usr/bin/env python3\n"
        "import json,pathlib,subprocess,sys\n"
        f"log=pathlib.Path({str(invocation_log)!r})\n"
        "with log.open('a') as h:h.write(json.dumps(sys.argv[1:])+\"\\n\")\n"
        "raise SystemExit(subprocess.run([sys.argv[0]+'.real',*sys.argv[1:]]).returncode)\n"
    )
    evidence_gate.chmod(0o755)
    _commit(root, "SC-039 without derived roots")
    # 這個 guard 只測命令序列是否有 producer；先在 fixture 內建立與目前
    # checker 一致的獨立 review/tests.hash，避免舊 freeze 提早遮蔽目標。
    agent_path = _valid_review_agent(root)
    red_inputs = json.loads((ev / "red-inputs.json").read_text())
    test_paths = sorted({str(rel) for entry in red_inputs for rel in entry.get("tests", [])})
    tests = [_sha_record(root, rel) for rel in test_paths]
    agent = json.loads(agent_path.read_text())
    token_proc = subprocess.run([
        sys.executable, "-c",
        "import pathlib,sys;sys.path.insert(0,'scripts/gates');"
        "from _state import tree_fingerprint;print(tree_fingerprint(pathlib.Path('.').resolve()))",
    ], cwd=root, capture_output=True, text=True, check=True)
    runtime_tree_token = token_proc.stdout.strip()
    dispatch_path = ev / "review-dispatch.json"
    dispatch = json.loads(dispatch_path.read_text())
    dispatch["tree_token"] = runtime_tree_token
    agent["tree_token"] = runtime_tree_token
    _write_json(dispatch_path, dispatch)
    agent["before_tests"] = [
        {"path": row["path"], "sha256": "sha256:" + "0" * 64} for row in tests
    ]
    agent["after_tests"] = tests
    _write_json(agent_path, agent)
    (ev / "tests.hash").write_text("".join(
        f"{row['sha256']}  {row['path']}\n" for row in tests
    ))
    # 獨立 review prerequisites 可預建；RED 必須由序列中的 red-capture 新鮮產生。
    (ev / "red.json").unlink(missing_ok=True)
    shutil.rmtree(ev / "static-red", ignore_errors=True)
    sequence = _e2e_actual(root, "SC-039")
    invocations = [
        json.loads(line) for line in invocation_log.read_text().splitlines()
    ] if invocation_log.is_file() else []
    required_pre_dashboard = {
        (str(SPEC_REL), "--index", "--pre-dashboard"),
        (str(SPEC_REL), "--commit", "--pre-dashboard"),
    }
    observed_pre_dashboard = {
        tuple(row) for row in invocations if isinstance(row, list) and "--pre-dashboard" in row
    }
    dashboard_created = (ev / "dashboard.json").is_file()
    findings_created = (ev / "findings.json").is_file()
    return {
        "status": "passed" if sequence.get("exit_code") == 0 else "failed",
        "failed_step": sequence.get("failed_step"),
        "dashboard_root_created": dashboard_created,
        "findings_root_created": findings_created,
        "direct_roots_not_in_manifest": sequence.get("direct_roots_not_in_manifest", False),
        "final_direct_roots_present": sequence.get("final_direct_roots_present", False),
        "token_stable_across_status_dashboard_amend": sequence.get(
            "token_stable_across_status_dashboard_amend", False,
        ),
        "evidence_check_read_only": sequence.get("evidence_check_read_only", False),
        "pre_dashboard_calls_observed": required_pre_dashboard <= observed_pre_dashboard,
        "gate_exits": {
            pathlib.Path(str(row.get("argv", [""])[0])).name: row.get("exit")
            for row in sequence.get("steps", []) if isinstance(row, dict) and row.get("argv")
        },
        "exit_code": sequence.get("exit_code", 1),
    }


def _findings_stdout_schema_guard(base: pathlib.Path) -> dict[str, Any]:
    """正常 v1 add 的原始 stdout 必須通過同一 CLI 公布的 JSON Schema。"""
    root = _adversarial_repo(base)
    ev = root / "specs/workflow-autonomy/evidence"
    _write_json(ev / "findings.json", {"items": [], "dispatched": {}, "summary": {}})
    repro_rel = "specs/workflow-autonomy/evidence/schema-repro.json"
    _write_json(root / repro_rel, {
        "schema_version": 1,
        "argv": [sys.executable, "-c", "raise SystemExit(1)"],
        "path_indices": [], "cwd": ".", "stdin_sha256": None,
        "environment": {}, "inputs": [],
    })
    schema_proc = subprocess.run(
        [str(root / "scripts/gates/findings"), "--schema"],
        cwd=root, capture_output=True, text=True,
    )
    add_proc = subprocess.run([
        str(root / "scripts/gates/findings"), "add", str(SPEC_REL),
        "--id", "F-SCHEMA", "--kind", "must_fix", "--check", "SC-038",
        "--location", "scripts/gates/_common.py:1", "--repro-json", repro_rel,
    ], cwd=root, capture_output=True, text=True)
    violation = None
    try:
        import jsonschema
        schema = json.loads(schema_proc.stdout)
        instance = json.loads(add_proc.stdout)
        jsonschema.validate(instance=instance, schema=schema)
    except Exception as exc:
        violation = f"{type(exc).__name__}: {exc}"
    passed = schema_proc.returncode == 0 and add_proc.returncode == 0 and violation is None
    return {
        "status": "passed" if passed else "failed",
        "schema_exit_code": schema_proc.returncode,
        "add_exit_code": add_proc.returncode,
        "schema_violation": violation,
        "exit_code": 0 if passed else 1,
    }


def _test_review_missing_agent_fields_guard(base: pathlib.Path) -> dict[str, Any]:
    """合法 dispatch/RED 下，agent 四個 v1 必填欄缺失必須 fail-closed。"""
    root = _adversarial_repo(base)
    agent_path = _valid_review_agent(root)
    _seed_well_formed_red(root)
    ev = root / "specs/workflow-autonomy/evidence"
    dispatch = json.loads((ev / "review-dispatch.json").read_text())
    red = json.loads((ev / "red.json").read_text())
    agent = json.loads(agent_path.read_text())
    required_agent_fields = (
        "before_tests", "after_tests", "reviewed_examples", "assertion_weakened",
    )
    if (dispatch.get("schema_version") != 1 or red.get("schema_version") != 1
            or red.get("status") != "passed"
            or not red.get("runner_results")
            or any(row.get("red_valid") is not True for row in red["runner_results"])
            or any(field not in agent for field in required_agent_fields)):
        raise AssertionError("M13 合法 dispatch/RED/agent prerequisite 不成立")
    for field in required_agent_fields:
        agent.pop(field)
    _write_json(agent_path, agent)

    schema_proc = subprocess.run(
        [str(root / "scripts/gates/test-review"), "--schema"],
        cwd=root, capture_output=True, text=True,
    )
    review_proc = subprocess.run(
        [str(root / "scripts/gates/test-review"), str(SPEC_REL)],
        cwd=root, capture_output=True, text=True,
    )
    stdout_payload = None
    for line in reversed(review_proc.stdout.splitlines()):
        try:
            candidate = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict):
            stdout_payload = candidate
            break
    artifact = json.loads((ev / "test-review.json").read_text())
    stdout_schema_valid = False
    if schema_proc.returncode == 0 and stdout_payload is not None:
        try:
            import jsonschema
            jsonschema.validate(instance=stdout_payload, schema=json.loads(schema_proc.stdout))
            stdout_schema_valid = True
        except Exception:
            pass
    return {
        "status": (stdout_payload or artifact).get("status"),
        "reason": (stdout_payload or artifact).get("reason"),
        "stdout_schema_valid": stdout_schema_valid,
        "exit_code": review_proc.returncode,
    }


def _pre_dashboard_evidence_guard(base: pathlib.Path, missing: str | None) -> dict[str, Any]:
    """--pre-dashboard 只能略過尚未產生的 dashboard direct root。"""
    root = _prepare_manifest_repo(base)
    ev = root / "specs/workflow-autonomy/evidence"
    manifest_path = ev / "delivery.json"
    manifest = json.loads(manifest_path.read_text())
    dashboard_rel = "specs/workflow-autonomy/evidence/dashboard.json"
    manifest["files"] = [row for row in manifest["files"] if row.get("path") != dashboard_rel]
    (ev / "dashboard.json").unlink(missing_ok=True)
    if missing == "delivery":
        manifest_path.unlink()
    elif missing == "status":
        (ev / "status.json").unlink()
        _write_json(manifest_path, manifest)
    elif missing == "findings":
        findings_rel = "specs/workflow-autonomy/evidence/findings.json"
        (ev / "findings.json").unlink()
        manifest["files"] = [row for row in manifest["files"] if row.get("path") != findings_rel]
        _write_json(manifest_path, manifest)
    else:
        _write_json(manifest_path, manifest)
    _git(root, "add", "-A")
    return _run(root, "evidence-check", str(SPEC_REL), "--index", "--pre-dashboard")


def _findings_denied_redispatch_guard(base: pathlib.Path) -> dict[str, Any]:
    root = _adversarial_repo(base)
    ev = root / "specs/workflow-autonomy/evidence"
    _write_json(ev / "findings.json", {"items": [], "dispatched": {}, "summary": {}})
    first = _run(
        root, "findings", str(SPEC_REL), "dispatched", "--gate", "G9",
        "--status", "denied",
    )
    first_state = json.loads((ev / "findings.json").read_text())
    second = _run(
        root, "findings", str(SPEC_REL), "dispatched", "--gate", "G9",
        "--status", "completed",
    )
    final_state = json.loads((ev / "findings.json").read_text())
    return {
        "first_status": (first_state.get("dispatched", {}).get("G9") or {}).get("status"),
        "redispatch_status": second.get("status"),
        "redispatch_reason": second.get("reason"),
        "final_status": (final_state.get("dispatched", {}).get("G9") or {}).get("status"),
        "exit_code": second.get("exit_code"),
    }


def _dashboard_denied_dispatch_guard(base: pathlib.Path) -> dict[str, Any]:
    """其餘 dashboard inputs 合法時，denied dispatch 必須單獨阻擋 G9/G10。"""
    root = _new_repo(base)
    _configure(root, "SC-039", {})
    _approval_fixture(root, "SC-039")
    import yaml
    pipeline_path = root / "specs/pipeline.yaml"
    pipeline = yaml.safe_load(pipeline_path.read_text())
    pipeline["lint"] = pipeline["test"] = pipeline["smoke"] = "true"
    pipeline_path.write_text(yaml.safe_dump(pipeline, allow_unicode=True, sort_keys=False))
    _commit(root, "dashboard denied fixture")
    _delivery_fixture(root, "SC-010", {})
    ev = root / "specs/workflow-autonomy/evidence"
    token_proc = subprocess.run([
        sys.executable, "-c",
        "import pathlib,sys;sys.path.insert(0,'scripts/gates');"
        "from _state import tree_fingerprint;print(tree_fingerprint(pathlib.Path('.').resolve()))",
    ], cwd=root, capture_output=True, text=True, check=True)
    tree_token = token_proc.stdout.strip()
    _write_json(ev / "smoke.json", {
        "ok": True, "exit_code": 0, "timed_out": False, "command": "true",
        "duration_s": 0.0, "screenshots": [], "required_scenarios": [],
        "scenario_results": [], "evidence_errors": [],
        "at": "2026-09-15T00:00:00+08:00", "tree": tree_token,
    })
    _write_json(ev / "findings.json", {
        "items": [],
        "dispatched": {
            "G9": {"at": "2026-09-15T00:00:00+08:00", "tree": tree_token, "status": "denied"},
            "G10": {"at": "2026-09-15T00:00:01+08:00", "tree": tree_token, "status": "completed"},
        },
        "summary": {"proposed": 0, "void": 0, "confirmed": 0},
    })
    test_rel = "scripts/gates/tests/spec_workflow_autonomy.py"
    frozen_files = {test_rel: "sha256:" + hashlib.sha256((root / test_rel).read_bytes()).hexdigest()}
    _write_json(ev / "test-review.json", {
        "schema_version": 1, "status": "passed", "ok": True, "mechanical_only": False,
        "agent": {"status": "passed"}, "files": frozen_files, "errors": [],
    })
    (ev / "tests.hash").write_text(
        f"{frozen_files[test_rel]}  {test_rel}\n"
    )
    manifest_path = ev / "delivery.json"
    manifest = json.loads(manifest_path.read_text())
    direct_roots = {
        "specs/workflow-autonomy/evidence/delivery.json",
        "specs/workflow-autonomy/evidence/status.json",
        "specs/workflow-autonomy/evidence/dashboard.json",
    }
    manifest["files"] = [
        row for row in manifest["files"] if row.get("path") not in direct_roots
    ]
    changed = {
        "specs/workflow-autonomy/evidence/findings.json",
        "specs/workflow-autonomy/evidence/test-review.json",
    }
    for row in manifest["files"]:
        if row.get("path") in changed:
            row["sha256"] = "sha256:" + hashlib.sha256((root / row["path"]).read_bytes()).hexdigest()
    _write_json(manifest_path, manifest)
    _git(root, "add", "-A")
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = subprocess.run(
        [str(root / "scripts/gates/dashboard"), str(SPEC_REL), "--pre-commit"],
        cwd=root, capture_output=True, text=True, timeout=120, env=env,
    )
    result = _parse_json_output(proc)
    dashboard = json.loads((ev / "dashboard.json").read_text())
    gates = {str(row.get("id")): row for row in dashboard.get("gates", [])}
    target = gates.get("G9/10") or {}
    other_failures = [gate for gate, row in gates.items() if gate != "G9/10" and row.get("ok") is not True]
    if other_failures:
        raise AssertionError(f"M19 dashboard prerequisite 未隔離：{other_failures}")
    return {
        "g9_g10_ok": target.get("ok"),
        "denied_reported": "denied" in str(target.get("note", "")).lower(),
        "exit_code": result.get("exit_code"),
    }


def adversarial_register(
    check: Callable[[str, bool, str], None], only_guards: set[str] | None = None,
) -> int:
    """G9/G10 對抗 guard；每一項都在隔離 Git repo 呼叫正式 CLI。"""
    cases: list[tuple[str, str, dict[str, Any], Callable[[pathlib.Path], dict[str, Any]], bool]] = [
        ("E01", "SC-011", {"status": "failed", "delivery_ready": False, "exit_code": 1}, lambda b: _manifest_mutation(b, "missing_manifest"), True),
        ("E02", "SC-011", {"status": "failed", "reason": "invalid_delivery_evidence", "invalid_files": [{"path": "specs/workflow-autonomy/spec.yaml", "reason": "missing"}], "delivery_ready": False, "exit_code": 1}, lambda b: _manifest_mutation(b, "missing_required_root"), True),
        ("E03", "SC-011", {"status": "failed", "reason": "invalid_delivery_evidence", "invalid_files": [{"path": "specs/workflow-autonomy/spec.yaml", "reason": "hash_mismatch"}], "delivery_ready": False, "exit_code": 1}, lambda b: _manifest_mutation(b, "wrong_spec_hash"), True),
        ("E04", "SC-011", {"status": "failed", "reason": "invalid_delivery_evidence", "invalid_files": [{"path": "specs/workflow-autonomy/evidence/approval.json", "reason": "hash_mismatch"}], "delivery_ready": False, "exit_code": 1}, lambda b: _manifest_mutation(b, "wrong_approval_anchor"), True),
        ("E05", "SC-011", {"status": "failed", "reason": "invalid_delivery_evidence", "invalid_files": [{"path": "specs/workflow-autonomy/evidence/status.json", "reason": "hash_mismatch"}], "delivery_ready": False, "exit_code": 1}, lambda b: _manifest_mutation(b, "status_inconsistent"), True),
        ("E06", "SC-011", {"status": "failed", "reason": "invalid_delivery_evidence", "invalid_files": [{"path": "specs/workflow-autonomy/evidence/static-red/adversarial.stderr.log", "reason": "missing"}], "delivery_ready": False, "exit_code": 1}, lambda b: _manifest_mutation(b, "missing_red_reference"), True),
        ("E07", "SC-039", {"status": "passed", "delivery_ready": True, "exit_code": 0}, lambda b: _empty_stream_guard(b, True, True), False),
        ("E08", "SC-031", {"status": "failed", "delivery_ready": False, "exit_code": 1}, lambda b: _empty_stream_guard(b, False, True), False),
        ("E09", "SC-031", {"status": "failed", "delivery_ready": False, "exit_code": 1}, lambda b: _empty_stream_guard(b, True, False), True),
        ("E10", "SC-011", {"status": "failed", "invalid_files": [{"path": "specs/workflow-autonomy/evidence/autonomy.json", "reason": "missing"}], "exit_code": 1}, lambda b: _optional_delivery_root_guard(b, "autonomy.json"), True),
        ("E11", "SC-011", {"status": "failed", "invalid_files": [{"path": "specs/workflow-autonomy/evidence/dashboard.json", "reason": "missing"}], "exit_code": 1}, lambda b: _optional_delivery_root_guard(b, "dashboard.json"), True),
        ("E12", "SC-011", {"status": "failed", "invalid_files": [{"path": "specs/workflow-autonomy/evidence/findings.json", "reason": "missing"}], "exit_code": 1}, lambda b: _optional_delivery_root_guard(b, "findings.json"), True),
        ("E13", "SC-011", {"status": "failed", "invalid_files": [{"path": "specs/workflow-autonomy/evidence/smoke.json", "reason": "missing"}], "exit_code": 1}, _smoke_mode_root_guard, True),
        ("E14", "SC-011", {"status": "failed", "delivery_ready": False, "exit_code": 1}, lambda b: _approval_semantics_guard(b, "missing_hash"), True),
        ("E15", "SC-011", {"status": "failed", "delivery_ready": False, "exit_code": 1}, lambda b: _approval_semantics_guard(b, "wrong_hash"), True),
        ("E16", "SC-011", {"status": "failed", "delivery_ready": False, "exit_code": 1}, lambda b: _approval_semantics_guard(b, "bad_time"), True),
        ("E17", "SC-031", {"status": "failed", "invalid_files": [{"path": "specs/workflow-autonomy/evidence/delivery.json", "reason": "snapshot_mismatch"}], "exit_code": 1}, _manifest_worktree_drift_guard, True),
        ("E18", "SC-031", {"status": "failed", "delivery_ready": False, "exit_code": 1}, lambda b: _red_stream_shape_guard(b, "double_empty"), True),
        ("E19", "SC-054", {"status": "failed", "delivery_ready": False, "exit_code": 1}, lambda b: _red_stream_shape_guard(b, "no_marker"), True),
        ("E20", "SC-011", {"status": "failed", "invalid_files": [{"path": "specs/workflow-autonomy/evidence/autonomy.json", "reason": "missing"}, {"path": "specs/workflow-autonomy/evidence/dashboard.json", "reason": "missing"}, {"path": "specs/workflow-autonomy/evidence/findings.json", "reason": "missing"}], "exit_code": 1}, _missing_v1_roots_guard, True),
        ("E21", "SC-011", {"status": "failed", "invalid_files": [{"path": "specs/workflow-autonomy/evidence/status.json", "reason": "missing"}], "exit_code": 1}, _missing_status_root_guard, True),
        ("D01", "SC-041", {"auto_push_ok": False, "required_inputs_reported": ["autonomy.json", "status.json", "delivery.json", "evidence-check"], "exit_code": 1}, _dashboard_inputs_guard, True),
        ("D02", "SC-041", {"exit_code": 1}, _pr_comment_missing_inputs_guard, True),
        ("T01", "SC-030", _expected_rejection("invalid_independent_review", 1), lambda b: _test_review_agent_guard(b, False), True),
        ("T02", "SC-042", _expected_rejection("assertion_weakened", 1), lambda b: _test_review_agent_guard(b, True), True),
        ("T03", "SC-030", _expected_rejection("invalid_independent_review", 1), _review_token_guard, True),
        ("T04", "SC-030", _expected_rejection("invalid_independent_review", 1), lambda b: _review_contract_guard(b, "dispatch_mismatch"), True),
        ("T05", "SC-030", _expected_rejection("invalid_independent_review", 1), lambda b: _review_contract_guard(b, "reviewed_examples"), True),
        ("T06", "SC-029", _expected_rejection("stale_red_evidence", 1), lambda b: _review_contract_guard(b, "red_raw_reference"), True),
        ("R01", "SC-029", _expected_rejection("stale_red_evidence", 1), _committed_red_reuse_guard, True),
        ("R02", "SC-054", {"failure_class": "error", "gate_exit_code": 1, "red_valid": False}, _binary_static_guard, True),
        ("F01", "SC-038", {"required_action": "full_rerun", "gates": ["G0-G7", "smoke", "G9", "G10"], "may_claim_pass": False, "exit_code": 1}, lambda b: _findings_repro_guard(b, "outside_cwd"), True),
        ("F02", "SC-038", {"required_action": "full_rerun", "gates": ["G0-G7", "smoke", "G9", "G10"], "may_claim_pass": False, "exit_code": 1}, lambda b: _findings_repro_guard(b, "path_indices"), True),
        ("F03", "SC-038", {"required_action": "full_rerun", "gates": ["G0-G7", "smoke", "G9", "G10"], "may_claim_pass": False, "exit_code": 1}, lambda b: _findings_repro_guard(b, "environment"), True),
        ("F04", "SC-031", {"status": "failed", "invalid_files": [{"path": "../outside-input.txt", "reason": "outside_repo"}], "exit_code": 1}, lambda b: _findings_repro_guard(b, "outside_input"), True),
        ("F05", "SC-038", {"required_action": "full_rerun", "gates": ["G0-G7", "smoke", "G9", "G10"], "may_claim_pass": False, "exit_code": 1}, lambda b: _findings_repro_guard(b, "snapshot_drift"), True),
        ("A01", "SC-027", _expected_rejection("invalid_completion_evidence", 1), lambda b: _autonomy_guard(b, "untracked_snapshot"), True),
        ("A02", "SC-058", _expected_rejection("changed_path_outside_repair", 1), lambda b: _autonomy_guard(b, "undeclared_delta"), True),
        ("A03", "SC-047", _expected_rejection("invalid_repair_transition", 1), lambda b: _autonomy_guard(b, "replay_content"), True),
        ("A04", "SC-041", {"status": "blocked", "may_continue": False, "exit_code": 1}, lambda b: _autonomy_guard(b, "check_content"), True),
        ("A05", "SC-041", {"status": "blocked", "may_continue": False, "exit_code": 1}, lambda b: _autonomy_guard(b, "ledger_hash"), True),
        ("A06", "SC-058", _expected_rejection("changed_path_outside_repair", 1), lambda b: _autonomy_guard(b, "verify_delta"), True),
        ("A07", "SC-041", {"status": "blocked", "may_continue": False, "exit_code": 1}, lambda b: _autonomy_guard(b, "ledger_tree"), True),
        ("A08", "SC-041", {"status": "blocked", "may_continue": False, "exit_code": 1}, lambda b: _autonomy_guard(b, "ledger_metadata"), True),
        ("A09", "SC-041", {"status": "blocked", "may_continue": False, "exit_code": 1}, lambda b: _autonomy_guard(b, "ledger_spec_hash"), True),
        ("A10", "SC-041", {"status": "blocked", "may_continue": False, "exit_code": 1}, lambda b: _autonomy_guard(b, "empty_content"), True),
        ("A11", "SC-058", _expected_rejection("changed_path_outside_repair", 1), lambda b: _autonomy_guard(b, "static_red_delta"), True),
        ("A12", "SC-041", {"status": "blocked", "may_continue": False, "exit_code": 1}, lambda b: _autonomy_guard(b, "ledger_blob"), True),
        ("A13", "SC-041", {"status": "blocked", "may_continue": False, "exit_code": 1}, lambda b: _autonomy_guard(b, "ledger_mode"), True),
        ("Z01", "SC-035", {"status": "passed", "exit_code": 0}, lambda b: _freeze_replace_guard(b, True), True),
        ("Z02", "SC-030", _expected_rejection("invalid_independent_review", 1), lambda b: _freeze_replace_guard(b, False), True),
        ("Z03", "SC-030", _expected_rejection("invalid_independent_review", 1), lambda b: _freeze_review_guard(b, "missing_test"), True),
        ("Z04", "SC-030", _expected_rejection("invalid_independent_review", 1), lambda b: _freeze_review_guard(b, "dispatch_mismatch"), True),
        ("Z05", "SC-030", _expected_rejection("invalid_independent_review", 1), lambda b: _freeze_review_guard(b, "reviewed_examples"), True),
        ("C01", "SC-057", _expected_rejection("invalid_cli", 2), _v0_mutation_guard, True),
        ("C02", "SC-057", _expected_rejection("invalid_cli", 2), lambda b: _cli_matrix_guard(b, False), True),
        ("C03", "SC-035", {"status": "passed", "exit_code": 0}, lambda b: _cli_matrix_guard(b, True), True),
        ("C04", "SC-044", {"status": "rejected", "canonical_id": "F-7", "fixes_preserved": True, "exit_code": 1}, _findings_argv_order_guard, True),
        ("C08", "SC-036", {"id": "F-7", "status": "fixed", "action": "preserve", "fixes": 1, "exit_code": 0}, _findings_revalidate_order_guard, True),
        ("F06", "SC-038", _expected_rejection("invalid_repro_schema", 2), lambda b: _findings_add_contract_guard(b, "schema"), True),
        ("F07", "SC-038", _expected_rejection("invalid_repro_schema", 2), lambda b: _findings_add_contract_guard(b, "argv"), True),
        ("F08", "SC-038", _expected_rejection("invalid_repro_schema", 2), lambda b: _findings_add_contract_guard(b, "path_indices"), True),
        ("F09", "SC-038", _expected_rejection("invalid_repro_schema", 2), lambda b: _findings_add_contract_guard(b, "cwd"), True),
        ("F10", "SC-038", _expected_rejection("invalid_repro_schema", 2), lambda b: _findings_add_contract_guard(b, "stdin"), True),
        ("F11", "SC-038", _expected_rejection("invalid_repro_schema", 2), lambda b: _findings_add_contract_guard(b, "environment"), True),
        ("F12", "SC-031", _expected_rejection("invalid_repro_schema", 2), lambda b: _findings_add_contract_guard(b, "input"), True),
        ("F13", "SC-031", _expected_rejection("invalid_repro_schema", 2), lambda b: _findings_add_contract_guard(b, "symlink"), True),
        ("F14", "SC-057", _expected_rejection("invalid_cli", 2), lambda b: _findings_add_contract_guard(b, "location"), True),
        ("F15", "SC-057", _expected_rejection("invalid_cli", 2), lambda b: _findings_add_contract_guard(b, "trailing"), True),
        ("C05", "SC-057", {"status": "rejected", "reason": "invalid_cli", "written": False, "evidence_delta": [], "exit_code": 2}, lambda b: _runs_contract_guard(b, "version0"), True),
        ("C06", "SC-057", {"status": "rejected", "reason": "invalid_cli", "written": False, "evidence_delta": [], "exit_code": 2}, lambda b: _runs_contract_guard(b, "unknown_nested"), True),
        ("C07", "SC-032", {"status": "rejected", "reason": "invalid_status_schema", "written": False, "evidence_delta": [], "exit_code": 2}, lambda b: _runs_contract_guard(b, "merged_blank"), True),
        ("X01", "SC-039", {"status": "blocked", "may_continue": False, "exit_code": 1}, _process_report_guard, True),
        ("M01", "SC-041", {"plan": "planned", "complete": "complete", "before_ledger_commit": "passed", "after_ledger_commit": "passed", "may_continue": True, "exit_code": 0}, _autonomy_post_ledger_commit_guard, True),
        ("M02", "SC-011", {"status": "failed", "reason": "invalid_delivery_evidence", "invalid_files": [{"path": "specs/workflow-autonomy/evidence/approval.json", "reason": "hash_mismatch"}], "delivery_ready": False, "exit_code": 1}, lambda b: _approval_required_field_guard(b, "schema_version"), True),
        ("M03", "SC-011", {"status": "failed", "reason": "invalid_delivery_evidence", "invalid_files": [{"path": "specs/workflow-autonomy/evidence/approval.json", "reason": "hash_mismatch"}], "delivery_ready": False, "exit_code": 1}, lambda b: _approval_required_field_guard(b, "source"), True),
        ("M04", "SC-011", {"status": "failed", "reason": "invalid_delivery_evidence", "invalid_files": [{"path": "specs/workflow-autonomy/evidence/approval.json", "reason": "hash_mismatch"}], "delivery_ready": False, "exit_code": 1}, lambda b: _approval_required_field_guard(b, "source_ref"), True),
        ("M05", "SC-011", {"status": "failed", "reason": "invalid_delivery_evidence", "invalid_files": [{"path": "specs/workflow-autonomy/evidence/status.json", "reason": "hash_mismatch"}], "delivery_ready": False, "exit_code": 1}, _incomplete_status_guard, True),
        ("M06", "SC-011", {"status": "failed", "reason": "invalid_delivery_evidence", "invalid_files": [{"path": "specs/workflow-autonomy/evidence/static-red/undeclared.stderr.log", "reason": "missing"}, {"path": "specs/workflow-autonomy/evidence/static-red/undeclared.stdout.log", "reason": "missing"}], "delivery_ready": False, "exit_code": 1}, _manifest_omits_red_references_guard, True),
        ("M07", "SC-029", _expected_rejection("stale_red_evidence", 1), _invalid_red_review_guard, True),
        ("M08", "SC-030", _expected_rejection("invalid_independent_review", 1), _invalid_red_freeze_guard, True),
        ("M09", "SC-011", {"status": "failed", "reason": "invalid_delivery_evidence", "delivery_ready": False, "exit_code": 1}, _invalid_red_delivery_guard, True),
        ("M10", "SC-039", {"status": "passed", "failed_step": None, "dashboard_root_created": True, "findings_root_created": True, "direct_roots_not_in_manifest": True, "final_direct_roots_present": True, "token_stable_across_status_dashboard_amend": True, "evidence_check_read_only": True, "pre_dashboard_calls_observed": True, "exit_code": 0}, _sc039_required_producers_guard, True),
        ("M11", "SC-038", {"status": "passed", "schema_exit_code": 0, "add_exit_code": 0, "schema_violation": None, "exit_code": 0}, _findings_stdout_schema_guard, True),
        ("M12", "SC-057", {"status": "rejected", "reason": "invalid_cli", "written": False, "evidence_delta": [], "exit_code": 2}, lambda b: _runs_contract_guard(b, "trailing_positional"), True),
        ("M13", "SC-030", {"status": "rejected", "reason": "invalid_independent_review", "stdout_schema_valid": True, "exit_code": 1}, _test_review_missing_agent_fields_guard, True),
        ("M14", "SC-039", {"status": "passed", "storage": "index", "delivery_ready": True, "exit_code": 0}, lambda b: _pre_dashboard_evidence_guard(b, None), True),
        ("M15", "SC-039", {"status": "failed", "reason": "missing_delivery_manifest", "delivery_ready": False, "exit_code": 1}, lambda b: _pre_dashboard_evidence_guard(b, "delivery"), True),
        ("M16", "SC-039", {"status": "failed", "reason": "invalid_delivery_evidence", "invalid_files": [{"path": "specs/workflow-autonomy/evidence/status.json", "reason": "missing"}], "delivery_ready": False, "exit_code": 1}, lambda b: _pre_dashboard_evidence_guard(b, "status"), True),
        ("M17", "SC-039", {"status": "failed", "reason": "invalid_delivery_evidence", "invalid_files": [{"path": "specs/workflow-autonomy/evidence/findings.json", "reason": "missing"}], "delivery_ready": False, "exit_code": 1}, lambda b: _pre_dashboard_evidence_guard(b, "findings"), True),
        ("M18", "SC-039", {"first_status": "denied", "redispatch_status": "rejected", "redispatch_reason": "dispatch_denied", "final_status": "denied", "exit_code": 1}, _findings_denied_redispatch_guard, True),
        ("M19", "SC-039", {"g9_g10_ok": False, "denied_reported": True, "exit_code": 1}, _dashboard_denied_dispatch_guard, True),
    ]
    for guard_id, scenario, expected, runner, must_red in cases:
        if only_guards is not None and guard_id not in only_guards:
            continue
        with tempfile.TemporaryDirectory(prefix=f"workflow-adversarial-{guard_id.lower()}-") as td:
            actual = runner(pathlib.Path(td))
        ok = assertThat(actual, expected)
        expectation = "vulnerability_projection" if must_red else "approved_or_reverse_projection"
        detail = (
            f"ADVERSARIAL_ASSERTION: {guard_id} scenario={scenario} expectation={expectation} "
            f"expected={_canonical(expected)} actual={_canonical(actual)}"
        )
        check(f"{guard_id} {scenario} {expectation}", ok, detail)
    return sum(1 for guard_id, *_ in cases if only_guards is None or guard_id in only_guards)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case")
    parser.add_argument("--example", type=int)
    parser.add_argument("--adversarial", action="store_true")
    parser.add_argument("--adversarial-guard", action="append", default=[])
    args = parser.parse_args(argv)
    if (args.case is None) != (args.example is None):
        parser.error("--case 與 --example 必須一起提供")

    results: list[tuple[bool, str, str]] = []

    def record(name: str, ok: bool, detail: str) -> None:
        results.append((ok, name, detail))

    only = (args.case, args.example) if args.case is not None else None
    guard_filter = set(args.adversarial_guard) or None
    if guard_filter is not None and not args.adversarial:
        parser.error("--adversarial-guard 需要搭配 --adversarial")
    selected = adversarial_register(record, guard_filter) if args.adversarial else register(record, only)
    if selected == 0:
        print("找不到指定的 Scenario/example")
        return 2

    failed = 0
    for ok, name, detail in results:
        print(f"  {'✓' if ok else '✘'} {name}")
        if not ok:
            failed += 1
            print(detail)
    print(f"\nworkflow-autonomy: {selected - failed}/{selected} 通過")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
