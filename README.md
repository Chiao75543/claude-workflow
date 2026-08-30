# claude-workflow

A spec-driven development pipeline for AI-assisted coding. Designed for [Claude Code](https://claude.com/claude-code) + [Codex CLI](https://github.com/openai/codex).

**Architecture:** the orchestrator is **stack-agnostic** — it owns the pipeline structure, multi-reviewer dispatch, and verification gates, but delegates *how* to write tests / implement code / review MRs to **project-local skills** under each project's `<repo>/.claude/skills/`. Stack-specific skill bundles (Android and iOS shipped; add your own) live in `templates/skills/<stack>/` and scaffold into a project via `scripts/init-project.sh`.

This repo packages:

- The **workflow-orchestrator skill** — a 12-stage pipeline from ticket to archived spec, with mandatory verification gates and per-comment user checkpoints in PR review fixes. Stack-agnostic; references project-local skills by convention name (see *Project bindings* in `SKILL.md`).
- **Slash commands** — `/workflow` (full pipeline) plus 7 namespaced sub-commands (`/workflow:spec`, `/workflow:test`, `/workflow:implement`, `/workflow:verify`, `/workflow:fix`, `/workflow:review-mr`, `/workflow:report`) for invoking each stage individually.
- **Stack-specific skill templates** — `templates/skills/android/` ships a working Android Clean Architecture skill set and `templates/skills/ios/` its iOS (SwiftUI + SPM) counterpart, each with the same 6 pipeline skills (test-writer, rd-implementer, code-reviewer, reporter, mr-reviewer, review-fixer); other stacks add their own folder.
- **`init-project.sh`** — scaffolds a stack's skill set into a target repo's `.claude/skills/`, auto-substituting `{PROJECT_ROOT}` and listing remaining placeholders.
- **AGENTS.md templates** — global Codex preferences + project-level rules that Codex needs (Codex does not load Claude Code skills).
- A **setup script** to install on a new machine.

For the full pipeline reference, read [`skills/workflow-orchestrator/PIPELINE.md`](skills/workflow-orchestrator/PIPELINE.md) — the published mirror of `SKILL.md`, which is canonical.

---

## What's in here

```
claude-workflow/
├── skills/
│   └── workflow-orchestrator/
│       ├── SKILL.md              # the skill itself (Claude Code reads this)
│       ├── PIPELINE.md           # standalone pipeline reference (GitHub-friendly)
│       └── references/
│           ├── single-spec-template.md
│           ├── file-mapping.md
│           ├── reviewer-prompts.md
│           └── codex-prompt-template.md
├── commands/
│   ├── workflow.md               # /workflow — full end-to-end pipeline
│   └── workflow/                 # /workflow:* — per-stage entry points
│       ├── spec.md               # /workflow:spec
│       ├── test.md               # /workflow:test
│       ├── implement.md          # /workflow:implement
│       ├── verify.md             # /workflow:verify
│       ├── fix.md                # /workflow:fix
│       ├── review-mr.md          # /workflow:review-mr
│       └── report.md             # /workflow:report
├── templates/
│   ├── codex-AGENTS.md           # global ~/.codex/AGENTS.md
│   ├── project-AGENTS.md.template # per-repo AGENTS.md (customize)
│   └── skills/                   # stack-specific skill bundles
│       ├── android/              # Android Clean Architecture defaults
│       │   ├── test-writer/SKILL.md
│       │   ├── rd-implementer/SKILL.md
│       │   ├── code-reviewer/SKILL.md
│       │   ├── reporter/SKILL.md
│       │   ├── mr-reviewer/SKILL.md
│       │   └── review-fixer/SKILL.md
│       └── ios/                  # iOS SwiftUI + SPM defaults (same 6 skills)
├── scripts/
│   ├── setup.sh                  # install on new machine (per-user)
│   └── init-project.sh           # scaffold skill bundle into a target repo
└── README.md
```

---

## Quick install (new machine)

```bash
# 1. Tool deps
brew install --cask claude
brew install glab gh
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh | bash
nvm install --lts
npm install -g @openai/codex openspec

# 2. Auth
claude login
codex login
glab auth login
gh auth login

# 3. Clone and install this repo
git clone https://github.com/<you>/claude-workflow.git ~/code/claude-workflow
~/code/claude-workflow/scripts/setup.sh
```

`setup.sh` will:

- Check tool dependencies.
- Symlink `skills/workflow-orchestrator/` into `~/.claude/skills/`.
- Symlink `commands/workflow.md` and `commands/workflow/` into `~/.claude/commands/` (enables `/workflow` and `/workflow:*` slash commands).
- Optionally copy `templates/codex-AGENTS.md` to `~/.codex/AGENTS.md`.
- Print next steps for project-level setup.

---

## Slash commands

Once installed, the following slash commands are available in Claude Code:

| Command | Purpose | Underlying skill |
| --- | --- | --- |
| `/workflow <feature>` | Full end-to-end pipeline (default entry point) | `workflow-orchestrator` |
| `/workflow:spec <feature>` | Author a new spec only (stops at spec checkpoint) | `workflow-orchestrator` (spec stages 3–5) |
| `/workflow:test` | Write TDD tests from approved spec | `test-writer` |
| `/workflow:implement` | Implement code from approved spec | `rd-implementer` |
| `/workflow:verify` | Verify implementation against spec | `code-reviewer` |
| `/workflow:fix` | Fix review / MR comments and reply resolved | `review-fixer` |
| `/workflow:review-mr <MR/PR>` | Review the project's MR/PR with inline comments | `mr-reviewer` (Android default: glab + DiffNote) |
| `/workflow:report` | Generate spec-vs-impl coverage report (.md/.html) | `reporter` |

Flags: `/workflow --fast` (1 combined reviewer per stage) / `/workflow --full` (2–3 parallel reviewers, default). Archive (Stage 12) is a pre-merge commit added on the feature branch after reviewer approval + user OK-to-merge (`openspec archive {name} --yes`; `scripts/archive.sh` is a standalone fallback) — feature + archive merge together in one MR.

The `workflow:` namespace prefix avoids collisions with other plugins or skills that may register similarly named commands (`/test`, `/implement`, `/verify`, etc.).

---

## Per-project setup

For each repo you work in:

```bash
# 1. AGENTS.md — long-lived project rules read by Codex AND by workflow-orchestrator
cp ~/code/claude-workflow/templates/project-AGENTS.md.template <repo>/AGENTS.md
# Edit AGENTS.md: substitute {Project}, {language}, {build_command}, etc.

# 2. Scaffold the stack's skill bundle into <repo>/.claude/skills/
#    (auto-loaded by Claude Code as project-local skills when working in <repo>)
~/code/claude-workflow/scripts/init-project.sh android <repo>
# init-project.sh auto-substitutes {PROJECT_ROOT}; it prints remaining
# placeholders ({PACKAGE_NAME}, {TEST_COMMAND}, etc.) you must edit by hand
# inside the scaffolded files.

# 3. Commit
git -C <repo> add AGENTS.md .claude/skills/
git -C <repo> commit -m "chore: add Codex AGENTS.md and workflow skill bindings"
```

Why per-repo:

- **AGENTS.md** is read automatically by Codex AND referenced by workflow-orchestrator for project-specific bindings (`{TEST_COMMAND}`, `{BUILD_COMMAND}`, `{LAYERING_CONVENTION}`, etc.).
- **`.claude/skills/`** holds the concrete `test-writer` / `rd-implementer` / `code-reviewer` / etc. skills that the orchestrator invokes. Tuning these per project is how the pipeline adapts to each codebase's conventions.

Adding a new stack: copy an existing stack folder (`templates/skills/android/` or `templates/skills/ios/`) to `templates/skills/<your-stack>/`, edit the SKILL.md contents to your stack's idioms, then `init-project.sh <your-stack> <repo>`.

---

## Project memory (separate, usually private)

Claude Code's per-project memory lives at `~/.claude/projects/-Users-<username>-<project>/memory/`. It contains:

- Active tickets and their state
- Confirmed product decisions (avoid re-litigating)
- External audit context
- Workflow preferences

**Keep this in a separate private repo**, not in `claude-workflow`. Reason:

- Memory typically contains internal ticket IDs, hostnames, audit info, sometimes keystore fingerprints.
- `claude-workflow` should be safe to share (this repo).

Recommended layout:

```bash
# Project memory in its own private repo
git clone <your-private-memory-repo> \
  ~/.claude/projects/-Users-$(whoami)-<project>/memory
```

When migrating to a new machine, the new path may differ (username changes). The setup script prints a reminder.

---

## The pipeline at a glance

```
┌─ 1. Identify ──────────── ticket + capability + {name}
├─ 2. Worktree ──────────── .worktrees/{name} (mandatory for new specs)
├─ 3. Spec author ──────── inline brainstorm + grill + spec.md
├─ 4. ▮ User approves spec ◄────┐ refine loop
├─ 5. Split + validate ──── spec.md → 5 derived files
├─ 6. Tests (RED) ◄──────── CRITICAL fix loop (3/2/0 agents)
├─ 7. Implement (GREEN) ◄── CRITICAL fix loop (3 agents)
├─ 7.5 Verify + Report ◄── lint gate + tests + spec review + report (0 CRITICAL gate)
├─ 8. Commit ◄──────────── CRITICAL fix loop (2 agents)
├─ 9. ▮ User confirms push
├─ 10. Push + PR ───────── git push + create PR
├─ 10.5 Codex review ───── advisory pass on the MR (dispatcher relay-posts findings)
├─ 11. PR review loop ◄── deferred; engine (codex/claude) + 2 user gates/comment
└─ 12. Archive ────────── pre-merge commit on feature branch → final CI → user merges
```

See [`PIPELINE.md`](skills/workflow-orchestrator/PIPELINE.md) for the full reference, including:

- Stage detail tables
- Mermaid flowcharts (main flow + Stage 11 per-comment loop)
- Stage 7.5 vs Stage 11 contrast
- Reviewer dispatch pattern
- Customization slots
- Common mistakes

---

## Core principles

1. Every change traces to a spec.
2. Single source of truth — authors edit one file, the rest are projections.
3. Verification before commit — no commit until tests green + 0 CRITICAL (user-adjudicated `rejected`/`deferred` findings excepted).
4. Lifecycle ends at archive, not at push.
5. Per-comment user gate in PR review fixes — no batching.
6. Reviewer agents in parallel, never serial.
7. CRITICAL blocks; WARNING / SUGGESTION surfaces.
8. Convergence boundary — tools before tests before AI review; CRITICAL reserved for code/test/behavior correctness + security baseline; review loops capped (initial + 2 re-dispatch rounds).

---

## Customization

workflow-orchestrator is **stack-agnostic**. Two layers of customization:

**Layer 1 — `<repo>/AGENTS.md` placeholders** (light, edit anytime):

| Placeholder | Used in orchestrator at | Examples |
| --- | --- | --- |
| `{TEST_COMMAND}` | Stage 7.5 test gate | `./gradlew test`, `npm test`, `pytest`, `cargo test` |
| `{LINT_COMMAND}` | Stage 7.5 lint gate (no-op if none; AGENTS.md template spells it `{lint_command}` — same binding) | `./gradlew lint`, `npm run lint`, `ruff check`, SwiftLint |
| `{BUILD_COMMAND}` | (project-skill discretion) | `./gradlew assembleDebug`, `npm run build` |
| `{LAYERING_CONVENTION}` | Stage 7 implementation | Domain→Data→DI→Presentation→Navigation (Android Clean Arch); MVC; Hexagonal; … |
| `{INTEGRATION_BRANCH}` | Stage 2 worktree base + Stage 10 push target | `main`, `develop`, `release` |
| `{TICKET_PREFIX}` | Stage 1 ticket id | `AIP` (Linear), `JIRA`, `GH` |

**Layer 2 — `<repo>/.claude/skills/<name>/SKILL.md` content** (heavy, scaffold once):

The orchestrator invokes `test-writer`, `rd-implementer`, `code-reviewer`, `reporter`, `mr-reviewer`, `review-fixer` by convention name. Project-local versions live at `<repo>/.claude/skills/<name>/` and are auto-loaded by Claude Code. Scaffold via `init-project.sh <stack> <repo>`. The `mr-reviewer` convention is VCS-host-neutral; each stack's template picks its own implementation (Android default uses GitLab/`glab`; a GitHub-based stack could use `gh` + PR review API).

Other configurable slots:

| Slot | Default | Substitution |
| --- | --- | --- |
| Spec system | OpenSpec | Custom markdown, RFC, ADR |
| VCS host | GitHub (`gh`) / GitLab (`glab`) | Bitbucket, Gitea, Forgejo |
| Fix engine | `codex:codex-rescue` agent | Any code-writing agent + fixer skill |
| Ticket tracker | Linear / Jira / GitHub Issues | Any |

---

## Maintenance

If you change the skill or commands on one machine, push to this repo so other machines pick it up:

```bash
cd ~/code/claude-workflow
git add skills/workflow-orchestrator/ commands/
git commit -m "..."
git push
```

Other machines:

```bash
cd ~/code/claude-workflow && git pull
# symlink already points here; no further action needed
```

---

## License

Adapt as you like. Suggested: MIT for shareable copies; remove license if keeping private.
