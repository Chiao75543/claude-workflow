---
name: "workflow:test"
description: "Write Android unit tests from an approved spec (OpenSpec or SDD). Covers UseCase / Repository / ViewModel layers and reports Scenario coverage."
category: Workflow
tags: [workflow, test, tdd]
---

Generate unit tests against an existing spec.

**Input**: optional spec path or change name in `$ARGUMENTS`. If empty, the skill will locate the active spec from `openspec/changes/` or SDD.

**Action**

Invoke the `test-writer` skill via the **Skill tool**:

```
Skill(skill="test-writer", args="$ARGUMENTS")
```

**Notes**

- Prerequisite: a spec exists and is approved. If none, suggest running `/workflow:spec` first.
- The skill reads acceptance criteria (Scenarios) from the spec and reports coverage gaps.
- Tests must fail initially (red phase of TDD) before `/workflow:implement` makes them pass.
