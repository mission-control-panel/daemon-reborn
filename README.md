# Daemon Reborn

Daemon Reborn is a clean-slate, privacy-first Windows desktop companion. Project tasks,
status, dependencies, and acceptance evidence are maintained on the [Daemon Reborn Trello board](https://trello.com/b/gvDmOrM7/daemon-reborn).

## Project direction

Trello is the source of truth for project planning and task tracking via the [Daemon Reborn board](https://trello.com/b/gvDmOrM7/daemon-reborn).
Historical `ORC-*` IDs and GitHub issue links inside migrated cards are preserved for provenance only.

Follow the root [AGENTS.md](AGENTS.md) before making changes. It is an entrypoint to Trello and repository standards, not a separate backlog.

This repository contains the implementation only. The legacy Daemon repository is reference-only;
no legacy code or assets are used here.

## Development setup

Install [uv](https://docs.astral.sh/uv/), then run:

```powershell
uv sync --locked
uv run python -m daemon_reborn --help
uv run pytest -q
uv run ruff check .
```

The project targets Python 3.12. `.python-version`, `requires-python`, and `uv.lock` pin the
interpreter line and resolved dependencies. PySide6 is a runtime dependency; tests and lint tools
are in the `dev` dependency group. Optional speech/model dependencies are intentionally not
installed by the base environment.

## Run the desktop shell

Start the minimal Windows shell from a development checkout:

```powershell
uv run python -m daemon_reborn
```

The shell shows a small placeholder character and a system-tray menu with Show pet, Hide pet, Settings, and Exit. Use Show/Hide pet to toggle the character, or Exit to shut down. Settings currently opens a placeholder notice. This shell does not start network, language-model, speech, or worker services and requires a Windows system tray.

## Current project scope

The `src/daemon_reborn` package establishes boundaries for app orchestration, standard-library-only
domain code, animation, assets, audio, Qt UI, voice, intelligence, memory and integrations. The CLI is a bootstrap
entrypoint for the current shell; further product behavior is implemented through the scoped Trello
cards.

PySide6 distribution and packaging obligations remain subject to the project's separate license
review before release.
