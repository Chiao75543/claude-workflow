#!/usr/bin/env bash
# Scaffold a project's workflow-orchestrator binding skills from a stack template.
#
# Usage:
#   ./scripts/init-project.sh <stack> <target-repo>
#
# Example:
#   ./scripts/init-project.sh android ~/code/myapp
#
# What it does:
#   - Copies templates/skills/<stack>/<name>/SKILL.md → <target>/.claude/skills/<name>/SKILL.md
#     for each skill convention referenced by workflow-orchestrator.
#     Only two remain project-local (test-writer, rd-implementer) — the other
#     four were replaced by scripts/gates/* and the shipped agents/*.
#     Also scaffolds specs/pipeline.yaml, the machine-readable stack binding
#     the gate scripts read (AGENTS.md is prose for the AI; this is for scripts).
#   - Auto-substitutes {PROJECT_ROOT} with the absolute path of <target-repo>.
#   - Backs up any pre-existing skill file in-place as SKILL.md.bak.<ts>.
#   - Lists remaining placeholders the user must edit by hand.

set -euo pipefail

stack="${1:-}"
target="${2:-}"

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TEMPLATES_DIR="$REPO_DIR/templates/skills"

if [ -z "$stack" ] || [ -z "$target" ]; then
  echo "Usage: $0 <stack> <target-repo>"
  echo ""
  echo "Available stacks:"
  if [ -d "$TEMPLATES_DIR" ]; then
    find "$TEMPLATES_DIR" -mindepth 1 -maxdepth 1 -type d -exec basename {} \; | sed 's/^/  - /'
  else
    echo "  (no templates dir at $TEMPLATES_DIR)"
  fi
  exit 1
fi

SRC_DIR="$TEMPLATES_DIR/$stack"

if [ ! -d "$SRC_DIR" ]; then
  echo "Error: no template for stack '$stack' (looked in $SRC_DIR)"
  echo ""
  echo "Available stacks:"
  find "$TEMPLATES_DIR" -mindepth 1 -maxdepth 1 -type d -exec basename {} \; | sed 's/^/  - /'
  exit 1
fi

if [ ! -d "$target" ]; then
  echo "Error: target repo not found: $target"
  exit 1
fi

TARGET="$(cd "$target" && pwd)"
DST_DIR="$TARGET/.claude/skills"

echo "==> Scaffolding '$stack' skill set"
echo "    Source: $SRC_DIR"
echo "    Target: $DST_DIR"
echo ""

mkdir -p "$DST_DIR"
ts="$(date +%Y%m%d-%H%M%S)"
copied=0
for skill_dir in "$SRC_DIR"/*/; do
  [ -d "$skill_dir" ] || continue
  name="$(basename "$skill_dir")"
  src_file="$skill_dir/SKILL.md"
  [ -f "$src_file" ] || { echo "    [skip]   $name (no SKILL.md in template)"; continue; }
  dst_file="$DST_DIR/$name/SKILL.md"
  mkdir -p "$DST_DIR/$name"
  if [ -f "$dst_file" ]; then
    backup="$dst_file.bak.$ts"
    cp "$dst_file" "$backup"
    echo "    [backup] $dst_file"
    echo "             -> $(basename "$backup")"
  fi
  # Auto-substitute {PROJECT_ROOT}; other placeholders left for hand-edit.
  sed "s|{PROJECT_ROOT}|$TARGET|g" "$src_file" > "$dst_file"
  echo "    [write]  $dst_file"
  copied=$((copied + 1))
done

# Scaffold the machine-readable stack binding the gate scripts read.
PIPELINE_CFG="$TARGET/specs/pipeline.yaml"
if [ -f "$PIPELINE_CFG" ]; then
  echo "    [keep]   $PIPELINE_CFG (already exists)"
else
  mkdir -p "$TARGET/specs"
  cat > "$PIPELINE_CFG" <<'CFG'
# 機器可讀的技術棧綁定,給 scripts/gates/* 用。
# AGENTS.md 是寫給 AI 讀的散文;這份是給腳本讀的。
# 每個 {PLACEHOLDER} 都要手動填。

runner: {TEST_OUTPUT_FORMAT}        # red-capture 的輸出解析器,例如 swift-testing

tests:
  globs:
    - "{TEST_GLOB}"                 # 例如 "Packages/*/Tests/**/*.swift"
  # 慣例:測試描述以 Scenario 編號開頭
  scenario_pattern: '(SC-\d+[a-z]?)'

reachability:
  globs:
    - "{APP_SOURCE_GLOB}"           # G8 在哪裡找建構點,例如 "App/**/*.swift"

lint: "{LINT_COMMAND}"
CFG
  echo "    [write]  $PIPELINE_CFG"
fi

echo ""
echo "==> Done. $copied skill(s) scaffolded."
echo ""
echo "Auto-substituted:"
echo "  {PROJECT_ROOT} = $TARGET"
echo ""

# List remaining placeholders found in the generated files.
remaining="$(grep -rohE '\{[A-Z_]+\}' "$DST_DIR" 2>/dev/null | sort -u || true)"
if [ -n "$remaining" ]; then
  echo "Remaining placeholders to edit by hand (search & replace in $DST_DIR):"
  echo "$remaining" | sed 's/^/  /'
  echo ""
  echo "Suggested mappings (Android example):"
  echo "  {PACKAGE_NAME}        — e.g. com.example.myapp"
  echo "  {PACKAGE_PATH}        — e.g. com/example/myapp (slash form)"
  echo "  {TEST_COMMAND}        — e.g. ./gradlew test"
  echo "  {TICKET_PREFIX}       — e.g. AIP / JIRA / GH"
  echo "  {GITLAB_PROJECT_PATH} — e.g. team/group/myapp"
  echo "  {GITLAB_API_HOST}     — GitLab API host or IP"
  echo "  {GITLAB_WEB_HOST}     — GitLab web UI host"
  echo "  {INTEGRATION_BRANCH}  — e.g. developer / main"
  echo "  {TEST_OUTPUT_FORMAT}  — red-capture parser: swift-testing (add more in scripts/gates/red-capture)"
  echo "  {TEST_GLOB}           — where the tests live"
  echo "  {APP_SOURCE_GLOB}     — where G8 looks for construction sites"
  echo "  {LINT_COMMAND}        — lint command (checked on changed files only)"
else
  echo "No unresolved placeholders detected."
fi

echo ""
echo "Restart Claude Code in $TARGET so the project-local skills get loaded."
