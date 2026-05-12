# spec.md → OpenSpec 5 files mapping

The user authored `openspec/changes/{name}/spec.md` (single source). The skill writes **5 derived files** in the **same folder**. The source `spec.md` is **kept** — it stays editable and authoritative. The 5 derived files are projections, rebuilt whenever `spec.md` changes.

## File 1: `.openspec.yaml` (metadata)

```yaml
schema: spec-driven
created: {YYYY-MM-DD}
```

That's it. No `name` or `status` field — those are derived from the directory name and tracked elsewhere.

## File 2: `proposal.md`

Sourced from `## Why`, `## What`, `## Impact` of spec.md.

```markdown
# Proposal: {Feature Name}

## Why
{copy of Why section}

## What
{copy of What section}

## Impact
{copy of Impact section}
```

## File 3: `design.md`

Sourced from `## Design` of spec.md.

If spec.md has no `## Design` section (skipped for trivial change), write:

```markdown
# Design: {Feature Name}

## Decisions
This change is small enough that the design is captured directly in the spec scenarios.
See `specs/{name}/spec.md`.
```

Otherwise:

```markdown
# Design: {Feature Name}

{copy of Design section, preserving sub-headings if any}
```

## File 4: `specs/{name}/spec.md`

Sourced from `## Requirements` of spec.md.

Path: `openspec/changes/{name}/specs/{name}/spec.md`

The single-source already uses OpenSpec nested structure (Requirement → Scenario). The split step adds the right top-level prefix and strips the outer `## Requirements` heading.

Choose the prefix based on step 6 of the skill (decide ADDED vs MODIFIED):

| Change kind | Prefix |
|---|---|
| New capability (no existing `openspec/specs/{name}/`) | `## ADDED Requirements` |
| Adds requirements to an existing capability | `## ADDED Requirements` |
| Modifies an existing requirement's body or scenarios | `## MODIFIED Requirements` |
| Removes a requirement | `## REMOVED Requirements` |

Source spec.md:
```markdown
## Requirements
### Requirement: 目標 X
App SHALL ...

#### Scenario: 行為 Y
- **WHEN** ...
- **THEN** ...
```

Destination `specs/{name}/spec.md`:
```markdown
## ADDED Requirements

### Requirement: 目標 X
App SHALL ...

#### Scenario: 行為 Y
- **WHEN** ...
- **THEN** ...
```

Preserve all `### Requirement:` and `#### Scenario:` levels verbatim.

## File 5: `tasks.md`

Sourced from `## Tasks` of spec.md. Direct copy, preserving checkbox state and phase headings (whatever the user chose):

```markdown
# Tasks: {Feature Name}

{copy of Tasks section verbatim}
```

## After all 5 files written

1. Keep `openspec/changes/{name}/spec.md` — do NOT delete. It is the single source of truth.
2. Run validation: `openspec validate {name}`

If validation fails:
- "Missing required field" → check `.openspec.yaml` has `schema` and `created`
- "Path mismatch" → ensure `specs/{name}/spec.md` is nested correctly
- "No requirements found" → check the `## ADDED Requirements` prefix is present

## Idempotency

This check belongs in **step 2 of the skill**, not here. If `openspec/changes/{name}/` already exists, do not proceed past step 2 — ask the user to overwrite, rename, or abort.
