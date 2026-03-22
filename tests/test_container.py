"""Tests for docklet.container — container lifecycle orchestration."""

from __future__ import annotations

import json
import signal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestParseMemoryLimit:
    """Tests for _parse_memory_limit(): converts strings like '512m' to bytes."""

    def test_megabytes(self) -> None:
        from docklet.container import _parse_memory_limit

        assert _parse_memory_limit("512m") == 512 * 1024 * 1024

    def test_gigabytes(self) -> None:
        from docklet.container import _parse_memory_limit

        assert _parse_memory_limit("1g") == 1 * 1024 * 1024 * 1024

    def test_kilobytes(self) -> None:
        from docklet.container import _parse_memory_limit

        assert _parse_memory_limit("256k") == 256 * 1024

    def test_bytes_plain(self) -> None:
        from docklet.container import _parse_memory_limit

        assert _parse_memory_limit("1048576b") == 1048576

    def test_uppercase_suffix(self) -> None:
        from docklet.container import _parse_memory_limit

        assert _parse_memory_limit("512M") == 512 * 1024 * 1024

    def test_invalid_suffix_raises(self) -> None:
        from docklet.container import _parse_memory_limit

        with pytest.raises(ValueError, match="Invalid memory limit"):
            _parse_memory_limit("512x")

    def test_non_numeric_raises(self) -> None:
        from docklet.container import _parse_memory_limit

        with pytest.raises(ValueError, match="Invalid memory limit"):
            _parse_memory_limit("abcm")


class TestCreate:
    """Tests for create(): generates ID, creates dir, writes config.json."""

    @patch("docklet.container.os.urandom", return_value=b"\xa1\xb2\xc3\xd4")
    def test_returns_8_char_hex_id(self, mock_urandom: MagicMock, tmp_path: Path) -> None:
        from docklet.container import create

        with patch("docklet.container.CONTAINERS_DIR", tmp_path):
            container_id = create("alpine", "latest", ["/bin/sh"])
        assert container_id == "a1b2c3d4"
        assert len(container_id) == 8

    @patch("docklet.container.os.urandom", return_value=b"\xa1\xb2\xc3\xd4")
    def test_creates_container_directory(self, mock_urandom: MagicMock, tmp_path: Path) -> None:
        from docklet.container import create

        with patch("docklet.container.CONTAINERS_DIR", tmp_path):
            container_id = create("alpine", "latest", ["/bin/sh"])
        assert (tmp_path / container_id).is_dir()

    @patch("docklet.container.os.urandom", return_value=b"\xa1\xb2\xc3\xd4")
    def test_writes_config_json(self, mock_urandom: MagicMock, tmp_path: Path) -> None:
        from docklet.container import create

        with patch("docklet.container.CONTAINERS_DIR", tmp_path):
            container_id = create("alpine", "latest", ["/bin/sh"])
        config_path = tmp_path / container_id / "config.json"
        assert config_path.is_file()
        config = json.loads(config_path.read_text())
        assert config["id"] == "a1b2c3d4"
        assert config["image"] == "alpine"
        assert config["tag"] == "latest"
        assert config["command"] == ["/bin/sh"]
        assert config["status"] == "created"
        assert config["pid"] is None
        assert config["ip"] is None

    @patch("docklet.container.os.urandom", return_value=b"\xa1\xb2\xc3\xd4")
    def test_writes_resource_limits(self, mock_urandom: MagicMock, tmp_path: Path) -> None:
        from docklet.container import create

        with patch("docklet.container.CONTAINERS_DIR", tmp_path):
            container_id = create(
                "alpine", "latest", ["/bin/sh"],
                mem_limit="512m", cpu_limit=50000,
            )
        config = json.loads((tmp_path / container_id / "config.json").read_text())
        assert config["mem_limit"] == "512m"
        assert config["cpu_limit"] == 50000

    @patch("docklet.container.os.urandom", return_value=b"\xa1\xb2\xc3\xd4")
    def test_config_has_created_timestamp(self, mock_urandom: MagicMock, tmp_path: Path) -> None:
        from docklet.container import create

        with patch("docklet.container.CONTAINERS_DIR", tmp_path):
            container_id = create("alpine", "latest", ["/bin/sh"])
        config = json.loads((tmp_path / container_id / "config.json").read_text())
        assert "created" in config
        # Should be ISO format timestamp
        assert "T" in config["created"]


