---
name: "workflow:review-mr"
description: "Review the project's Merge / Pull Request. Posts inline review comments via the VCS CLI and a summary report with a 0–100 score. Implementation is stack/host-specific (e.g. the Android template uses glab + DiffNote API)."
category: Workflow
tags: [workflow, mr-review, code-review]
---

Review a Merge / Pull Request on the project's VCS host as a senior code reviewer.

**Input**: MR/PR URL, IID/number, or `<project> !<iid>` (GitLab) / `<owner>/<repo>#<n>` (GitHub) in `$ARGUMENTS`. Required.

**Action**

Invoke the project-local `mr-reviewer` skill via the **Skill tool**:

```
Skill(skill="mr-reviewer", args="$ARGUMENTS")
```

The skill at `<repo>/.claude/skills/mr-reviewer/SKILL.md` knows the project's VCS host, review dimensions, and posting protocol.

**Notes**

- If `$ARGUMENTS` is empty, ask the user for the MR/PR URL or ID before invoking.
- The Android template's `mr-reviewer` uses `glab` + GitLab DiffNote API. Other stacks may use `gh` + GitHub PR review API or equivalent.
- Output: inline review comments on the host + summary report with 0–100 score (skill defines the rubric).
- After review, the MR/PR author can run `/workflow:fix` to address comments.
