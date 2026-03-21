"""cgroups v2 resource limits.

All operations are plain file reads/writes to the cgroup filesystem.
This demonstrates that cgroups are fundamentally just a filesystem interface.
"""

from __future__ import annotations

import os
import shutil

from docklet.config import CGROUP_ROOT
from docklet.log import get_logger

log = get_logger("cgroups")


def _write(path: str, value: str) -> None:
    """Write a value to a cgroup file."""
    with open(path, "w") as f:
        f.write(value)


def _read(path: str) -> str:
    """Read a cgroup file, returning stripped content."""
    with open(path) as f:
        return f.read().strip()


def init(cgroup_root: str = CGROUP_ROOT) -> None:
    """Create the docklet cgroup subtree and enable controllers."""
    os.makedirs(cgroup_root, exist_ok=True)
    # Enable controllers on the parent (may fail in test with fake fs)
    subtree_ctrl = os.path.join(cgroup_root, "cgroup.subtree_control")
    if os.path.exists(subtree_ctrl):
        _write(subtree_ctrl, "+cpu +memory +pids")
    log.info("cgroup root initialized", extra={"container_id": cgroup_root})


def create(container_id: str, cgroup_root: str = CGROUP_ROOT) -> None:
    """Create a cgroup for a container."""
    cg_dir = os.path.join(cgroup_root, container_id)
    os.makedirs(cg_dir, exist_ok=True)
    log.info("cgroup created", extra={"container_id": container_id})


def set_memory_limit(
    container_id: str, limit_bytes: int, cgroup_root: str = CGROUP_ROOT
) -> None:
    """Set memory limit by writing to memory.max."""
    path = os.path.join(cgroup_root, container_id, "memory.max")
    _write(path, str(limit_bytes))
    log.info(
        "memory limit set",
        extra={"container_id": container_id, "layer": f"{limit_bytes} bytes"},
    )


def set_cpu_limit(
    container_id: str,
    quota_us: int = 50000,
    period_us: int = 100000,
    cgroup_root: str = CGROUP_ROOT,
) -> None:
    """Set CPU limit by writing to cpu.max. Default = 50% of one core."""
    path = os.path.join(cgroup_root, container_id, "cpu.max")
    _write(path, f"{quota_us} {period_us}")
    log.info(
        "cpu limit set",
        extra={"container_id": container_id, "layer": f"{quota_us}/{period_us}"},
    )


def set_pids_limit(
    container_id: str, limit: int, cgroup_root: str = CGROUP_ROOT
) -> None:
    """Set max number of processes by writing to pids.max."""
    path = os.path.join(cgroup_root, container_id, "pids.max")
    _write(path, str(limit))
    log.info("pids limit set", extra={"container_id": container_id, "layer": str(limit)})


def add_process(
    container_id: str, pid: int, cgroup_root: str = CGROUP_ROOT
) -> None:
    """Add a process to the container's cgroup."""
    path = os.path.join(cgroup_root, container_id, "cgroup.procs")
    _write(path, str(pid))
    log.info("process added to cgroup", extra={"container_id": container_id})


def stats(
    container_id: str, cgroup_root: str = CGROUP_ROOT
) -> dict[str, int]:
    """Read cgroup stats for reporting."""
    cg_dir = os.path.join(cgroup_root, container_id)
    result: dict[str, int] = {}

    mem_path = os.path.join(cg_dir, "memory.current")
    if os.path.exists(mem_path):
        result["memory_current"] = int(_read(mem_path))

    cpu_path = os.path.join(cg_dir, "cpu.stat")
    if os.path.exists(cpu_path):
        for line in _read(cpu_path).splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[0] == "usage_usec":
                result["cpu_usage_usec"] = int(parts[1])

    return result


def cleanup(container_id: str, cgroup_root: str = CGROUP_ROOT) -> None:
    """Remove a container's cgroup directory."""
    cg_dir = os.path.join(cgroup_root, container_id)
    if os.path.isdir(cg_dir):
        shutil.rmtree(cg_dir)
        log.info("cgroup cleaned up", extra={"container_id": container_id})