class TestStart:
    """Tests for start(): fork + unshare + cgroup + network + double-fork."""

    @patch("docklet.container.os.waitpid")
    @patch("docklet.container.os.write")
    @patch("docklet.container.os.read", return_value=b"1")
    @patch("docklet.container.os.close")
    @patch("docklet.container.os.pipe", return_value=(10, 11))
    @patch("docklet.container.os.fork", return_value=42)  # parent side: child PID=42
    @patch("docklet.container.network")
    @patch("docklet.container.cgroups")
    @patch("docklet.container.image")
    def test_parent_sets_up_cgroup(
        self,
        mock_image: MagicMock,
        mock_cgroups: MagicMock,
        mock_network: MagicMock,
        mock_fork: MagicMock,
        mock_pipe: MagicMock,
        mock_close: MagicMock,
        mock_read: MagicMock,
        mock_write: MagicMock,
        mock_waitpid: MagicMock,
        tmp_path: Path,
    ) -> None:
        from docklet.container import start

        mock_image.get_layers.return_value = ["/layers/abc"]
        mock_network.setup_container_net.return_value = "10.0.100.2"
        mock_waitpid.return_value = (42, 0)

        container_id = "a1b2c3d4"
        container_dir = tmp_path / container_id
        container_dir.mkdir()
        config = {
            "id": container_id,
            "image": "alpine",
            "tag": "latest",
            "command": ["/bin/sh"],
            "pid": None,
            "status": "created",
            "ip": None,
            "created": "2026-03-21T12:00:00",
            "mem_limit": "512m",
            "cpu_limit": 50000,
        }
        (container_dir / "config.json").write_text(json.dumps(config))

        with patch("docklet.container.CONTAINERS_DIR", tmp_path):
            start(container_id)

        mock_cgroups.init.assert_called_once()
        mock_cgroups.create.assert_called_once_with(container_id)
        mock_cgroups.add_process.assert_called_once_with(container_id, 42)
        mock_cgroups.set_memory_limit.assert_called_once_with(
            container_id, 512 * 1024 * 1024
        )
        mock_cgroups.set_cpu_limit.assert_called_once_with(container_id, 50000)

    @patch("docklet.container.os.waitpid")
    @patch("docklet.container.os.write")
    @patch("docklet.container.os.read", return_value=b"1")
    @patch("docklet.container.os.close")
    @patch("docklet.container.os.pipe", return_value=(10, 11))
    @patch("docklet.container.os.fork", return_value=42)
    @patch("docklet.container.network")
    @patch("docklet.container.cgroups")
    @patch("docklet.container.image")
    def test_parent_sets_up_network(
        self,
        mock_image: MagicMock,
        mock_cgroups: MagicMock,
        mock_network: MagicMock,
        mock_fork: MagicMock,
        mock_pipe: MagicMock,
        mock_close: MagicMock,
        mock_read: MagicMock,
        mock_write: MagicMock,
        mock_waitpid: MagicMock,
        tmp_path: Path,
    ) -> None:
        from docklet.container import start

        mock_image.get_layers.return_value = ["/layers/abc"]
        mock_network.setup_container_net.return_value = "10.0.100.2"
        mock_network.setup_bridge.return_value = None
        mock_waitpid.return_value = (42, 0)

        container_id = "a1b2c3d4"
        container_dir = tmp_path / container_id
        container_dir.mkdir()
        config = {
            "id": container_id,
            "image": "alpine",
            "tag": "latest",
            "command": ["/bin/sh"],
            "pid": None,
            "status": "created",
            "ip": None,
            "created": "2026-03-21T12:00:00",
            "mem_limit": None,
            "cpu_limit": None,
        }
        (container_dir / "config.json").write_text(json.dumps(config))

        with patch("docklet.container.CONTAINERS_DIR", tmp_path):
            start(container_id)

        mock_network.setup_bridge.assert_called_once()
        mock_network.setup_container_net.assert_called_once_with(container_id, 42)

    @patch("docklet.container.os.waitpid")
    @patch("docklet.container.os.write")
    @patch("docklet.container.os.read", return_value=b"1")
    @patch("docklet.container.os.close")
    @patch("docklet.container.os.pipe", return_value=(10, 11))
    @patch("docklet.container.os.fork", return_value=42)
    @patch("docklet.container.network")
    @patch("docklet.container.cgroups")
    @patch("docklet.container.image")
    def test_parent_writes_config_with_pid_and_ip(
        self,
        mock_image: MagicMock,
        mock_cgroups: MagicMock,
        mock_network: MagicMock,
        mock_fork: MagicMock,
        mock_pipe: MagicMock,
        mock_close: MagicMock,
        mock_read: MagicMock,
        mock_write: MagicMock,
        mock_waitpid: MagicMock,
        tmp_path: Path,
    ) -> None:
        from docklet.container import start

        mock_image.get_layers.return_value = ["/layers/abc"]
        mock_network.setup_container_net.return_value = "10.0.100.2"
        mock_waitpid.return_value = (42, 0)

        container_id = "a1b2c3d4"
        container_dir = tmp_path / container_id
        container_dir.mkdir()
        config = {
            "id": container_id,
            "image": "alpine",
            "tag": "latest",
            "command": ["/bin/sh"],
            "pid": None,
            "status": "created",
            "ip": None,
            "created": "2026-03-21T12:00:00",
            "mem_limit": None,
            "cpu_limit": None,
        }
        (container_dir / "config.json").write_text(json.dumps(config))

        with patch("docklet.container.CONTAINERS_DIR", tmp_path):
            start(container_id)

        updated = json.loads((container_dir / "config.json").read_text())
        assert updated["pid"] == 42
        assert updated["ip"] == "10.0.100.2"
        assert updated["status"] == "running"

    @patch("docklet.container.os.waitpid")
    @patch("docklet.container.os.write")
    @patch("docklet.container.os.read", return_value=b"1")
    @patch("docklet.container.os.close")
    @patch("docklet.container.os.pipe", return_value=(10, 11))
    @patch("docklet.container.os.fork", return_value=42)
    @patch("docklet.container.network")
    @patch("docklet.container.cgroups")
    @patch("docklet.container.image")
    def test_parent_skips_limits_when_none(
        self,
        mock_image: MagicMock,
        mock_cgroups: MagicMock,
        mock_network: MagicMock,
        mock_fork: MagicMock,
        mock_pipe: MagicMock,
        mock_close: MagicMock,
        mock_read: MagicMock,
        mock_write: MagicMock,
        mock_waitpid: MagicMock,
        tmp_path: Path,
    ) -> None:
        from docklet.container import start

        mock_image.get_layers.return_value = ["/layers/abc"]
        mock_network.setup_container_net.return_value = "10.0.100.2"
        mock_waitpid.return_value = (42, 0)

        container_id = "a1b2c3d4"
        container_dir = tmp_path / container_id
        container_dir.mkdir()
        config = {
            "id": container_id,
            "image": "alpine",
            "tag": "latest",
            "command": ["/bin/sh"],
            "pid": None,
            "status": "created",
            "ip": None,
            "created": "2026-03-21T12:00:00",
            "mem_limit": None,
            "cpu_limit": None,
        }
        (container_dir / "config.json").write_text(json.dumps(config))

        with patch("docklet.container.CONTAINERS_DIR", tmp_path):
            start(container_id)

        mock_cgroups.set_memory_limit.assert_not_called()
        mock_cgroups.set_cpu_limit.assert_not_called()

    @patch("docklet.container.os.waitpid")
    @patch("docklet.container.os.write")
    @patch("docklet.container.os.read", return_value=b"1")
    @patch("docklet.container.os.close")
    @patch("docklet.container.os.pipe", return_value=(10, 11))
    @patch("docklet.container.os.fork", return_value=42)
    @patch("docklet.container.network")
    @patch("docklet.container.cgroups")
    @patch("docklet.container.image")
    def test_parent_signals_child_network_ready(
        self,
        mock_image: MagicMock,
        mock_cgroups: MagicMock,
        mock_network: MagicMock,
        mock_fork: MagicMock,
        mock_pipe: MagicMock,
        mock_close: MagicMock,
        mock_read: MagicMock,
        mock_write: MagicMock,
        mock_waitpid: MagicMock,
        tmp_path: Path,
    ) -> None:
        from docklet.container import start

        mock_image.get_layers.return_value = ["/layers/abc"]
        mock_network.setup_container_net.return_value = "10.0.100.2"
        mock_waitpid.return_value = (42, 0)

        container_id = "a1b2c3d4"
        container_dir = tmp_path / container_id
        container_dir.mkdir()
        config = {
            "id": container_id,
            "image": "alpine",
            "tag": "latest",
            "command": ["/bin/sh"],
            "pid": None,
            "status": "created",
            "ip": None,
            "created": "2026-03-21T12:00:00",
            "mem_limit": None,
            "cpu_limit": None,
        }
        (container_dir / "config.json").write_text(json.dumps(config))

        with patch("docklet.container.CONTAINERS_DIR", tmp_path):
            start(container_id)

        # Parent reads from pipe (child's unshare-done signal) then writes to pipe (network-ready)
        mock_read.assert_called()
        mock_write.assert_called()

    @patch("docklet.container.os._exit")
    @patch("docklet.container.os.execvp")
    @patch("docklet.container.namespaces")
    @patch("docklet.container.filesystem")
    @patch("docklet.container.os.waitpid")
    @patch("docklet.container.os.write")
    @patch("docklet.container.os.read", return_value=b"1")
    @patch("docklet.container.os.close")
    @patch("docklet.container.os.pipe", return_value=(10, 11))
    @patch("docklet.container.os.fork")
    @patch("docklet.container.network")
    @patch("docklet.container.cgroups")
    @patch("docklet.container.image")
    def test_child_calls_unshare(
        self,
        mock_image: MagicMock,
        mock_cgroups: MagicMock,
        mock_network: MagicMock,
        mock_fork: MagicMock,
        mock_pipe: MagicMock,
        mock_close: MagicMock,
        mock_read: MagicMock,
        mock_write: MagicMock,
        mock_waitpid: MagicMock,
        mock_filesystem: MagicMock,
        mock_namespaces: MagicMock,
        mock_execvp: MagicMock,
        mock_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        from docklet.container import start

        mock_image.get_layers.return_value = ["/layers/abc"]
        mock_network.setup_container_net.return_value = "10.0.100.2"
        mock_filesystem.setup_overlay.return_value = "/merged"
        # First fork returns 0 (child), second fork returns 0 (inner child)
        mock_fork.side_effect = [0, 0]
        mock_waitpid.return_value = (0, 0)

        container_id = "a1b2c3d4"
        container_dir = tmp_path / container_id
        container_dir.mkdir()
        config = {
            "id": container_id,
            "image": "alpine",
            "tag": "latest",
            "command": ["/bin/sh"],
            "pid": None,
            "status": "created",
            "ip": None,
            "created": "2026-03-21T12:00:00",
            "mem_limit": None,
            "cpu_limit": None,
        }
        (container_dir / "config.json").write_text(json.dumps(config))

        with patch("docklet.container.CONTAINERS_DIR", tmp_path):
            start(container_id)

        mock_namespaces.unshare.assert_called_once()
        # Verify unshare flags include required namespaces
        unshare_flags = mock_namespaces.unshare.call_args[0][0]
        from docklet.config import (
            CLONE_NEWIPC,
            CLONE_NEWNET,
            CLONE_NEWNS,
            CLONE_NEWPID,
            CLONE_NEWUTS,
        )

        assert unshare_flags & CLONE_NEWPID
        assert unshare_flags & CLONE_NEWNS
        assert unshare_flags & CLONE_NEWUTS
        assert unshare_flags & CLONE_NEWIPC
        assert unshare_flags & CLONE_NEWNET

    @patch("docklet.container.os._exit")
    @patch("docklet.container.os.execvp")
    @patch("docklet.container.namespaces")
    @patch("docklet.container.filesystem")
    @patch("docklet.container.os.waitpid")
    @patch("docklet.container.os.write")
    @patch("docklet.container.os.read", return_value=b"1")
    @patch("docklet.container.os.close")
    @patch("docklet.container.os.pipe", return_value=(10, 11))
    @patch("docklet.container.os.fork")
    @patch("docklet.container.network")
    @patch("docklet.container.cgroups")
    @patch("docklet.container.image")
    def test_inner_child_sets_up_filesystem_and_execs(
        self,
        mock_image: MagicMock,
        mock_cgroups: MagicMock,
        mock_network: MagicMock,
        mock_fork: MagicMock,
        mock_pipe: MagicMock,
        mock_close: MagicMock,
        mock_read: MagicMock,
        mock_write: MagicMock,
        mock_waitpid: MagicMock,
        mock_filesystem: MagicMock,
        mock_namespaces: MagicMock,
        mock_execvp: MagicMock,
        mock_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        from docklet.container import start

        mock_image.get_layers.return_value = ["/layers/abc"]
        mock_network.setup_container_net.return_value = "10.0.100.2"
        mock_filesystem.setup_overlay.return_value = "/merged"
        # First fork returns 0 (child), second fork returns 0 (inner child)
        mock_fork.side_effect = [0, 0]
        mock_waitpid.return_value = (0, 0)

        container_id = "a1b2c3d4"
        container_dir = tmp_path / container_id
        container_dir.mkdir()
        config = {
            "id": container_id,
            "image": "alpine",
            "tag": "latest",
            "command": ["/bin/sh"],
            "pid": None,
            "status": "created",
            "ip": None,
            "created": "2026-03-21T12:00:00",
            "mem_limit": None,
            "cpu_limit": None,
        }
        (container_dir / "config.json").write_text(json.dumps(config))

        with patch("docklet.container.CONTAINERS_DIR", tmp_path):
            start(container_id)

        mock_filesystem.setup_overlay.assert_called_once_with(container_id, ["/layers/abc"])
        mock_filesystem.mount_special.assert_called_once_with("/merged")
        mock_filesystem.pivot_root.assert_called_once_with("/merged")
        mock_namespaces.sethostname.assert_called_once_with(container_id[:8])
        mock_execvp.assert_called_once_with("/bin/sh", ["/bin/sh"])


class TestRun:
    """Tests for run(): calls create() then start(), returns container ID."""

    @patch("docklet.container.start")
    @patch("docklet.container.create", return_value="a1b2c3d4")
    def test_calls_create_then_start(
        self, mock_create: MagicMock, mock_start: MagicMock
    ) -> None:
        from docklet.container import run

        result = run("alpine", "latest", ["/bin/sh"])
        mock_create.assert_called_once_with(
            "alpine", "latest", ["/bin/sh"],
            mem_limit=None, cpu_limit=None,
        )
        mock_start.assert_called_once_with("a1b2c3d4")
        assert result == "a1b2c3d4"

    @patch("docklet.container.start")
    @patch("docklet.container.create", return_value="a1b2c3d4")
    def test_passes_resource_limits(
        self, mock_create: MagicMock, mock_start: MagicMock
    ) -> None:
        from docklet.container import run

        run("alpine", "latest", ["/bin/sh"], mem_limit="256m", cpu_limit=25000)
        mock_create.assert_called_once_with(
            "alpine", "latest", ["/bin/sh"],
            mem_limit="256m", cpu_limit=25000,
        )

    @patch("docklet.container.start")
    @patch("docklet.container.create", return_value="deadbeef")
    def test_returns_container_id(
        self, mock_create: MagicMock, mock_start: MagicMock
    ) -> None:
        from docklet.container import run

        result = run("ubuntu", "22.04", ["/bin/bash"])
        assert result == "deadbeef"


class TestStop:
    """Tests for stop(): sends SIGTERM then SIGKILL, updates config."""

    @patch("docklet.container.os.kill")
    @patch("docklet.container.os.waitpid")
    def test_sends_sigterm(
        self, mock_waitpid: MagicMock, mock_kill: MagicMock, tmp_path: Path
    ) -> None:
        from docklet.container import stop

        mock_waitpid.return_value = (42, 0)

        container_id = "a1b2c3d4"
        container_dir = tmp_path / container_id
        container_dir.mkdir()
        config = {
            "id": container_id,
            "image": "alpine",
            "tag": "latest",
            "command": ["/bin/sh"],
            "pid": 42,
            "status": "running",
            "ip": "10.0.100.2",
            "created": "2026-03-21T12:00:00",
            "mem_limit": None,
            "cpu_limit": None,
        }
        (container_dir / "config.json").write_text(json.dumps(config))

        with patch("docklet.container.CONTAINERS_DIR", tmp_path):
            stop(container_id)

        # Should send SIGTERM first
        mock_kill.assert_any_call(42, signal.SIGTERM)

    @patch("docklet.container.os.kill")
    @patch("docklet.container.os.waitpid")
    def test_sends_sigkill_after_timeout(
        self, mock_waitpid: MagicMock, mock_kill: MagicMock, tmp_path: Path
    ) -> None:
        from docklet.container import stop

        # waitpid times out (returns 0, 0 meaning child still running), then succeeds
        mock_waitpid.side_effect = [ChildProcessError, (42, 0)]

        container_id = "a1b2c3d4"
        container_dir = tmp_path / container_id
        container_dir.mkdir()
        config = {
            "id": container_id,
            "image": "alpine",
            "tag": "latest",
            "command": ["/bin/sh"],
            "pid": 42,
            "status": "running",
            "ip": "10.0.100.2",
            "created": "2026-03-21T12:00:00",
            "mem_limit": None,
            "cpu_limit": None,
        }
        (container_dir / "config.json").write_text(json.dumps(config))

        with patch("docklet.container.CONTAINERS_DIR", tmp_path):
            stop(container_id)

        mock_kill.assert_any_call(42, signal.SIGKILL)

    @patch("docklet.container.os.kill")
    @patch("docklet.container.os.waitpid")
    def test_updates_status_to_stopped(
        self, mock_waitpid: MagicMock, mock_kill: MagicMock, tmp_path: Path
    ) -> None:
        from docklet.container import stop

        mock_waitpid.return_value = (42, 0)

        container_id = "a1b2c3d4"
        container_dir = tmp_path / container_id
        container_dir.mkdir()
        config = {
            "id": container_id,
            "image": "alpine",
            "tag": "latest",
            "command": ["/bin/sh"],
            "pid": 42,
            "status": "running",
            "ip": "10.0.100.2",
            "created": "2026-03-21T12:00:00",
            "mem_limit": None,
            "cpu_limit": None,
        }
        (container_dir / "config.json").write_text(json.dumps(config))

        with patch("docklet.container.CONTAINERS_DIR", tmp_path):
            stop(container_id)

        updated = json.loads((container_dir / "config.json").read_text())
        assert updated["status"] == "stopped"

    def test_stop_already_stopped_is_noop(self, tmp_path: Path) -> None:
        from docklet.container import stop

        container_id = "a1b2c3d4"
        container_dir = tmp_path / container_id
        container_dir.mkdir()
        config = {
            "id": container_id,
            "image": "alpine",
            "tag": "latest",
            "command": ["/bin/sh"],
            "pid": None,
            "status": "stopped",
            "ip": "10.0.100.2",
            "created": "2026-03-21T12:00:00",
            "mem_limit": None,
            "cpu_limit": None,
        }
        (container_dir / "config.json").write_text(json.dumps(config))

        with patch("docklet.container.CONTAINERS_DIR", tmp_path):
            stop(container_id)  # Should not raise


class TestRemove:
    """Tests for remove(): stops if running, cleans up all resources, removes dir."""

    @patch("docklet.container.cgroups")
    @patch("docklet.container.network")
    @patch("docklet.container.filesystem")
    @patch("docklet.container.stop")
    def test_stops_running_container(
        self,
        mock_stop: MagicMock,
        mock_filesystem: MagicMock,
        mock_network: MagicMock,
        mock_cgroups: MagicMock,
        tmp_path: Path,
    ) -> None:
        from docklet.container import remove

        container_id = "a1b2c3d4"
        container_dir = tmp_path / container_id
        container_dir.mkdir()
        config = {
            "id": container_id,
            "image": "alpine",
            "tag": "latest",
            "command": ["/bin/sh"],
            "pid": 42,
            "status": "running",
            "ip": "10.0.100.2",
            "created": "2026-03-21T12:00:00",
            "mem_limit": None,
            "cpu_limit": None,
        }
        (container_dir / "config.json").write_text(json.dumps(config))

        with patch("docklet.container.CONTAINERS_DIR", tmp_path):
            remove(container_id)

        mock_stop.assert_called_once_with(container_id)

    @patch("docklet.container.shutil")
    @patch("docklet.container.cgroups")
    @patch("docklet.container.network")
    @patch("docklet.container.filesystem")
    @patch("docklet.container.stop")
    def test_cleans_up_resources(
        self,
        mock_stop: MagicMock,
        mock_filesystem: MagicMock,
        mock_network: MagicMock,
        mock_cgroups: MagicMock,
        mock_shutil: MagicMock,
        tmp_path: Path,
    ) -> None:
        from docklet.container import remove

        container_id = "a1b2c3d4"
        container_dir = tmp_path / container_id
        container_dir.mkdir()
        config = {
            "id": container_id,
            "image": "alpine",
            "tag": "latest",
            "command": ["/bin/sh"],
            "pid": 42,
            "status": "running",
            "ip": "10.0.100.2",
            "created": "2026-03-21T12:00:00",
            "mem_limit": None,
            "cpu_limit": None,
        }
        (container_dir / "config.json").write_text(json.dumps(config))

        with patch("docklet.container.CONTAINERS_DIR", tmp_path):
            remove(container_id)

        mock_filesystem.cleanup_overlay.assert_called_once_with(container_id)
        mock_cgroups.cleanup.assert_called_once_with(container_id)
        mock_network.cleanup_net.assert_called_once_with(container_id)

    @patch("docklet.container.cgroups")
    @patch("docklet.container.network")
    @patch("docklet.container.filesystem")
    @patch("docklet.container.stop")
    def test_does_not_stop_stopped_container(
        self,
        mock_stop: MagicMock,
        mock_filesystem: MagicMock,
        mock_network: MagicMock,
        mock_cgroups: MagicMock,
        tmp_path: Path,
    ) -> None:
        from docklet.container import remove

        container_id = "a1b2c3d4"
        container_dir = tmp_path / container_id
        container_dir.mkdir()
        config = {
            "id": container_id,
            "image": "alpine",
            "tag": "latest",
            "command": ["/bin/sh"],
            "pid": None,
            "status": "stopped",
            "ip": "10.0.100.2",
            "created": "2026-03-21T12:00:00",
            "mem_limit": None,
            "cpu_limit": None,
        }
        (container_dir / "config.json").write_text(json.dumps(config))

        with patch("docklet.container.CONTAINERS_DIR", tmp_path):
            remove(container_id)

        mock_stop.assert_not_called()


class TestListContainers:
    """Tests for list_containers(): reads configs, checks PID liveness."""

    def test_empty_when_no_containers(self, tmp_path: Path) -> None:
        from docklet.container import list_containers

        with patch("docklet.container.CONTAINERS_DIR", tmp_path):
            result = list_containers()
        assert result == []

    def test_returns_container_info(self, tmp_path: Path) -> None:
        from docklet.container import list_containers

        container_id = "a1b2c3d4"
        container_dir = tmp_path / container_id
        container_dir.mkdir()
        config = {
            "id": container_id,
            "image": "alpine",
            "tag": "latest",
            "command": ["/bin/sh"],
            "pid": None,
            "status": "stopped",
            "ip": "10.0.100.2",
            "created": "2026-03-21T12:00:00",
            "mem_limit": None,
            "cpu_limit": None,
        }
        (container_dir / "config.json").write_text(json.dumps(config))

        with patch("docklet.container.CONTAINERS_DIR", tmp_path):
            result = list_containers()

        assert len(result) == 1
        assert result[0]["id"] == container_id
        assert result[0]["status"] == "stopped"

    @patch("docklet.container.os.kill")
    def test_marks_running_if_pid_alive(
        self, mock_kill: MagicMock, tmp_path: Path
    ) -> None:
        from docklet.container import list_containers

        mock_kill.return_value = None  # signal 0 succeeds → process alive

        container_id = "a1b2c3d4"
        container_dir = tmp_path / container_id
        container_dir.mkdir()
        config = {
            "id": container_id,
            "image": "alpine",
            "tag": "latest",
            "command": ["/bin/sh"],
            "pid": 42,
            "status": "running",
            "ip": "10.0.100.2",
            "created": "2026-03-21T12:00:00",
            "mem_limit": None,
            "cpu_limit": None,
        }
        (container_dir / "config.json").write_text(json.dumps(config))

        with patch("docklet.container.CONTAINERS_DIR", tmp_path):
            result = list_containers()

        assert result[0]["status"] == "running"
        mock_kill.assert_called_with(42, 0)

    @patch("docklet.container.os.kill")
    def test_marks_stopped_if_pid_dead(
        self, mock_kill: MagicMock, tmp_path: Path
    ) -> None:
        from docklet.container import list_containers

        mock_kill.side_effect = ProcessLookupError  # PID doesn't exist

        container_id = "a1b2c3d4"
        container_dir = tmp_path / container_id
        container_dir.mkdir()
        config = {
            "id": container_id,
            "image": "alpine",
            "tag": "latest",
            "command": ["/bin/sh"],
            "pid": 42,
            "status": "running",
            "ip": "10.0.100.2",
            "created": "2026-03-21T12:00:00",
            "mem_limit": None,
            "cpu_limit": None,
        }
        (container_dir / "config.json").write_text(json.dumps(config))

        with patch("docklet.container.CONTAINERS_DIR", tmp_path):
            result = list_containers()

        assert result[0]["status"] == "stopped"

    def test_ignores_dirs_without_config(self, tmp_path: Path) -> None:
        from docklet.container import list_containers

        (tmp_path / "broken").mkdir()

        with patch("docklet.container.CONTAINERS_DIR", tmp_path):
            result = list_containers()

        assert result == []

    def test_returns_multiple_containers(self, tmp_path: Path) -> None:
        from docklet.container import list_containers

        for cid in ["aaaa1111", "bbbb2222"]:
            d = tmp_path / cid
            d.mkdir()
            config = {
                "id": cid,
                "image": "alpine",
                "tag": "latest",
                "command": ["/bin/sh"],
                "pid": None,
                "status": "stopped",
                "ip": None,
                "created": "2026-03-21T12:00:00",
                "mem_limit": None,
                "cpu_limit": None,
            }
            (d / "config.json").write_text(json.dumps(config))

        with patch("docklet.container.CONTAINERS_DIR", tmp_path):
            result = list_containers()

        assert len(result) == 2


class TestExecIn:
    """Tests for exec_in(): enters existing container namespaces and runs command."""

    @patch("docklet.container.os._exit")
    @patch("docklet.container.os.execvp")
    @patch("docklet.container.os.fork", return_value=0)
    @patch("docklet.container.namespaces")
    @patch("docklet.container.os.close")
    @patch("docklet.container.os.open", return_value=5)
    def test_opens_namespace_files(
        self,
        mock_os_open: MagicMock,
        mock_close: MagicMock,
        mock_namespaces: MagicMock,
        mock_fork: MagicMock,
        mock_execvp: MagicMock,
        mock_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        from docklet.container import exec_in

        container_id = "a1b2c3d4"
        container_dir = tmp_path / container_id
        container_dir.mkdir()
        config = {
            "id": container_id,
            "image": "alpine",
            "tag": "latest",
            "command": ["/bin/sh"],
            "pid": 42,
            "status": "running",
            "ip": "10.0.100.2",
            "created": "2026-03-21T12:00:00",
            "mem_limit": None,
            "cpu_limit": None,
        }
        (container_dir / "config.json").write_text(json.dumps(config))

        with patch("docklet.container.CONTAINERS_DIR", tmp_path):
            exec_in(container_id, ["/bin/ls"])

        # Should open namespace files for pid, mnt, uts, ipc, net
        ns_types = {"pid", "mnt", "uts", "ipc", "net"}
        opened_paths = {c[0][0] for c in mock_os_open.call_args_list}
        for ns in ns_types:
            assert f"/proc/42/ns/{ns}" in opened_paths

    @patch("docklet.container.os._exit")
    @patch("docklet.container.os.execvp")
    @patch("docklet.container.os.fork", return_value=0)
    @patch("docklet.container.namespaces")
    @patch("docklet.container.os.close")
    @patch("docklet.container.os.open", return_value=5)
    def test_calls_setns_for_each_namespace(
        self,
        mock_os_open: MagicMock,
        mock_close: MagicMock,
        mock_namespaces: MagicMock,
        mock_fork: MagicMock,
        mock_execvp: MagicMock,
        mock_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        from docklet.container import exec_in

        container_id = "a1b2c3d4"
        container_dir = tmp_path / container_id
        container_dir.mkdir()
        config = {
            "id": container_id,
            "image": "alpine",
            "tag": "latest",
            "command": ["/bin/sh"],
            "pid": 42,
            "status": "running",
            "ip": "10.0.100.2",
            "created": "2026-03-21T12:00:00",
            "mem_limit": None,
            "cpu_limit": None,
        }
        (container_dir / "config.json").write_text(json.dumps(config))

        with patch("docklet.container.CONTAINERS_DIR", tmp_path):
            exec_in(container_id, ["/bin/ls"])

        # setns should be called 5 times (one for each namespace)
        assert mock_namespaces.setns.call_count == 5

    @patch("docklet.container.os._exit")
    @patch("docklet.container.os.execvp")
    @patch("docklet.container.os.fork", return_value=0)
    @patch("docklet.container.namespaces")
    @patch("docklet.container.os.close")
    @patch("docklet.container.os.open", return_value=5)
    def test_execs_command_after_setns(
        self,
        mock_os_open: MagicMock,
        mock_close: MagicMock,
        mock_namespaces: MagicMock,
        mock_fork: MagicMock,
        mock_execvp: MagicMock,
        mock_exit: MagicMock,
        tmp_path: Path,
    ) -> None:
        from docklet.container import exec_in

        container_id = "a1b2c3d4"
        container_dir = tmp_path / container_id
        container_dir.mkdir()
        config = {
            "id": container_id,
            "image": "alpine",
            "tag": "latest",
            "command": ["/bin/sh"],
            "pid": 42,
            "status": "running",
            "ip": "10.0.100.2",
            "created": "2026-03-21T12:00:00",
            "mem_limit": None,
            "cpu_limit": None,
        }
        (container_dir / "config.json").write_text(json.dumps(config))

        with patch("docklet.container.CONTAINERS_DIR", tmp_path):
            exec_in(container_id, ["/bin/ls", "-la"])

        mock_execvp.assert_called_once_with("/bin/ls", ["/bin/ls", "-la"])

    @patch("docklet.container.os.waitpid")
    @patch("docklet.container.os.fork", return_value=99)
    @patch("docklet.container.namespaces")
    @patch("docklet.container.os.close")
    @patch("docklet.container.os.open", return_value=5)
    def test_parent_waits_for_child(
        self,
        mock_os_open: MagicMock,
        mock_close: MagicMock,
        mock_namespaces: MagicMock,
        mock_fork: MagicMock,
        mock_waitpid: MagicMock,
        tmp_path: Path,
    ) -> None:
        from docklet.container import exec_in

        mock_waitpid.return_value = (99, 0)

        container_id = "a1b2c3d4"
        container_dir = tmp_path / container_id
        container_dir.mkdir()
        config = {
            "id": container_id,
            "image": "alpine",
            "tag": "latest",
            "command": ["/bin/sh"],
            "pid": 42,
            "status": "running",
            "ip": "10.0.100.2",
            "created": "2026-03-21T12:00:00",
            "mem_limit": None,
            "cpu_limit": None,
        }
        (container_dir / "config.json").write_text(json.dumps(config))

        with patch("docklet.container.CONTAINERS_DIR", tmp_path):
            exec_in(container_id, ["/bin/ls"])

        mock_waitpid.assert_called_once_with(99, 0)
