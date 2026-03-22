"""Tests for docklet.cli — argparse CLI that ties together all user-facing commands."""

from __future__ import annotations

import sys
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# Inject a mock container module before importing cli, since container.py
# is being built concurrently on a separate branch and doesn't exist yet.
_mock_container_module = MagicMock()
sys.modules.setdefault("docklet.container", _mock_container_module)

from docklet.cli import _parse_image_tag, main  # noqa: E402


class TestParseImageTag:
    """Tests for the _parse_image_tag helper."""

    def test_image_with_tag(self) -> None:
        assert _parse_image_tag("alpine:3.18") == ("alpine", "3.18")

    def test_image_without_tag_defaults_to_latest(self) -> None:
        assert _parse_image_tag("alpine") == ("alpine", "latest")

    def test_image_with_empty_tag(self) -> None:
        """A trailing colon with nothing after it still defaults to latest."""
        assert _parse_image_tag("alpine:") == ("alpine", "latest")

    def test_image_with_namespace_and_tag(self) -> None:
        assert _parse_image_tag("myuser/myimage:v2") == ("myuser/myimage", "v2")

    def test_image_with_namespace_no_tag(self) -> None:
        assert _parse_image_tag("myuser/myimage") == ("myuser/myimage", "latest")


class TestRootCheck:
    """Tests for the root privilege check."""

    def test_non_root_exits_with_error(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch("os.geteuid", return_value=1000), pytest.raises(SystemExit) as exc_info:
            main(["pull", "alpine"])
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "docklet must be run as root" in captured.err

    def test_root_user_passes_check(self) -> None:
        """Root (euid 0) should not trigger the root check exit."""
        with (
            patch("os.geteuid", return_value=0),
            patch("docklet.cli.registry") as mock_registry,
        ):
            mock_registry.pull_image = MagicMock(return_value=["/some/layer"])
            # Should not raise SystemExit for root check
            main(["pull", "alpine"])


class TestNoSubcommand:
    """When no subcommand is given, help should be printed."""

    def test_no_args_exits_with_help(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch("os.geteuid", return_value=0), pytest.raises(SystemExit) as exc_info:
            main([])
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "usage" in captured.err.lower() or "usage" in captured.out.lower()


class TestPullCommand:
    """Tests for the 'pull' subcommand."""

    def test_pull_with_tag(self, capsys: pytest.CaptureFixture[str]) -> None:
        with (
            patch("os.geteuid", return_value=0),
            patch("docklet.cli.registry") as mock_registry,
        ):
            mock_registry.pull_image = MagicMock(return_value=["/layer/1", "/layer/2"])
            main(["pull", "alpine:3.18"])
            mock_registry.pull_image.assert_called_once_with("alpine", "3.18")
            captured = capsys.readouterr()
            assert "alpine:3.18" in captured.out

    def test_pull_without_tag_defaults_to_latest(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with (
            patch("os.geteuid", return_value=0),
            patch("docklet.cli.registry") as mock_registry,
        ):
            mock_registry.pull_image = MagicMock(return_value=["/layer/1"])
            main(["pull", "alpine"])
            mock_registry.pull_image.assert_called_once_with("alpine", "latest")
            captured = capsys.readouterr()
            assert "alpine:latest" in captured.out


class TestRunCommand:
    """Tests for the 'run' subcommand."""

    def test_run_basic(self, capsys: pytest.CaptureFixture[str]) -> None:
        with (
            patch("os.geteuid", return_value=0),
            patch("docklet.cli.container") as mock_container,
        ):
            mock_container.run = MagicMock(return_value="abc123")
            main(["run", "alpine"])
            mock_container.run.assert_called_once_with(
                "alpine", "latest", ["/bin/sh"], mem_limit=None, cpu_limit=None
            )
            captured = capsys.readouterr()
            assert "abc123" in captured.out

    def test_run_with_tag_and_command(self, capsys: pytest.CaptureFixture[str]) -> None:
        with (
            patch("os.geteuid", return_value=0),
            patch("docklet.cli.container") as mock_container,
        ):
            mock_container.run = MagicMock(return_value="def456")
            main(["run", "ubuntu:22.04", "/bin/bash", "-c", "echo hello"])
            mock_container.run.assert_called_once_with(
                "ubuntu", "22.04", ["/bin/bash", "-c", "echo hello"],
                mem_limit=None, cpu_limit=None
            )

    def test_run_with_memory_and_cpu(self, capsys: pytest.CaptureFixture[str]) -> None:
        with (
            patch("os.geteuid", return_value=0),
            patch("docklet.cli.container") as mock_container,
        ):
            mock_container.run = MagicMock(return_value="ghi789")
            main(["run", "-m", "512m", "-c", "50", "alpine", "/bin/sh"])
            mock_container.run.assert_called_once_with(
                "alpine", "latest", ["/bin/sh"], mem_limit="512m", cpu_limit=50
            )

    def test_run_default_command_is_sh(self, capsys: pytest.CaptureFixture[str]) -> None:
        with (
            patch("os.geteuid", return_value=0),
            patch("docklet.cli.container") as mock_container,
        ):
            mock_container.run = MagicMock(return_value="jkl012")
            main(["run", "alpine"])
            args = mock_container.run.call_args
            assert args[0][2] == ["/bin/sh"]


class TestExecCommand:
    """Tests for the 'exec' subcommand."""

    def test_exec_calls_container_exec_in(self) -> None:
        with (
            patch("os.geteuid", return_value=0),
            patch("docklet.cli.container") as mock_container,
        ):
            mock_container.exec_in = MagicMock()
            main(["exec", "abc123", "/bin/bash", "-c", "ls"])
            mock_container.exec_in.assert_called_once_with(
                "abc123", ["/bin/bash", "-c", "ls"]
            )


class TestPsCommand:
    """Tests for the 'ps' subcommand."""

    def test_ps_empty(self, capsys: pytest.CaptureFixture[str]) -> None:
        with (
            patch("os.geteuid", return_value=0),
            patch("docklet.cli.container") as mock_container,
        ):
            mock_container.list_containers = MagicMock(return_value=[])
            main(["ps"])
            captured = capsys.readouterr()
            assert "CONTAINER ID" in captured.out

    def test_ps_with_containers(self, capsys: pytest.CaptureFixture[str]) -> None:
        containers: list[dict[str, Any]] = [
            {
                "id": "abc123",
                "image": "alpine:latest",
                "command": "/bin/sh",
                "status": "running",
                "ip": "10.0.100.2",
            },
            {
                "id": "def456",
                "image": "ubuntu:22.04",
                "command": "/bin/bash",
                "status": "stopped",
                "ip": "10.0.100.3",
            },
        ]
        with (
            patch("os.geteuid", return_value=0),
            patch("docklet.cli.container") as mock_container,
        ):
            mock_container.list_containers = MagicMock(return_value=containers)
            main(["ps"])
            captured = capsys.readouterr()
            assert "abc123" in captured.out
            assert "def456" in captured.out
            assert "alpine:latest" in captured.out
            assert "running" in captured.out
            assert "10.0.100.2" in captured.out


class TestImagesCommand:
    """Tests for the 'images' subcommand."""

    def test_images_empty(self, capsys: pytest.CaptureFixture[str]) -> None:
        with (
            patch("os.geteuid", return_value=0),
            patch("docklet.cli.image") as mock_image,
        ):
            mock_image.list_images = MagicMock(return_value=[])
            main(["images"])
            captured = capsys.readouterr()
            assert "REPOSITORY" in captured.out

    def test_images_with_data(self, capsys: pytest.CaptureFixture[str]) -> None:
        images: list[dict[str, Any]] = [
            {"name": "alpine", "tag": "latest", "size": 5242880},
            {"name": "ubuntu", "tag": "22.04", "size": 78643200},
        ]
        with (
            patch("os.geteuid", return_value=0),
            patch("docklet.cli.image") as mock_image,
        ):
            mock_image.list_images = MagicMock(return_value=images)
            main(["images"])
            captured = capsys.readouterr()
            assert "alpine" in captured.out
            assert "latest" in captured.out
            assert "ubuntu" in captured.out
            assert "22.04" in captured.out


class TestRmCommand:
    """Tests for the 'rm' subcommand."""

    def test_rm_calls_container_remove(self, capsys: pytest.CaptureFixture[str]) -> None:
        with (
            patch("os.geteuid", return_value=0),
            patch("docklet.cli.container") as mock_container,
        ):
            mock_container.remove = MagicMock()
            main(["rm", "abc123"])
            mock_container.remove.assert_called_once_with("abc123")
            captured = capsys.readouterr()
            assert "abc123" in captured.out
