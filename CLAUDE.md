# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Docklet is a minimalist Docker clone written in Python for learning Linux container internals. It uses real kernel primitives (namespaces, cgroups v2, overlayfs) via ctypes with zero external dependencies (pure stdlib). See `SPEC.md` for the full technical specification.

## Build & Run

```bash
pip install -e .           # Install in dev mode
sudo docklet run alpine /bin/sh   # Run a container (requires root + CAP_SYS_ADMIN, CAP_NET_ADMIN)
```

## Architecture

The container startup path is: `cli.py` → `container.py` → fork → `namespaces.unshare()` → fork again (for PID ns) → `filesystem.setup_overlay()` + `pivot_root()` → `os.execvp()`. The parent side handles cgroup setup and veth networking between the two forks.

Key design decisions:
- **`os.fork()` + `unshare()`** over raw `clone()` — Python's GC/thread state doesn't survive clone
- **Double fork** — `unshare(CLONE_NEWPID)` only affects children, so a second fork makes the container PID 1
- **`subprocess.run(["ip", ...])`** for networking — netlink binary protocol isn't worth the complexity for educational code
- **`urllib.request`** for Docker Hub registry API — no requests dependency

## Constraints

- Must remain **zero-dependency** (stdlib only)
- Requires **Linux x86-64** — syscall numbers are architecture-specific
- Requires **root** with `CAP_SYS_ADMIN` and `CAP_NET_ADMIN` to actually run containers
- The current dev environment (unprivileged Docker container) cannot run containers — code must be tested on a privileged host

## Workflow Rules

- **Commit after every green module.** After a module passes tests + mypy + ruff, commit it immediately before starting the next module. Do not batch multiple modules into one commit. Each commit must compile and pass all tests independently.
- **One logical change per commit.** If the commit message needs "and", split it.
- **Commit message format:** `<type>: <what and why>` (types: feat, fix, refactor, test, chore, docs).

## DORA Skills Applied

This project uses DORA engineering skills throughout development:

| Skill | Application |
|---|---|
| **loose-coupling** | Modules (namespaces, cgroups, filesystem, network, registry, image) are independent; only `container.py` orchestrates them |
| **configuration-as-code** | All paths, syscall numbers, and tunables live in `config.py` — single source of truth |
| **type-safety-and-linting** | Type hints throughout, mypy/ruff configured |
| **test-driven-development** | Tests written before implementation for each module |
| **structured-logging-and-tracing** | Structured logging with container ID correlation across lifecycle operations |
| **observability-aware-coding** | Key operations (pull, start, exec, stop) instrumented with timing and status |
| **dependency-management** | Zero external dependencies enforced — stdlib only |
| **small-incremental-commits** | One commit per module, building bottom-up |
| **rollback-friendly-design** | Container teardown reverses setup steps; partial failures clean up already-created resources |
| **contract-testing** | Registry API responses validated against expected schemas |
| **feature-flags** | Runtime capability detection — graceful behavior when kernel features are unavailable |
