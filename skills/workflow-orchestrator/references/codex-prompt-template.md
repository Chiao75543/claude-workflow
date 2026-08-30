# Codex prompt templates for Stage 11

Stage 11 派 codex (via `codex:codex-rescue` agent) 修 PR review comments。codex **不會**自動套用 Claude Code skill — 它看到的只有 `<repo>/AGENTS.md` + `~/.codex/AGENTS.md` + 我們派遣時的 prompt + repo files。

兩個 prompt：**plan only** (Step 2b) 和 **apply fix** (Step 2d)。每條 CRITICAL/WARNING comment 跑兩次：先 plan、user 同意、再 apply。

---

## Step 2b prompt — PLAN ONLY

```
You are continuing on an in-progress PR. Produce a fix PLAN for the
review comment below. THIS RUN IS PLAN ONLY — DO NOT edit any files,
DO NOT commit, DO NOT run tests yet.

## PR context

- Repository: {repo_root}
- PR / MR: #{PR_ID}, branch: {branch_name}
- Base branch: {INTEGRATION_BRANCH}
- Related spec: openspec/changes/{name}/specs/{name}/spec.md
- Spec section relevant to this fix:

  {paste the matching Requirement + Scenario verbatim}

## The reviewer comment

- File: {file_path}:{line_number}
- Severity: {CRITICAL | WARNING}
- Reviewer: {reviewer_name}
- Body (verbatim):

  > {comment body, preserve formatting}

## Your output (markdown)

1. **Files to edit** — list each path you will touch.
2. **Changes per file** — 1-3 bullets per file, what and why.
3. **Spec mapping** — which Scenario(s) the fix satisfies; flag any
   tension with another Scenario.
4. **Side-effects / risks** — what could break elsewhere.
5. **Confidence** — low / medium / high. Explain in one sentence.
6. **Open questions** (optional) — things you would ask a human if
   you could.

## Hard rules

- Plan only. No edits, no commits, no test runs.
- Minimal scope: address THIS comment only, no drive-by refactoring.
- If the comment seems wrong or contradicts the spec, say so in
  "Open questions" — do not silently override the reviewer.
- If you cannot form a plan with the given context (missing file,
  unclear ask), report "INSUFFICIENT CONTEXT" and list what you need.
```

---

## Step 2d prompt — APPLY FIX

Use after the user approves the plan from 2b.

```
The plan you produced was approved. Apply the fix now.

## PR context

(Same as Step 2b — repeat the same context block verbatim so codex
has it in this run.)

## The approved plan

{paste the plan from 2b, including any user `modify <text>` adjustments}

## What to do now

1. Apply the changes exactly as planned. Do not deviate without
   stating why in your output.
2. After editing, run the relevant tests:
   {test command, e.g. `./gradlew test --tests "*MatchingTest*"`}
3. Commit locally with this message format:

   ```
   fix(review): {scope} address {file}:{line} - {one-line summary}

   Comment: {reviewer_name} on {file}:{line}
   PR: #{PR_ID}
   Spec: openspec/changes/{name}/specs/{name}/spec.md
   Scenarios: {scenario-name}
   AI-assisted: codex
   ```

4. Do NOT push. Do NOT mark the discussion as resolved — the
   pipeline (Stage 11 Step 2f) handles resolve after the human
   verifies the diff.

## Your output (markdown)

- **Files changed** with line counts (e.g. `Foo.kt: +12 -3`)
- **Test result** — pass / fail; if fail, show the failure
- **Commit hash** (`git rev-parse HEAD` after commit)
- **Deviation from plan** — if any; explain why
- **Self-doubt** — anything you are unsure about, surface here so
  the human can catch it at Step 2e
```

---

## Variants

### Read-only investigation (rare)

If at Step 2b codex returns INSUFFICIENT CONTEXT, send a follow-up
read-only run:

```
Investigate why the reviewer flagged {file}:{line} as {severity}.
Do NOT edit anything. Output:
1. What the current code does
2. What the spec/Scenario expects
3. The gap between the two
4. A revised plan you can act on
```

Then return to Step 2b with the enriched context.

### Multi-file refactor needed for a single comment

If the plan in 2b requires editing > 5 files or > 200 LoC, surface
this to the user explicitly:

```
NOTE: This fix touches {N} files / {M} LoC. This exceeds the
"minimal scope" rule. Options:
- Proceed (user override)
- Narrow the fix (return revised plan)
- Split into a separate PR after this one merges
```

User decides at Step 2c before approval.

---

## Why prompt templates instead of relying on AGENTS.md

`AGENTS.md` carries **long-lived repo rules** (architecture, naming,
test commands). The prompt carries **per-comment context** (which
file, which Scenario, what the reviewer said). Both are needed.

If something is true for every PR comment fix in this repo, move it
to `AGENTS.md`. If it changes per comment, keep it in the prompt.

---

## Sanity check before sending

Before invoking `Agent(subagent_type="codex:codex-rescue", ...)`:

- [ ] Spec section pasted verbatim (not just path)
- [ ] Comment body verbatim (no paraphrasing)
- [ ] Test command for this repo / module is correct
- [ ] Commit message template includes Spec + Scenarios + AI-assisted footer
- [ ] Prompt says "do not push", "do not resolve discussion"
- [ ] Step 2b says PLAN ONLY; Step 2d says APPLY

Missing items above are the most common reason for codex producing
output the user has to reject at Step 2c / 2e.
