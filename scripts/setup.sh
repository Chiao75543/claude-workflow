#!/usr/bin/env bash
# Setup claude-workflow on a new machine.
#
# Usage:
#   ./scripts/setup.sh
#
# What it does:
#   1. Checks required tools (claude, codex, git, node)
#   2. Symlinks skills/workflow-orchestrator/ into ~/.claude/skills/
#   3. Optionally copies templates/codex-AGENTS.md to ~/.codex/AGENTS.md
#   4. Prints next steps for project-level AGENTS.md and memory

set -euo pipefail

CLAUDE_DIR="${CLAUDE_DIR:-$HOME/.claude}"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> claude-workflow setup"
echo "    Repo:   $REPO_DIR"
echo "    Target: $CLAUDE_DIR"
echo ""

# 1. Check tool dependencies
echo "==> Checking tool dependencies..."
missing=0
for tool in claude codex git node npm glab gh; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "    [MISSING] $tool"
    missing=1
  else
    echo "    [ok]      $tool ($(command -v "$tool"))"
  fi
done
if [ "$missing" -eq 1 ]; then
  echo ""
  echo "    Install missing tools before continuing. See README.md."
fi
echo ""

# 2. Symlink workflow-orchestrator skill
mkdir -p "$CLAUDE_DIR/skills"
SKILL_SRC="$REPO_DIR/skills/workflow-orchestrator"
SKILL_DST="$CLAUDE_DIR/skills/workflow-orchestrator"
if [ -L "$SKILL_DST" ]; then
  current_target="$(readlink "$SKILL_DST")"
  if [ "$current_target" = "$SKILL_SRC" ]; then
    echo "==> Symlink already correct: $SKILL_DST -> $SKILL_SRC"
  else
    echo "==> Existing symlink points elsewhere ($current_target). Backing up."
    mv "$SKILL_DST" "$SKILL_DST.bak.$(date +%s)"
    ln -s "$SKILL_SRC" "$SKILL_DST"
    echo "    Re-linked: $SKILL_DST -> $SKILL_SRC"
  fi
elif [ -e "$SKILL_DST" ]; then
  echo "==> Existing directory at $SKILL_DST — backing up to $SKILL_DST.bak.$(date +%s)"
  mv "$SKILL_DST" "$SKILL_DST.bak.$(date +%s)"
  ln -s "$SKILL_SRC" "$SKILL_DST"
  echo "    Linked: $SKILL_DST -> $SKILL_SRC"
else
  ln -s "$SKILL_SRC" "$SKILL_DST"
  echo "==> Linked $SKILL_DST -> $SKILL_SRC"
fi
echo ""

# 3. Optional: Copy global codex AGENTS.md
if [ -t 0 ]; then
  read -r -p "==> Copy templates/codex-AGENTS.md to ~/.codex/AGENTS.md? [y/N] " yn
  if [[ "${yn:-}" =~ ^[Yy]$ ]]; then
    mkdir -p "$HOME/.codex"
    if [ -f "$HOME/.codex/AGENTS.md" ]; then
      mv "$HOME/.codex/AGENTS.md" "$HOME/.codex/AGENTS.md.bak.$(date +%s)"
      echo "    Existing AGENTS.md backed up."
    fi
    cp "$REPO_DIR/templates/codex-AGENTS.md" "$HOME/.codex/AGENTS.md"
    echo "    Copied to ~/.codex/AGENTS.md"
  fi
fi
echo ""

echo "==> Done."
echo ""
echo "Next steps:"
echo "  - For each project repo, copy and customize the template:"
echo "      cp $REPO_DIR/templates/project-AGENTS.md.template <repo>/AGENTS.md"
echo "  - Restore project memory (private repo):"
echo "      mkdir -p ~/.claude/projects/-Users-\$(whoami)-<project>"
echo "      git clone <your-private-memory-repo> ~/.claude/projects/-Users-\$(whoami)-<project>/memory"
echo "  - Restart Claude Code so it picks up the new skill."
