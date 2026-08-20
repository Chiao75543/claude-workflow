#!/usr/bin/env bash
# Stage 12 archive — moves a change spec into archive/ and merges its
# Requirements into openspec/specs/{capability}/spec.md.
#
# Stage 12 pre-merge archive: run on the feature branch after reviewer
# approval + user OK-to-merge, BEFORE the final merge, so feature + archive
# ship together in one MR.
#
# Standalone fallback for projects without the openspec CLI. Prefer
# `openspec archive <name> --yes` when available — the CLI also runs
# `openspec validate` and does a real MODIFIED delta merge, which this
# script does not (see NOTE below).
#
# Usage: scripts/archive.sh <change-name>
#
# Expects openspec/changes/<name>/.openspec.yaml with at least:
#   change_type: ADDED | MODIFIED
#   capability:  <capability-name>      # equals <name> for ADDED
#
# NOTE on the spec merge: the ADDED path is a straightforward copy with the
# section prefix stripped. The MODIFIED path is non-trivial (diff-merge into
# an existing capability spec) — this scaffold appends a marked block so the
# content is not silently dropped. Replace the MODIFIED branch with the real
# OpenSpec merger once available.

set -euo pipefail

# All paths below are repo-relative; don't depend on the caller's CWD.
if TOPLEVEL="$(git rev-parse --show-toplevel 2>/dev/null)"; then
  cd "${TOPLEVEL}"
fi

NAME="${1:?usage: scripts/archive.sh <change-name>}"
CHANGE_DIR="openspec/changes/${NAME}"
DATE="$(date -u +%Y-%m-%d)"
ARCHIVE_DIR="openspec/changes/archive/${DATE}-${NAME}"

if [ ! -d "${CHANGE_DIR}" ]; then
  echo "error: ${CHANGE_DIR} not found" >&2
  exit 1
fi

META="${CHANGE_DIR}/.openspec.yaml"
if [ ! -f "${META}" ]; then
  echo "error: ${META} missing — cannot determine capability/change_type" >&2
  exit 1
fi

CHANGE_TYPE="$(awk -F': *' '/^change_type:/ {print $2; exit}' "${META}" | tr -d '[:space:]')"
CAPABILITY="$(awk -F': *' '/^capability:/  {print $2; exit}' "${META}" | tr -d '[:space:]')"
: "${CHANGE_TYPE:?missing change_type in ${META}}"
: "${CAPABILITY:?missing capability in ${META}}"

SRC_SPEC="${CHANGE_DIR}/specs/${NAME}/spec.md"
DST_DIR="openspec/specs/${CAPABILITY}"
DST_SPEC="${DST_DIR}/spec.md"

if [ ! -f "${SRC_SPEC}" ]; then
  echo "error: ${SRC_SPEC} not found" >&2
  exit 1
fi

mkdir -p "${DST_DIR}"

case "${CHANGE_TYPE}" in
  ADDED)
    if [ -e "${DST_SPEC}" ]; then
      echo "error: ${DST_SPEC} already exists but change_type=ADDED" >&2
      exit 1
    fi
    sed 's/^## ADDED Requirements/## Requirements/' "${SRC_SPEC}" > "${DST_SPEC}"
    ;;
  MODIFIED)
    if [ ! -e "${DST_SPEC}" ]; then
      echo "error: ${DST_SPEC} missing but change_type=MODIFIED" >&2
      exit 1
    fi
    # TODO: real diff-merge of "## MODIFIED Requirements" into the existing
    # capability spec. Scaffold appends a clearly-marked block so the content
    # is preserved and visible in review.
    {
      printf '\n<!-- merged from change %s on %s -->\n' "${NAME}" "${DATE}"
      cat "${SRC_SPEC}"
    } >> "${DST_SPEC}"
    ;;
  *)
    echo "error: unknown change_type=${CHANGE_TYPE} (expected ADDED or MODIFIED)" >&2
    exit 1
    ;;
esac

mkdir -p "$(dirname "${ARCHIVE_DIR}")"
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git mv "${CHANGE_DIR}" "${ARCHIVE_DIR}"
  git add "${DST_SPEC}"
else
  mv "${CHANGE_DIR}" "${ARCHIVE_DIR}"
fi

echo "archived: ${NAME} -> ${ARCHIVE_DIR}"
echo "capability spec: ${DST_SPEC} (${CHANGE_TYPE})"
