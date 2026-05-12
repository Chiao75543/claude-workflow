---
name: workflow
description: End-to-end pipeline from a feature description to a pushed branch — spec authoring (brainstorm + grill + OpenSpec auto-split), TDD tests, implementation, commit, push, with 2–3 parallel reviewer agents at every stage. Supports --fast (1 combined reviewer per stage) and --full overrides.
category: Workflow
tags: [workflow, pipeline, openspec, tdd]
---

Run the end-to-end workflow pipeline.

**Input** (passed as `$ARGUMENTS` after `/workflow`):
- Free-text feature description, e.g. `/workflow 新增使用者登入功能`
- Optional flags:
  - `--fast` → force fast mode (1 combined reviewer per stage)
  - `--full` → force full mode (2–3 parallel reviewers per stage)

**Action**

Invoke the `workflow-orchestrator` skill via the **Skill tool** immediately, passing `$ARGUMENTS` as the `args`. Do NOT use the Read tool on the skill file — let the Skill tool load it.

```
Skill(skill="workflow-orchestrator", args="$ARGUMENTS")
```

**Notes**

- If `$ARGUMENTS` is empty, ask the user for a one-line feature description before invoking the skill.
- The skill owns the full pipeline (Stages 1–12): identify → worktree → spec → TDD tests → implement → review → commit → push → MR review loop → archive.
- User checkpoints are inside the skill (spec approval, pre-push). Don't add extra confirmations here.
- If the user mentions skipping (e.g. trivial UI tweak), follow the skill's `Skip rule` — don't override it from this command.
