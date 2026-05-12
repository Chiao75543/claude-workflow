# claude-workflow

A portable, spec-driven development pipeline for AI-assisted coding. Designed for [Claude Code](https://claude.com/claude-code) + [Codex CLI](https://github.com/openai/codex), but tool-agnostic where possible.

This repo packages:

- The **workflow-orchestrator skill** — a 12-stage pipeline from ticket to archived spec, with mandatory verification gates and per-comment user checkpoints in PR review fixes.
- **Slash commands** — `/workflow` (full pipeline) plus 7 namespaced sub-commands (`/workflow:spec`, `/workflow:test`, `/workflow:implement`, `/workflow:verify`, `/workflow:fix`, `/workflow:review-mr`, `/workflow:report`) for invoking each stage individually.
- **AGENTS.md templates** — global Codex preferences + project-level rules that Codex needs (Codex does not load Claude Code skills).
- A **setup script** to install on a new machine.

For the full pipeline reference, read [`skills/workflow-orchestrator/PIPELINE.md`](skills/workflow-orchestrator/PIPELINE.md).

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
│   └── project-AGENTS.md.template # per-repo AGENTS.md (customize)
├── scripts/
│   └── setup.sh                  # install on new machine
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
| `/workflow:review-mr <MR>` | Review a GitLab MR with inline DiffNotes | `gitlab-mr-reviewer` |
| `/workflow:report` | Generate spec-vs-impl coverage report (.md/.html) | `reporter` |

Flags: `/workflow --fast` (1 combined reviewer per stage) / `/workflow --full` (2–3 parallel reviewers, default). To archive a completed change, use the existing `/opsx:archive`.

The `workflow:` namespace prefix avoids collisions with other plugins or skills that may register similarly named commands (`/test`, `/implement`, `/verify`, etc.).

---

## Per-project setup

For each repo you work in:

```bash
cp ~/code/claude-workflow/templates/project-AGENTS.md.template <repo>/AGENTS.md
# Edit AGENTS.md: substitute {Project}, {language}, {build_command}, etc.
git -C <repo> add AGENTS.md
git -C <repo> commit -m "chore: add Codex AGENTS.md aligned with workflow-orchestrator"
```

Why per-repo: Codex reads `<repo>/AGENTS.md` automatically. This is where long-lived project rules (test commands, architecture, Stage 7.5 / Stage 11 conventions) need to live.

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
├─ 7.5 Verify + Report ◄── tests + spec review + report (0 CRITICAL gate)
├─ 8. Commit ◄──────────── CRITICAL fix loop (2 agents)
├─ 9. ▮ User confirms push
├─ 10. Push + PR ───────── git push + create PR
├─ 11. PR review loop ◄── deferred; engine (codex/claude) + 2 user gates/comment
└─ 12. Archive ────────── post-merge, user-triggered, cleanup
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
3. Verification before commit — no commit until tests green + 0 CRITICAL.
4. Lifecycle ends at archive, not at push.
5. Per-comment user gate in PR review fixes — no batching.
6. Reviewer agents in parallel, never serial.
7. CRITICAL blocks; WARNING / SUGGESTION surfaces.

---

## Customization

The pipeline is tool-agnostic. Substitution points:

| Slot                | Default                                          | Examples                                                     |
| ------------------- | ------------------------------------------------ | ------------------------------------------------------------ |
| Spec system         | OpenSpec                                         | Custom markdown, RFC, ADR                                    |
| VCS host            | GitHub (`gh`) / GitLab (`glab`)                  | Bitbucket, Gitea, Forgejo                                    |
| Integration branch  | `main`                                           | `develop`, `release`                                         |
| Test command        | project-specific                                 | `npm test`, `pytest`, `./gradlew test`, `cargo test`         |
| Fix engine          | `codex:codex-rescue` agent                       | Any code-writing agent + fixer skill                         |
| Reviewer agents     | `code-reviewer`, `reporter`, etc.                | Custom per project                                           |
| Ticket tracker      | Linear / Jira / GitHub Issues                    | Any                                                          |

Edit the template at `templates/project-AGENTS.md.template`, swap commands at Stages 5/7.5/10/11/12.

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
