"""Tests for docklet.config — paths, constants, and syscall numbers."""

from pathlib import Path


def test_docklet_root_is_var_lib_docklet() -> None:
    from docklet.config import DOCKLET_ROOT

    assert Path("/var/lib/docklet") == DOCKLET_ROOT


def test_containers_dir_under_root() -> None:
    from docklet.config import CONTAINERS_DIR, DOCKLET_ROOT

    assert CONTAINERS_DIR == DOCKLET_ROOT / "containers"


def test_images_dir_under_root() -> None:
    from docklet.config import DOCKLET_ROOT, IMAGES_DIR

    assert IMAGES_DIR == DOCKLET_ROOT / "images"


def test_layers_dir_under_root() -> None:
    from docklet.config import DOCKLET_ROOT, LAYERS_DIR

    assert LAYERS_DIR == DOCKLET_ROOT / "layers"


def test_cgroup_root() -> None:
    from docklet.config import CGROUP_ROOT

    assert Path("/sys/fs/cgroup/docklet") == CGROUP_ROOT


def test_network_constants() -> None:
    from docklet.config import BRIDGE_IP, NETWORK_BRIDGE, SUBNET

    assert NETWORK_BRIDGE == "docklet0"
    assert SUBNET == "10.0.100.0/24"
    assert BRIDGE_IP == "10.0.100.1"


def test_syscall_numbers() -> None:
    from docklet.config import SYS_MOUNT, SYS_PIVOT_ROOT, SYS_SETNS, SYS_UMOUNT2, SYS_UNSHARE

    assert SYS_PIVOT_ROOT == 155
    assert SYS_MOUNT == 165
    assert SYS_UMOUNT2 == 166
    assert SYS_UNSHARE == 272
    assert SYS_SETNS == 308


def test_namespace_clone_flags() -> None:
    from docklet.config import (
        CLONE_NEWIPC,
        CLONE_NEWNET,
        CLONE_NEWNS,
        CLONE_NEWPID,
        CLONE_NEWUSER,
        CLONE_NEWUTS,
    )

    assert CLONE_NEWNS == 0x00020000
    assert CLONE_NEWUTS == 0x04000000
    assert CLONE_NEWIPC == 0x08000000
    assert CLONE_NEWUSER == 0x10000000
    assert CLONE_NEWPID == 0x20000000
    assert CLONE_NEWNET == 0x40000000
