---
name: "workflow:verify"
description: "Verify current implementation matches the spec. Produces CRITICAL / WARNING / SUGGESTION findings by comparing OpenSpec/SDD acceptance criteria against git diff."
category: Workflow
tags: [workflow, verify, code-review]
---

Run spec-vs-implementation verification.

**Input**: optional spec path, change name, or diff range in `$ARGUMENTS`. If empty, the skill uses the active spec and current `git diff`.

**Action**

Invoke the `code-reviewer` skill via the **Skill tool**:

```
Skill(skill="code-reviewer", args="$ARGUMENTS")
```

**Notes**

- Produces a tiered report: CRITICAL (spec violations — must fix), WARNING (concerns — should fix), SUGGESTION (nits — optional).
- Block on any CRITICAL before continuing to commit/push.
- After fixes, re-run `/workflow:verify` to confirm.
- Pair with `/workflow:report` to persist the verification result as a .md/.html file.
