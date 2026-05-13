# AGENTS.md

Tuno is a Python project for a terminal-based UNO game.

## References

Must read before doing anything:
- `agent_docs/omx.md`: oh-my-codex, a coordination layer for Codex

Optional:
- `agent_docs/cloudflare.md`: Cloudflare Workers
- `docs/DEVELOP.md`: Full development guide

## Entry points

- `src/tuno/client/__main__.py`: Client CLI
- `src/tuno/server/standalone.py`: Server
- `src/tuno/server/worker.py`: Serverless Python Worker for Cloudflare deployment
- `src/tests`: Unit tests, organized by module

## Run

Always use the conda environment `tuno` for development.

Commonly used commands:

```bash
python -m tuno.client # Start the client CLI
python -m tuno.client --server <server> # Start the client CLI with a preconfigured server, so you do not need to enter it in the TUI
python -m tuno.server --host 127.0.0.1 --port 8765 # Start the server with a specific host and port
```

Read `docs/DEVELOP.md` when you need commands for building, installing, or Worker development.

## Tests

```bash
python -m unittest discover -s tests -v # Run all unit tests
python -m ruff check . # Run lint checks
python -m ruff format --check . # Check formatting
```

## Code conventions

- Update the unit tests under `tests` after making functional changes.
- **DO NOT add unit tests for rendering-only or UI-only behavior**, such as height, bold text, or markup. Only add tests for functional behavior. Note that important displayed info, such as core game info, status, commands, and update notes, is considered functional behavior.
- After functional code changes (not documentation or UI-only changes), run the tests, lint checks, and formatting checks. Fix all errors and warnings.
- Favor simple, maintainable solutions. Keep functions small and focused.
- Add comments in English for important functions or code blocks.
