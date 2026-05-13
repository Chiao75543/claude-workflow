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
#     for each skill convention referenced by workflow-orchestrator
#     (test-writer, rd-implementer, code-reviewer, reporter, gitlab-mr-reviewer,
#     review-fixer — see workflow-orchestrator's "Project bindings" section).
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
else
  echo "No unresolved placeholders detected."
fi

echo ""
echo "Restart Claude Code in $TARGET so the project-local skills get loaded."
