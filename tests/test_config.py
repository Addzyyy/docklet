"""Tests for docklet.config — paths, constants, and syscall numbers."""

import importlib
from pathlib import Path
from unittest.mock import patch

import docklet.config as config_module
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
    NETWORK_BRIDGE,
    SUBNET,
    SYS_MOUNT,
    SYS_PIVOT_ROOT,
    SYS_SETNS,
    SYS_UMOUNT2,
    SYS_UNSHARE,
)


class TestPaths:
    def test_docklet_root(self) -> None:
        assert Path("/var/lib/docklet") == DOCKLET_ROOT

    def test_containers_dir_under_root(self) -> None:
        assert CONTAINERS_DIR == DOCKLET_ROOT / "containers"

    def test_images_dir_under_root(self) -> None:
        assert IMAGES_DIR == DOCKLET_ROOT / "images"

    def test_layers_dir_under_root(self) -> None:
        assert LAYERS_DIR == DOCKLET_ROOT / "layers"

    def test_cgroup_root(self) -> None:
        assert Path("/sys/fs/cgroup/docklet") == CGROUP_ROOT


class TestNetworking:
    def test_bridge_name(self) -> None:
        assert NETWORK_BRIDGE == "docklet0"

    def test_subnet(self) -> None:
        assert SUBNET == "10.0.100.0/24"

    def test_bridge_ip(self) -> None:
        assert BRIDGE_IP == "10.0.100.1"


class TestSyscallNumbers:
    """Syscall numbers are for x86-64 Linux only."""

    def test_pivot_root(self) -> None:
        assert SYS_PIVOT_ROOT == 155

    def test_mount(self) -> None:
        assert SYS_MOUNT == 165

    def test_umount2(self) -> None:
        assert SYS_UMOUNT2 == 166

    def test_unshare(self) -> None:
        assert SYS_UNSHARE == 272

    def test_setns(self) -> None:
        assert SYS_SETNS == 308


class TestNamespaceFlags:
    def test_clone_newns(self) -> None:
        assert CLONE_NEWNS == 0x00020000

    def test_clone_newuts(self) -> None:
        assert CLONE_NEWUTS == 0x04000000

    def test_clone_newipc(self) -> None:
        assert CLONE_NEWIPC == 0x08000000

    def test_clone_newuser(self) -> None:
        assert CLONE_NEWUSER == 0x10000000

    def test_clone_newpid(self) -> None:
        assert CLONE_NEWPID == 0x20000000

    def test_clone_newnet(self) -> None:
        assert CLONE_NEWNET == 0x40000000


class TestEnvironmentOverrides:
    """Config values for paths and networking can be overridden via env vars."""

    def test_docklet_root_from_env(self) -> None:
        with patch.dict("os.environ", {"DOCKLET_ROOT": "/tmp/test-docklet"}):
            importlib.reload(config_module)
            assert Path("/tmp/test-docklet") == config_module.DOCKLET_ROOT
            assert Path("/tmp/test-docklet/containers") == config_module.CONTAINERS_DIR
            assert Path("/tmp/test-docklet/images") == config_module.IMAGES_DIR
            assert Path("/tmp/test-docklet/layers") == config_module.LAYERS_DIR
        importlib.reload(config_module)

    def test_bridge_name_from_env(self) -> None:
        with patch.dict("os.environ", {"DOCKLET_BRIDGE": "custom-br0"}):
            importlib.reload(config_module)
            assert config_module.NETWORK_BRIDGE == "custom-br0"
        importlib.reload(config_module)

    def test_subnet_from_env(self) -> None:
        with patch.dict("os.environ", {"DOCKLET_SUBNET": "172.16.0.0/16"}):
            importlib.reload(config_module)
            assert config_module.SUBNET == "172.16.0.0/16"
        importlib.reload(config_module)

    def test_bridge_ip_from_env(self) -> None:
        with patch.dict("os.environ", {"DOCKLET_BRIDGE_IP": "172.16.0.1"}):
            importlib.reload(config_module)
            assert config_module.BRIDGE_IP == "172.16.0.1"
        importlib.reload(config_module)
