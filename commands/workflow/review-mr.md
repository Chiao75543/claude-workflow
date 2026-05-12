---
name: "workflow:review-mr"
description: "Review a GitLab Merge Request. Posts DiffNote inline comments via glab + curl and a summary report with a 0–100 score."
category: Workflow
tags: [workflow, gitlab, mr-review]
---

Review a GitLab MR as a senior code reviewer.

**Input**: MR URL, IID, or `<project> !<iid>` in `$ARGUMENTS`. Required.

**Action**

Invoke the `gitlab-mr-reviewer` skill via the **Skill tool**:

```
Skill(skill="gitlab-mr-reviewer", args="$ARGUMENTS")
```

**Notes**

- If `$ARGUMENTS` is empty, ask the user for the MR URL/IID before invoking.
- Review dimensions: Clean Architecture, Null Safety, Compose patterns, test coverage.
- Output: inline DiffNote comments on GitLab + summary report with 0–100 score.
- After review, the MR author can run `/workflow:fix` to address comments.
