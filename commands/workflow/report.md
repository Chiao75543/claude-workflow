---
name: "workflow:report"
description: "Generate a spec-vs-implementation report (Requirement × Scenario coverage + issue list) and save as local .md or .html. Run after /workflow:verify or /workflow:review-mr."
category: Workflow
tags: [workflow, report, coverage]
---

Produce a coverage and findings report against the active spec.

**Input**: optional output format (`md` | `html`) and spec/change name in `$ARGUMENTS`. Defaults to `md` and the active spec.

**Action**

Invoke the `reporter` skill via the **Skill tool**:

```
Skill(skill="reporter", args="$ARGUMENTS")
```

**Notes**

- Prerequisite: a prior `/workflow:verify` or `/workflow:review-mr` run (the skill reads its findings as input).
- Supports OpenSpec (preferred) and legacy SDD format.
- Report contents: Requirement × Scenario coverage matrix, per-Scenario impl table, issue summary.
- Output is written to the repo root or a configurable path — the skill will print the file path on completion.
