#!/usr/bin/env bash
# Setup claude-workflow on a new machine.
#
# Usage:
#   ./scripts/setup.sh
#
# What it does:
#   1. Checks required tools (claude, codex, git, node)
#   2. Symlinks skills/workflow-orchestrator/ into ~/.claude/skills/
#   3. Symlinks commands/workflow.md and commands/workflow/ into ~/.claude/commands/
#   4. Optionally copies templates/codex-AGENTS.md to ~/.codex/AGENTS.md
#   5. Prints next steps for project-level AGENTS.md and memory

set -euo pipefail

CLAUDE_DIR="${CLAUDE_DIR:-$HOME/.claude}"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKUP_DIR="$CLAUDE_DIR/backups/setup-$(date +%Y%m%d-%H%M%S)"
BACKUP_USED=0

backup_path() {
  # Move an existing path into BACKUP_DIR (created lazily so empty runs leave no folder).
  local src="$1"
  if [ "$BACKUP_USED" -eq 0 ]; then
    mkdir -p "$BACKUP_DIR"
    BACKUP_USED=1
  fi
  mv "$src" "$BACKUP_DIR/$(basename "$src")"
  echo "    Backed up: $src -> $BACKUP_DIR/$(basename "$src")"
}

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
    backup_path "$SKILL_DST"
    ln -s "$SKILL_SRC" "$SKILL_DST"
    echo "    Re-linked: $SKILL_DST -> $SKILL_SRC"
  fi
elif [ -e "$SKILL_DST" ]; then
  echo "==> Existing directory at $SKILL_DST — backing up."
  backup_path "$SKILL_DST"
  ln -s "$SKILL_SRC" "$SKILL_DST"
  echo "    Linked: $SKILL_DST -> $SKILL_SRC"
else
  ln -s "$SKILL_SRC" "$SKILL_DST"
  echo "==> Linked $SKILL_DST -> $SKILL_SRC"
fi
echo ""

# 3. Symlink slash commands (/workflow + /workflow:* sub-commands)
mkdir -p "$CLAUDE_DIR/commands"

link_command() {
  # $1 = source path inside repo, $2 = destination path in ~/.claude/commands
  local src="$1"
  local dst="$2"
  if [ -L "$dst" ]; then
    local current_target
    current_target="$(readlink "$dst")"
    if [ "$current_target" = "$src" ]; then
      echo "==> Symlink already correct: $dst -> $src"
      return
    fi
    echo "==> Existing symlink points elsewhere ($current_target). Backing up."
    backup_path "$dst"
  elif [ -e "$dst" ]; then
    echo "==> Existing path at $dst — backing up."
    backup_path "$dst"
  fi
  ln -s "$src" "$dst"
  echo "    Linked: $dst -> $src"
}

link_command "$REPO_DIR/commands/workflow.md" "$CLAUDE_DIR/commands/workflow.md"
link_command "$REPO_DIR/commands/workflow"    "$CLAUDE_DIR/commands/workflow"
echo ""

# 4. Optional: Copy global codex AGENTS.md
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
if [ "$BACKUP_USED" -eq 1 ]; then
  echo "    Pre-existing paths were backed up to: $BACKUP_DIR"
  echo "    Delete that directory once you've confirmed the new symlinks work."
fi
echo ""
echo "Next steps:"
echo "  - For each project repo, copy and customize the template:"
echo "      cp $REPO_DIR/templates/project-AGENTS.md.template <repo>/AGENTS.md"
echo "  - Restore project memory (private repo):"
echo "      mkdir -p ~/.claude/projects/-Users-\$(whoami)-<project>"
echo "      git clone <your-private-memory-repo> ~/.claude/projects/-Users-\$(whoami)-<project>/memory"
echo "  - Restart Claude Code so it picks up the new skill."
