---
name: "workflow:spec"
description: "Author a new spec only — brainstorm + grill + draft + OpenSpec auto-split. Stops at the spec checkpoint, does not implement or test."
category: Workflow
tags: [workflow, openspec, spec]
---

Run only the spec-authoring portion of the workflow pipeline.

**Input**: free-text feature description in `$ARGUMENTS`.

**Action**

Invoke the `workflow-orchestrator` skill via the **Skill tool** with these constraints:

```
Skill(
  skill="workflow-orchestrator",
  args="--spec-only $ARGUMENTS"
)
```

In the skill prompt, **stop after Stage 5 (spec approval checkpoint)**. Do NOT continue into TDD tests (Stage 6), implementation (Stage 7), or downstream stages. Surface the final `openspec/changes/{name}/spec.md` for review and end the turn.

**Notes**

- If `$ARGUMENTS` is empty, ask for a one-line feature description first.
- After the spec is approved, the user can resume with `/workflow:test` and `/workflow:implement` manually, or re-enter the full pipeline with `/workflow {description}`.
