---
name: "workflow:fix"
description: "Fix code review or GitLab MR review issues, re-verify against spec, and reply 'resolved' on each GitLab discussion."
category: Workflow
tags: [workflow, fix, review]
---

Resolve review comments (CRITICAL / WARNING) from a code review or GitLab MR.

**Input**: optional MR URL / IID, or path to a review report, in `$ARGUMENTS`. If empty, the skill locates the active MR or most recent review report.

**Action**

Invoke the `review-fixer` skill via the **Skill tool**:

```
Skill(skill="review-fixer", args="$ARGUMENTS")
```

**Notes**

- The skill fixes CRITICAL first, then WARNING. SUGGESTION items are surfaced but not auto-fixed.
- After fixing, it re-runs `/workflow:verify` automatically.
- For GitLab MR comments, it posts a "resolved" reply and marks each discussion resolved via the GitLab API.
