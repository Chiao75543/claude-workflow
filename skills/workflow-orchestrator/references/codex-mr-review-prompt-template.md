# Codex MR-review prompt template (Stage 10.5)

Used when dispatching `Agent(subagent_type="codex:codex-rescue", prompt=…)` for the post-push advisory review.

## Key contract

| Concern | Owner |
|---|---|
| Read MR diff, classify findings | Codex |
| Post inline DiffNote comments | **Dispatcher** (main shell) |
| Post summary `glab mr note` | **Dispatcher** |
| Compute weighted score | Codex (returns; dispatcher posts) |

Codex sandbox typically cannot reach the GitLab API host. Treat codex's job as **analysis-only**; the dispatcher relays.

## Pre-flight (dispatcher gathers before dispatch)

```bash
glab mr view {MR_ID}
glab mr diff {MR_ID}
glab api projects/{PROJECT_PATH_ENCODED}/merge_requests/{MR_ID} \
  | jq '{base: .diff_refs.base_sha, head: .diff_refs.head_sha, start: .diff_refs.start_sha, web: .web_url}'
git remote get-url origin   # for project-path inference
```

Save: `base_sha`, `head_sha`, `start_sha`, `gitlab_host` (from `web_url`), `project_path_encoded`.

## Prompt template

```
You are running as Codex acting as a senior {PROJECT} code reviewer per the
`mr-reviewer` skill.

**Working directory**: {WORKTREE_PATH} (branch {BRANCH})

**MR to review**: GitLab MR !{MR_ID} at {MR_WEB_URL}
- Title: {MR_TITLE}
- Target branch: {TARGET_BRANCH}
- Spec: {SPEC_PATH or "n/a"}

**SHA refs**:
- base_sha={BASE_SHA}
- head_sha={HEAD_SHA}
- start_sha={START_SHA}
- gitlab_host={GITLAB_HOST}
- project_path_encoded={PROJECT_PATH_ENCODED}

**Files in scope** (production + tests; SKIP `openspec/changes/**/*.md`):
{FILE_LIST_WITH_DIFF_STATS}

**Project conventions**: {CLAUDE_MD_PATH} — read it for:
- Magic Numbers as constants
- No `// region` blocks
- ApiResponse safety (`requireData()` / `getDataOrNull()`, never `!!`)
- KDoc on public APIs
- Compose: composable naming / modifier rules / parameter order

**Prior review state**: {PRIOR_REVIEW_SUMMARY — e.g. "6 reviewer passes (Stage 6×3, Stage 7×3) with 0 CRITICAL; see review.md"}

**Your tasks**:

1. Read each file in scope fully (`cat <file>` for context — `glab mr diff` for the change deltas).
2. Analyze per CRITICAL / WARNING / SUGGESTION / SIMPLIFY taxonomy.
   - Set the bar HIGH if prior reviews already passed; only raise items prior reviewers genuinely missed.
   - Do NOT duplicate items already in {REVIEW_MD_PATH}.
3. **DO NOT** post comments yourself — the GitLab API host is typically blocked from your sandbox.
4. Return your findings as a structured payload AND a draft summary. The dispatcher (main shell) will relay both to GitLab.

**Return format** (strict — dispatcher parses this):

```yaml
findings:
  - severity: CRITICAL | WARNING | SUGGESTION | SIMPLIFY
    file: <relative path from repo root>
    line: <integer, line number in the new file>
    diff_position:
      old_path: <same as file, or new path for rename>
      new_path: <same as file>
      new_line: <line>          # for additions / modifications-as-add
      old_line: <line>          # for deletions / modifications-as-delete
    body: |
      **[severity emoji + tag]** 問題標題

      **問題**: 具體描述

      **建議修正**:
      ```kotlin
      // 修正後程式碼
      ```

      ---
      *🤖 Reviewed by Codex*

score:
  architecture_compliance: <0..100>
  code_quality: <0..100>
  security_null_safety: <0..100>
  maintainability: <0..100>
  compose_android: <0..100>
  weighted_total: <0..100>            # 25 / 25 / 20 / 15 / 15

verdict: mergeable | not_mergeable      # not_mergeable iff ≥1 CRITICAL

summary_markdown: |
  ## 📋 Code Review Summary

  ### Overview Score: **{weighted_total} / 100** — {評級}

  | 評分項目 | 分數 | 權重 | 加權分 |
  ...
  (full skill Step 9 markdown template)
  ---
  *🤖 Reviewed by Codex*
```

**Hard rules**:
- Traditional Chinese for comment bodies (technical terms in English).
- Skip OpenSpec markdown files entirely.
- Do NOT propose changes outside the change's declared scope (e.g., renames the design.md explicitly defers).
- If you find zero defensible issues, return `findings: []` and a clean summary — dispatcher will skip inline posts but still post the summary.
```

## Dispatcher post-receipt logic

After codex returns the payload, dispatcher (main Claude shell):

1. **For each finding** → curl POST DiffNote with `body` + `position` fields:
   ```bash
   curl -s --request POST \
     --header "PRIVATE-TOKEN: $(glab auth status -t 2>&1 | grep -oE 'gl[a-zA-Z0-9_-]+')" \
     --header "Content-Type: application/json" \
     --data @<(jq -n --argjson f "$FINDING_JSON" '{body: $f.body, position: $f.diff_position + {base_sha: $base, start_sha: $start, head_sha: $head, position_type: "text"}}') \
     "http://{GITLAB_HOST}/api/v4/projects/{PROJECT_PATH_ENCODED}/merge_requests/{MR_ID}/discussions"
   ```
   Verify response contains `"type":"DiffNote"`. If `"Note"` → position mis-set; retry with corrected line.

2. **Post summary**:
   ```bash
   glab mr note {MR_ID} --message "$summary_markdown"
   ```

3. **Report back to user** in chat:
   - `{N_CRITICAL} CRITICAL / {N_WARN} WARNING / {N_SUGG} SUGGESTION / {N_SIMP} SIMPLIFY`
   - Score `{weighted_total} / 100`
   - Verdict + link to summary note URL

## Idempotency check (recommended)

Before dispatching codex, check if a `*🤖 Reviewed by Codex*`-signed discussion already exists on the MR:

```bash
glab api projects/{PROJECT_PATH_ENCODED}/merge_requests/{MR_ID}/discussions \
  | jq '[.[] | select(.notes[]?.body | contains("🤖 Reviewed by Codex"))] | length'
```

If ≥1 and user did not request `--re-review`, skip Stage 10.5 and inform user.
