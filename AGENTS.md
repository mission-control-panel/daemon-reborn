# Agent entrypoint

Trello is the authoritative source of truth for Daemon Reborn task tracking, status, dependencies, and acceptance evidence:

- **Trello board:** [Daemon Reborn](https://trello.com/b/gvDmOrM7/daemon-reborn) (`Backlog`, `Ready`, `In Progress`, `Blocked`, `In Review`, `Done`, `Canceled`)
- **Legacy references:** Historical `ORC-*` Linear IDs and GitHub issue links on migrated cards remain provenance references only; do not use Linear as an active project tracker.

This file and `README.md` are pointers and bootstrap instructions; do not add a separate repository TODO list or duplicate backlog here.

## Read before work

1. Open the [Daemon Reborn Trello board](https://trello.com/b/gvDmOrM7/daemon-reborn) and read the target card, its checklist/description, comments, acceptance criteria, and `blockedBy` references. Confirm every required predecessor is `Done` (or merged on `main` and verified) before starting.
2. Inspect the current `main` baseline, existing tests (`uv run pytest -q`, `uv run ruff check .`, `uv run mypy`), and relevant repository docs under `docs/`.
3. Work only from a scoped card/task with clear outcome, acceptance criteria, dependencies, checks, and security/privacy boundaries.

## Route and execute

- Before starting work on a card, move it to **In Progress** and post a **START** comment with intent, baseline branch/SHA, dependencies verified, plan, expected checks, and risks.
- Keep changes tightly scoped to the card. Never copy code, assets, secrets, or configuration from legacy Daemon.
- Do not silently make unapproved architecture, vendor, permission, licensing, or security/privacy changes; if a task is blocked on an external or owner prerequisite (e.g., character art approval, authorized reference audio WAV provenance, code signing certificate, clean-machine VM verification), move the card to **Blocked** and post a **BLOCKED** comment stating the exact unblock condition.
- Keep commits and pull requests small and issue/card-linked (`ORC-*` / card URL). Run the required checks and record exact commands, environment, exit codes, and any **NOT RUN** checks with reproducible next actions. Do not claim results from prior or partial runs.

## Review and handoff

- Before review, move the card to **In Review** and post a **REVIEW HANDOFF** comment containing the acceptance checklist, exact test/lint/typecheck results, commit/PR references and SHAs, limitations/NOT RUN checks, security/privacy/licensing notes, and rollback path.
- Move a card to **Done** only after acceptance criteria and merged code/evidence on `main` are verified; post a **CLOSEOUT** comment with the verified SHA.
- Keep all task tracking in Trello rather than leaving hidden TODOs in code or documentation.
