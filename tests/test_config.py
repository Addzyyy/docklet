"""Tests for docklet.config — paths, constants, and syscall numbers."""

from docklet.config import (
    BRIDGE_IP,
    CGROUP_ROOT,
    CLONE_NEWIPC,
    CLONE_NEWNET,
    CLONE_NEWNS,
    CLONE_NEWPID,
    CLONE_NEWUSER,
    CLONE_NEWUTS,
    CONTAINERS_DIR,
    DOCKLET_ROOT,
    IMAGES_DIR,
    LAYERS_DIR,
    MNT_DETACH,
    MS_NODEV,
    MS_NOEXEC,
    MS_NOSUID,
    MS_PRIVATE,
    MS_REC,
    NETWORK_BRIDGE,
    SUBNET,
    SYS_mount,
    SYS_pivot_root,
    SYS_umount2,
    ensure_dirs,
)


def test_paths_are_under_docklet_root() -> None:
    assert CONTAINERS_DIR.startswith(DOCKLET_ROOT)
    assert IMAGES_DIR.startswith(DOCKLET_ROOT)
    assert LAYERS_DIR.startswith(DOCKLET_ROOT)


def test_cgroup_root_under_sys_fs() -> None:
    assert CGROUP_ROOT.startswith("/sys/fs/cgroup/")


def test_namespace_flags_are_distinct_bits() -> None:
    flags = [CLONE_NEWNS, CLONE_NEWUTS, CLONE_NEWIPC, CLONE_NEWUSER, CLONE_NEWPID, CLONE_NEWNET]
    # Each flag should be a power of 2 (single bit set)
    for flag in flags:
        assert flag > 0
        assert flag & (flag - 1) == 0, f"{flag:#x} is not a single bit"
    # All flags should be distinct
    assert len(set(flags)) == len(flags)


def test_syscall_numbers_are_positive_integers() -> None:
    for num in [SYS_pivot_root, SYS_mount, SYS_umount2]:
        assert isinstance(num, int)
        assert num > 0


def test_mount_flags_defined() -> None:
    assert MS_NOSUID > 0
    assert MS_NODEV > 0
    assert MS_NOEXEC > 0
    assert MS_PRIVATE > 0
    assert MS_REC > 0
    assert MNT_DETACH > 0


def test_network_constants() -> None:
    assert NETWORK_BRIDGE == "docklet0"
    assert BRIDGE_IP == "10.0.100.1"
    assert "10.0.100" in SUBNET


def test_ensure_dirs_creates_directories(tmp_path: "object") -> None:
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        import docklet.config as cfg
        original = cfg.DOCKLET_ROOT
        cfg.DOCKLET_ROOT = d
        cfg.CONTAINERS_DIR = f"{d}/containers"
        cfg.IMAGES_DIR = f"{d}/images"
        cfg.LAYERS_DIR = f"{d}/layers"
        try:
            ensure_dirs()
            import os
            assert os.path.isdir(f"{d}/containers")
            assert os.path.isdir(f"{d}/images")
            assert os.path.isdir(f"{d}/layers")
        finally:
            cfg.DOCKLET_ROOT = original
            cfg.CONTAINERS_DIR = f"{original}/containers"
            cfg.IMAGES_DIR = f"{original}/images"
            cfg.LAYERS_DIR = f"{original}/layers"
