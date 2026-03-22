"""Cgroups v2 resource limits via plain file reads/writes.

All operations target /sys/fs/cgroup/docklet/ (configurable via docklet.config.CGROUP_ROOT).
No external dependencies — just mkdir and file I/O on the cgroup filesystem.
"""

from docklet.config import CGROUP_ROOT


def init() -> None:
    """Create the docklet cgroup root and enable cpu, memory, pids controllers."""
    CGROUP_ROOT.mkdir(parents=True, exist_ok=True)
    subtree_control = CGROUP_ROOT / "cgroup.subtree_control"
    with open(subtree_control, "w") as f:
        f.write("+cpu +memory +pids")


def create(container_id: str) -> None:
    """Create a per-container cgroup directory."""
    container_dir = CGROUP_ROOT / container_id
    container_dir.mkdir(parents=True, exist_ok=True)


def set_memory_limit(container_id: str, limit_bytes: int) -> None:
    """Write the memory limit to memory.max."""
    memory_max = CGROUP_ROOT / container_id / "memory.max"
    with open(memory_max, "w") as f:
        f.write(str(limit_bytes))


def set_cpu_limit(
    container_id: str,
    quota_us: int = 50000,
    period_us: int = 100000,
) -> None:
    """Write cpu quota and period to cpu.max."""
    cpu_max = CGROUP_ROOT / container_id / "cpu.max"
    with open(cpu_max, "w") as f:
        f.write(f"{quota_us} {period_us}")


def set_pids_limit(container_id: str, limit: int) -> None:
    """Write the pids limit to pids.max."""
    pids_max = CGROUP_ROOT / container_id / "pids.max"
    with open(pids_max, "w") as f:
        f.write(str(limit))


def add_process(container_id: str, pid: int) -> None:
    """Write a PID to cgroup.procs to add it to the container's cgroup."""
    cgroup_procs = CGROUP_ROOT / container_id / "cgroup.procs"
    with open(cgroup_procs, "w") as f:
        f.write(str(pid))


def stats(container_id: str) -> dict[str, str]:
    """Read memory.current and cpu.stat for reporting."""
    container_dir = CGROUP_ROOT / container_id
    with open(container_dir / "memory.current") as f:
        memory_current = f.read().strip()
    with open(container_dir / "cpu.stat") as f:
        cpu_stat = f.read().strip()
    return {
        "memory_current": memory_current,
        "cpu_stat": cpu_stat,
    }


def cleanup(container_id: str) -> None:
    """Remove the container's cgroup directory."""
    container_dir = CGROUP_ROOT / container_id
    container_dir.rmdir()
