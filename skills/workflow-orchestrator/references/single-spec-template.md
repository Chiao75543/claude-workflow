# spec.md template (the file the user authors)

This is the **single source** that `spec-builder` shows to the user for review before splitting into the OpenSpec 4-file structure.

Keep each section short. Skip optional sections for trivial changes.

```markdown
# {Feature Name}

## Why
{1–3 lines: motivation, stakeholder, deadline if any.
   - "Why now?" — what triggered this work
   - "Who benefits?" — user / team / compliance
   - If responding to an audit or ticket, link it here.
}

## What
{1–3 lines: scope of change.
   - What changes from the user's perspective
   - What stays the same (explicit non-goals)
   - Key UI / API / module touched
}

## Impact
{Bullet list:
   - Files / modules affected (rough)
   - Other features that might regress
   - Dependencies (backend / SDK / library)
   - Risks (security, perf, data) — short
}

## Design
{Optional. Skip for trivial changes.
 Cover:
   - Architecture decisions (and rejected alternatives)
   - Domain model if new entities
   - Edge cases identified during brainstorm / grill
   - Risks elaborated
}

## Requirements
{Required. The contract. Nested: Requirement (goal) → Scenario (behaviour).
 Use OpenSpec convention: "App SHALL ..." in Requirement body, WHEN/THEN bullets in each Scenario.}

### Requirement: {goal name — what the app must do}
{1–3 lines describing the SHALL clause. Example:
"App SHALL ... 才能避免 ..."}

#### Scenario: {behaviour name — concrete situation}
- **WHEN** {trigger / precondition}
- **THEN** {expected outcome}
- **AND** {additional assertion if needed}

#### Scenario: {another behaviour}
- **WHEN** ...
- **THEN** ...

### Requirement: {another goal}
{...}

#### Scenario: ...

## Tasks
{Checkbox list. Group by phase that fits THIS work, not a fixed schema.}

{For Android UI feature, common phases:}
### Phase 1 — Domain
- [ ] {task}

### Phase 2 — Data
- [ ] {task}

### Phase 3 — Presentation
- [ ] {task}

### Phase 4 — Test
- [ ] {task}

{For backend / doc / config / build / refactor work, pick phases that match.
 Example for a backend integration:}
### Phase 1 — API contract
- [ ] {task}

### Phase 2 — Integration
- [ ] {task}

### Phase 3 — Migration / rollout
- [ ] {task}

{Example for a doc-only or config change:}
### Tasks
- [ ] {task}
- [ ] {task}
```

## Sizing guidance

| Change size | Total spec.md lines (rough) |
|---|---|
| Trivial (1-line fix, doc) | Don't use this skill |
| Small (single file edit) | 20–40 |
| Medium (single feature, ~5 files) | 50–100 |
| Large (epic, many files) | 100–200 — consider splitting into multiple changes |

If spec.md > 200 lines, the feature is too big for one OpenSpec change. Suggest decomposition.
