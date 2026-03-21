"""Tests for docklet.cgroups — cgroups v2 resource limits.

Uses a tmpdir to simulate the cgroup filesystem since writing
to /sys/fs/cgroup requires root.
"""

import os

from docklet.cgroups import (
    add_process,
    cleanup,
    create,
    init,
    set_cpu_limit,
    set_memory_limit,
    set_pids_limit,
    stats,
)


def test_init_creates_cgroup_dir(tmp_path: object) -> None:
    cgroup_root = str(tmp_path)
    init(cgroup_root=cgroup_root)
    assert os.path.isdir(cgroup_root)


def test_create_makes_container_cgroup(tmp_path: object) -> None:
    cgroup_root = str(tmp_path)
    init(cgroup_root=cgroup_root)
    create("abc123", cgroup_root=cgroup_root)
    assert os.path.isdir(os.path.join(cgroup_root, "abc123"))


def test_set_memory_limit_writes_file(tmp_path: object) -> None:
    cgroup_root = str(tmp_path)
    init(cgroup_root=cgroup_root)
    create("abc123", cgroup_root=cgroup_root)
    set_memory_limit("abc123", 512 * 1024 * 1024, cgroup_root=cgroup_root)
    mem_max = os.path.join(cgroup_root, "abc123", "memory.max")
    with open(mem_max) as f:
        assert f.read().strip() == str(512 * 1024 * 1024)


def test_set_cpu_limit_writes_file(tmp_path: object) -> None:
    cgroup_root = str(tmp_path)
    init(cgroup_root=cgroup_root)
    create("abc123", cgroup_root=cgroup_root)
    set_cpu_limit("abc123", quota_us=50000, period_us=100000, cgroup_root=cgroup_root)
    cpu_max = os.path.join(cgroup_root, "abc123", "cpu.max")
    with open(cpu_max) as f:
        assert f.read().strip() == "50000 100000"


def test_set_pids_limit_writes_file(tmp_path: object) -> None:
    cgroup_root = str(tmp_path)
    init(cgroup_root=cgroup_root)
    create("abc123", cgroup_root=cgroup_root)
    set_pids_limit("abc123", 100, cgroup_root=cgroup_root)
    pids_max = os.path.join(cgroup_root, "abc123", "pids.max")
    with open(pids_max) as f:
        assert f.read().strip() == "100"


def test_add_process_writes_pid(tmp_path: object) -> None:
    cgroup_root = str(tmp_path)
    init(cgroup_root=cgroup_root)
    create("abc123", cgroup_root=cgroup_root)
    add_process("abc123", 12345, cgroup_root=cgroup_root)
    procs = os.path.join(cgroup_root, "abc123", "cgroup.procs")
    with open(procs) as f:
        assert f.read().strip() == "12345"


def test_stats_reads_cgroup_files(tmp_path: object) -> None:
    cgroup_root = str(tmp_path)
    init(cgroup_root=cgroup_root)
    create("abc123", cgroup_root=cgroup_root)
    cg_dir = os.path.join(cgroup_root, "abc123")
    # Simulate kernel files
    with open(os.path.join(cg_dir, "memory.current"), "w") as f:
        f.write("1048576\n")
    with open(os.path.join(cg_dir, "cpu.stat"), "w") as f:
        f.write("usage_usec 500000\nuser_usec 400000\nsystem_usec 100000\n")
    result = stats("abc123", cgroup_root=cgroup_root)
    assert result["memory_current"] == 1048576
    assert result["cpu_usage_usec"] == 500000


def test_cleanup_removes_cgroup_dir(tmp_path: object) -> None:
    cgroup_root = str(tmp_path)
    init(cgroup_root=cgroup_root)
    create("abc123", cgroup_root=cgroup_root)
    cg_dir = os.path.join(cgroup_root, "abc123")
    assert os.path.isdir(cg_dir)
    cleanup("abc123", cgroup_root=cgroup_root)
    assert not os.path.isdir(cg_dir)
