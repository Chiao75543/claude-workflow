#!/usr/bin/env bash
# Opt-in setup for the Codex-specific lean workflow skill.

set -euo pipefail

CODEX_SKILLS_DIR="${CODEX_SKILLS_DIR:-$HOME/.agents/skills}"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$REPO_DIR/skills/codex-workflow"
DST="$CODEX_SKILLS_DIR/codex-workflow"

if [ ! -f "$SRC/SKILL.md" ]; then
  echo "Error: missing Codex skill source: $SRC/SKILL.md"
  exit 1
fi

mkdir -p "$CODEX_SKILLS_DIR"
if [ -L "$DST" ] && [ "$(readlink "$DST")" = "$SRC" ]; then
  echo "Codex skill already linked: $DST -> $SRC"
  exit 0
fi
if [ -e "$DST" ] || [ -L "$DST" ]; then
  echo "Error: destination already exists: $DST"
  echo "Remove or relocate it explicitly, then run this setup again."
  exit 1
fi

ln -s "$SRC" "$DST"
echo "Linked Codex skill: $DST -> $SRC"
echo "Invoke it as \$codex-workflow; restart Codex only if it does not appear."
