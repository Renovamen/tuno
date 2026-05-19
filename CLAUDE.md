# CLAUDE.md

Tuno is a Python project for a terminal-based UNO game.

## References

- `agent_docs/cloudflare.md`: Cloudflare Workers
- `docs/DEVELOP.md`: Full development guide
- `docs/DESIGN.md`: Project design and architecture

## Entry points

- `src/tuno/client/__main__.py`: Client CLI
- `src/tuno/server/standalone.py`: Server
- `src/tuno/server/worker.py`: Serverless Python Worker for Cloudflare deployment
- `src/tests`: Unit tests, organized by module

## Setup

Always use the project-local `uv` environment for development. When the environment needs to be updated from `pyproject.toml`, sync the required extras:

```bash
uv sync --extra dev # Add --extra worker or --extra build when needed
```

## Run

Run commands through `uv run`. Common commands:

```bash
uv run python -m tuno.client # Start the client CLI
uv run python -m tuno.client --server <server> # Start the client CLI with a preconfigured server, so you do not need to enter it in the TUI

uv run python -m tuno.server --host 127.0.0.1 --port 8765 # Start the server with a specific host and port
uv run pywrangler dev # Start the Cloudflare Worker
```

Read `docs/DEVELOP.md` when you need commands for building, installing, or deploying the Worker.

## Tests

```bash
uv run python -m unittest discover -s tests -v # Run all unit tests
uv run python -m ruff check . # Run lint checks
uv run python -m ruff format --check . # Check formatting
```

## Code conventions

- Update unit tests under `tests` whenever a functional change affects behavior.
- Do not add tests for rendering-only details such as height, bold text, or markup. Do test displayed information that affects gameplay or user flow, including core game info, status, commands, and update notes.
- Keep tests focused on public behavior: core logic, user-visible flows, and meaningful edge cases. Avoid tests for private helpers, implementation details, or refactor-only seams unless the helper is a stable public contract.
- After functional code changes (not documentation or UI-only changes), run the tests, lint checks, and formatting checks. Fix all errors and warnings.
- Keep every function focused and under 50 lines. If it exceeds this, split it.
- Use English docstrings for important functions and English comments for non-obvious code blocks, especially to explain hidden constraints, workarounds, or subtle invariants. Do not add comments that merely restate clear names or self-explanatory code.
- Do not preserve backward compatibility unless the user explicitly asks for it.
