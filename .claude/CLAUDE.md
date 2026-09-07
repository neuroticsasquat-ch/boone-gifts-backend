# Boone Gifts Backend — Claude Code

Project documentation lives in [`AGENTS.md`](../AGENTS.md) — architecture, commands, conventions,
the visibility model, and production details. Read it first; this file holds only the settings that
are specific to Claude Code and the personal skills.

<!-- Specs/plans live under this repo's own docs/ (not the umbrella). This overrides the
     personal-skills DOCS_DIR auto-resolution so /planit, /implementit, /reviewit, and the loop
     resolve DOCS_DIR = <repo>/docs and find files in docs/superpowers/{specs,plans}. -->
specs_dir: docs

<!-- Linear targets for /projectit and /planit: which initiative and team new projects
     and tickets are filed under, and the repo label loop.py filters tickets on. -->
linear_initiative: Boone Gifts
linear_team: Neuroticsasquatch
linear_repo: boone-gifts-backend
