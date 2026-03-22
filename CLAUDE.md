# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Docklet is a minimalist Docker clone written in Python for learning Linux container internals. It uses real kernel primitives (namespaces, cgroups v2, overlayfs) via ctypes with zero external dependencies (pure stdlib). See `SPEC.md` for the full technical specification.

## Build & Test Commands

```bash
pip install -e .                        # Install in dev mode
python -m pytest tests/                 # Run all tests
python -m pytest tests/test_config.py   # Run a single test file
python -m pytest tests/ -k "test_name"  # Run a specific test by name
python -m mypy docklet/                 # Type check (strict mode enabled)
python -m ruff check .                  # Lint
python -m ruff check . --fix            # Lint with auto-fix
```

To run the actual container runtime (requires privileged host, not available in dev container):
```bash
sudo docklet run alpine /bin/sh
```

## Architecture

The container startup path is: `cli.py` → `container.py` → fork → `namespaces.unshare()` → fork again (for PID ns) → `filesystem.setup_overlay()` + `pivot_root()` → `os.execvp()`. The parent side handles cgroup setup and veth networking between the two forks.

Key design decisions:
- **`os.fork()` + `unshare()`** over raw `clone()` — Python's GC/thread state doesn't survive clone
- **Double fork** — `unshare(CLONE_NEWPID)` only affects children, so a second fork makes the container PID 1
- **`subprocess.run(["ip", ...])`** for networking — netlink binary protocol isn't worth the complexity for educational code
- **`urllib.request`** for Docker Hub registry API — no requests dependency

Modules are loosely coupled: `config.py`, `namespaces.py`, `cgroups.py`, `filesystem.py`, `network.py`, `registry.py`, and `image.py` are independent. Only `container.py` orchestrates them.

## Build Order

Modules are built bottom-up. Each phase must pass tests + mypy + ruff before proceeding.

| Phase | Modules | Root required? |
|-------|---------|----------------|
| 1 | config.py | No |
| 2 | registry.py, image.py | No |
| 3 | namespaces.py, cgroups.py, filesystem.py | To test |
| 4 | network.py | To test |
| 5 | container.py | To test |
| 6 | cli.py, pyproject.toml | No |

## Constraints

- Must remain **zero-dependency** (stdlib only)
- Requires **Linux x86-64** — syscall numbers are architecture-specific
- Requires **root** with `CAP_SYS_ADMIN` and `CAP_NET_ADMIN` to run containers
- The current dev environment (unprivileged Docker container) cannot run containers — unit tests must mock kernel interfaces

## Tool Configuration

- **mypy**: strict mode, Python 3.10 target, `disallow_untyped_defs`
- **ruff**: Python 3.10 target, line length 100, enables pycodestyle/pyflakes/isort/bugbear/pyupgrade/annotations/return/simplify
- **pytest**: test discovery in `tests/`

## Workflow Rules

- **Feature branches only.** Never commit directly to main. Create a short-lived branch (e.g., `feat/config-module`) before the first commit.
- **TDD.** Write the failing test before the implementation.
- **Commit after every green module.** After a module passes tests + mypy + ruff, commit immediately. Do not batch multiple modules into one commit.
- **One logical change per commit.** If the commit message needs "and", split it.
- **Commit message format:** `<type>: <what and why>` (types: feat, fix, refactor, test, chore, docs).
- **Push after every commit.** Do not accumulate local commits.
- **Run dora-review after each push.** Use the `dora-skills:dora-review` agent before moving to the next module.
- **Merge to main via PR** when the work is ready.

## DORA Skills

This project uses DORA engineering skills (available as `dora-skills:*`). Load each skill **at the moment it's relevant**, not all at once.

### Startup
- Load `dora-skills:dora-overview` at the start of any coding session to route to the right practices.
- Run `dora-skills:dora-health-check` agent for a baseline score before starting work.

### During development — load the skill that matches what you're about to do

| When you are... | Load this skill |
|---|---|
| Writing any new code | `dora-skills:test-driven-development` — failing test must exist first |
| Designing module boundaries or interfaces | `dora-skills:loose-coupling` |
| Adding paths, constants, env vars, or tunables | `dora-skills:configuration-as-code` |
| Writing type hints, fixing mypy/ruff errors | `dora-skills:type-safety-and-linting` |
| Adding logging, print, or debug output | `dora-skills:structured-logging-and-tracing` |
| Adding metrics, health checks, or timing | `dora-skills:observability-aware-coding` |
| Changing API endpoints or response shapes | `dora-skills:api-versioning` |
| Changing API schemas or service contracts | `dora-skills:contract-testing` |
| Writing database/schema migrations | `dora-skills:backward-compatible-migrations` |
| Adding packages or updating dependencies | `dora-skills:dependency-management` |
| Shipping a new feature or risky change | `dora-skills:feature-flags` |
| Writing deployment/teardown/cleanup logic | `dora-skills:rollback-friendly-design` |
| Creating a branch or merging | `dora-skills:trunk-based-development` |
| Staging or committing changes | `dora-skills:small-incremental-commits` |
| Creating or reviewing a PR | `dora-skills:small-pull-requests` |
| Reviewing code or self-reviewing before PR | `dora-skills:code-review-discipline` |
| Unsure about requirements or hitting ambiguity | `dora-skills:stop-and-clarify` |

### After completing work
- Run `dora-skills:dora-review` agent after each push to review changes.
- Run `dora-skills:dora-health-check` agent to compare against baseline.
- Run `dora-skills:dora-improve` agent if any metric scored low.
