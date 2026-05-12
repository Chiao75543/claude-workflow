---
name: "workflow:implement"
description: "Implement Android code from an approved spec, layer by layer: Domain → Data → DI → Presentation → Navigation."
category: Workflow
tags: [workflow, implement, android]
---

Implement code against an existing spec.

**Input**: optional spec path or change name in `$ARGUMENTS`. If empty, the skill locates the active spec.

**Action**

Invoke the `rd-implementer` skill via the **Skill tool**:

```
Skill(skill="rd-implementer", args="$ARGUMENTS")
```

**Notes**

- Prerequisite: spec is approved AND tests exist (run `/workflow:spec` and `/workflow:test` first if not).
- The skill enforces 5 phases: Domain → Data → DI → Presentation → Navigation. Don't skip.
- After implementation, run `/workflow:verify` to confirm code matches spec.
