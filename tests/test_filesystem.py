"""Tests for docklet.filesystem — overlay filesystem and pivot_root."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from docklet import filesystem
from docklet.config import SYS_MOUNT, SYS_PIVOT_ROOT, SYS_UMOUNT2


class TestSetupOverlay:
    """Tests for setup_overlay() — mounts overlayfs for the container."""

    @patch("docklet.filesystem._libc")
    @patch("docklet.filesystem.CONTAINERS_DIR", new_callable=lambda: MagicMock(spec=Path))
    def test_creates_required_directories(
        self, mock_containers: MagicMock, mock_libc: MagicMock
    ) -> None:
        mock_libc.syscall.return_value = 0
        # Make __truediv__ return MagicMocks that also support __truediv__
        merged = MagicMock(spec=Path)
        upper = MagicMock(spec=Path)
        work = MagicMock(spec=Path)
        container_dir = MagicMock(spec=Path)
        container_dir.__truediv__ = MagicMock(
            side_effect=lambda k: {"merged": merged, "upper": upper, "work": work}[k]
        )
        mock_containers.__truediv__ = MagicMock(return_value=container_dir)

        # Need str() to work on the Path mocks
        merged.__str__ = MagicMock(return_value="/fake/merged")
        upper.__str__ = MagicMock(return_value="/fake/upper")
        work.__str__ = MagicMock(return_value="/fake/work")

        filesystem.setup_overlay("ctr1", ["/layers/base", "/layers/app"])

        merged.mkdir.assert_called_once_with(parents=True, exist_ok=True)
        upper.mkdir.assert_called_once_with(parents=True, exist_ok=True)
        work.mkdir.assert_called_once_with(parents=True, exist_ok=True)

    @patch("docklet.filesystem._libc")
    @patch("docklet.filesystem.CONTAINERS_DIR", new_callable=lambda: MagicMock(spec=Path))
    def test_calls_mount_syscall_with_overlay_options(
        self, mock_containers: MagicMock, mock_libc: MagicMock
    ) -> None:
        mock_libc.syscall.return_value = 0
        merged = MagicMock(spec=Path)
        upper = MagicMock(spec=Path)
        work = MagicMock(spec=Path)
        container_dir = MagicMock(spec=Path)
        container_dir.__truediv__ = MagicMock(
            side_effect=lambda k: {"merged": merged, "upper": upper, "work": work}[k]
        )
        mock_containers.__truediv__ = MagicMock(return_value=container_dir)

        merged.__str__ = MagicMock(return_value="/fake/merged")
        upper.__str__ = MagicMock(return_value="/fake/upper")
        work.__str__ = MagicMock(return_value="/fake/work")

        filesystem.setup_overlay("ctr1", ["/layers/base", "/layers/app"])

        # Verify mount syscall was called
        mock_libc.syscall.assert_called_once()
        args = mock_libc.syscall.call_args[0]
        assert args[0] == SYS_MOUNT  # syscall number
        assert args[1] == b"overlay"  # source
        assert args[2] == b"/fake/merged"  # target

    @patch("docklet.filesystem._libc")
    @patch("docklet.filesystem.CONTAINERS_DIR", new_callable=lambda: MagicMock(spec=Path))
    def test_returns_merged_path(
        self, mock_containers: MagicMock, mock_libc: MagicMock
    ) -> None:
        mock_libc.syscall.return_value = 0
        merged = MagicMock(spec=Path)
        upper = MagicMock(spec=Path)
        work = MagicMock(spec=Path)
        container_dir = MagicMock(spec=Path)
        container_dir.__truediv__ = MagicMock(
            side_effect=lambda k: {"merged": merged, "upper": upper, "work": work}[k]
        )
        mock_containers.__truediv__ = MagicMock(return_value=container_dir)

        merged.__str__ = MagicMock(return_value="/fake/merged")
        upper.__str__ = MagicMock(return_value="/fake/upper")
        work.__str__ = MagicMock(return_value="/fake/work")

        result = filesystem.setup_overlay("ctr1", ["/layers/base"])
        assert result == "/fake/merged"

    @patch("docklet.filesystem._libc")
    @patch("docklet.filesystem.CONTAINERS_DIR", new_callable=lambda: MagicMock(spec=Path))
    def test_overlay_options_contain_lowerdir_upperdir_workdir(
        self, mock_containers: MagicMock, mock_libc: MagicMock
    ) -> None:
        mock_libc.syscall.return_value = 0
        merged = MagicMock(spec=Path)
        upper = MagicMock(spec=Path)
        work = MagicMock(spec=Path)
        container_dir = MagicMock(spec=Path)
        container_dir.__truediv__ = MagicMock(
            side_effect=lambda k: {"merged": merged, "upper": upper, "work": work}[k]
        )
        mock_containers.__truediv__ = MagicMock(return_value=container_dir)

        merged.__str__ = MagicMock(return_value="/fake/merged")
        upper.__str__ = MagicMock(return_value="/fake/upper")
        work.__str__ = MagicMock(return_value="/fake/work")

        filesystem.setup_overlay("ctr1", ["/layers/base", "/layers/app"])

        args = mock_libc.syscall.call_args[0]
        # The data argument (mount options) should contain lowerdir, upperdir, workdir
        options = args[5]
        assert isinstance(options, bytes)
        assert b"lowerdir=/layers/base:/layers/app" in options
        assert b"upperdir=/fake/upper" in options
        assert b"workdir=/fake/work" in options

    @patch("docklet.filesystem._libc")
    @patch("docklet.filesystem.CONTAINERS_DIR", new_callable=lambda: MagicMock(spec=Path))
    @patch("ctypes.get_errno", return_value=1)
    def test_setup_overlay_failure_raises_oserror(
        self,
        mock_errno: MagicMock,
        mock_containers: MagicMock,
        mock_libc: MagicMock,
    ) -> None:
        mock_libc.syscall.return_value = -1
        merged = MagicMock(spec=Path)
        upper = MagicMock(spec=Path)
        work = MagicMock(spec=Path)
        container_dir = MagicMock(spec=Path)
        container_dir.__truediv__ = MagicMock(
            side_effect=lambda k: {"merged": merged, "upper": upper, "work": work}[k]
        )
        mock_containers.__truediv__ = MagicMock(return_value=container_dir)

        merged.__str__ = MagicMock(return_value="/fake/merged")
        upper.__str__ = MagicMock(return_value="/fake/upper")
        work.__str__ = MagicMock(return_value="/fake/work")

        try:
            filesystem.setup_overlay("ctr1", ["/layers/base"])
            raise AssertionError("Expected OSError")  # noqa: TRY301
        except OSError as exc:
            assert exc.errno == 1


class TestPivotRoot:
    """Tests for pivot_root() — the pivot_root dance."""

    @patch("docklet.filesystem.os")
    @patch("docklet.filesystem._libc")
    def test_bind_mounts_new_root_onto_itself(
        self, mock_libc: MagicMock, mock_os: MagicMock
    ) -> None:
        mock_libc.syscall.return_value = 0
        filesystem.pivot_root("/new_root")

        # First syscall should be bind mount (SYS_MOUNT)
        calls = mock_libc.syscall.call_args_list
        bind_call = calls[0]
        assert bind_call[0][0] == SYS_MOUNT
        assert bind_call[0][1] == b"/new_root"
        assert bind_call[0][2] == b"/new_root"

    @patch("docklet.filesystem.os")
    @patch("docklet.filesystem._libc")
    def test_chdir_to_new_root(
        self, mock_libc: MagicMock, mock_os: MagicMock
    ) -> None:
        mock_libc.syscall.return_value = 0
        filesystem.pivot_root("/new_root")
        mock_os.chdir.assert_called_once_with("/new_root")

    @patch("docklet.filesystem.os")
    @patch("docklet.filesystem._libc")
    def test_calls_pivot_root_syscall(
        self, mock_libc: MagicMock, mock_os: MagicMock
    ) -> None:
        mock_libc.syscall.return_value = 0
        filesystem.pivot_root("/new_root")

        calls = mock_libc.syscall.call_args_list
        # pivot_root syscall should be the second call
        pivot_call = calls[1]
        assert pivot_call[0][0] == SYS_PIVOT_ROOT
        assert pivot_call[0][1] == b"."
        assert pivot_call[0][2] == b"."

    @patch("docklet.filesystem.os")
    @patch("docklet.filesystem._libc")
    def test_umounts_old_root_with_mnt_detach(
        self, mock_libc: MagicMock, mock_os: MagicMock
    ) -> None:
        mock_libc.syscall.return_value = 0
        filesystem.pivot_root("/new_root")

        calls = mock_libc.syscall.call_args_list
        # umount2 should be the third syscall
        umount_call = calls[2]
        assert umount_call[0][0] == SYS_UMOUNT2
        assert umount_call[0][1] == b"."
        assert umount_call[0][2] == 0x00000002  # MNT_DETACH

    @patch("docklet.filesystem.os")
    @patch("docklet.filesystem._libc")
    @patch("ctypes.get_errno", return_value=22)
    def test_pivot_root_failure_raises_oserror(
        self, mock_errno: MagicMock, mock_libc: MagicMock, mock_os: MagicMock
    ) -> None:
        # First call (bind mount) succeeds, second (pivot_root) fails
        mock_libc.syscall.side_effect = [0, -1]
        try:
            filesystem.pivot_root("/new_root")
            raise AssertionError("Expected OSError")  # noqa: TRY301
        except OSError as exc:
            assert exc.errno == 22


class TestMountSpecial:
    """Tests for mount_special() — mounts /proc, /dev/pts, /dev/shm."""

    @patch("docklet.filesystem.os")
    @patch("docklet.filesystem._libc")
    def test_mounts_proc(self, mock_libc: MagicMock, mock_os: MagicMock) -> None:
        mock_libc.syscall.return_value = 0
        filesystem.mount_special("/rootfs")

        calls = mock_libc.syscall.call_args_list
        # Find the proc mount call
        proc_calls = [
            c for c in calls if len(c[0]) >= 3 and c[0][2] == b"/rootfs/proc"
        ]
        assert len(proc_calls) == 1
        assert proc_calls[0][0][1] == b"proc"  # source
        assert proc_calls[0][0][3] == b"proc"  # fstype

    @patch("docklet.filesystem.os")
    @patch("docklet.filesystem._libc")
    def test_mounts_devpts(self, mock_libc: MagicMock, mock_os: MagicMock) -> None:
        mock_libc.syscall.return_value = 0
        filesystem.mount_special("/rootfs")

        calls = mock_libc.syscall.call_args_list
        devpts_calls = [
            c for c in calls if len(c[0]) >= 3 and c[0][2] == b"/rootfs/dev/pts"
        ]
        assert len(devpts_calls) == 1
        assert devpts_calls[0][0][3] == b"devpts"

    @patch("docklet.filesystem.os")
    @patch("docklet.filesystem._libc")
    def test_mounts_devshm(self, mock_libc: MagicMock, mock_os: MagicMock) -> None:
        mock_libc.syscall.return_value = 0
        filesystem.mount_special("/rootfs")

        calls = mock_libc.syscall.call_args_list
        shm_calls = [
            c for c in calls if len(c[0]) >= 3 and c[0][2] == b"/rootfs/dev/shm"
        ]
        assert len(shm_calls) == 1
        assert shm_calls[0][0][3] == b"tmpfs"

    @patch("docklet.filesystem.os")
    @patch("docklet.filesystem._libc")
    def test_creates_mount_point_directories(
        self, mock_libc: MagicMock, mock_os: MagicMock
    ) -> None:
        mock_libc.syscall.return_value = 0
        filesystem.mount_special("/rootfs")

        # Should call os.makedirs for each mount point
        makedirs_calls = mock_os.makedirs.call_args_list
        paths = [c[0][0] for c in makedirs_calls]
        assert "/rootfs/proc" in paths
        assert "/rootfs/dev/pts" in paths
        assert "/rootfs/dev/shm" in paths

    @patch("docklet.filesystem.os")
    @patch("docklet.filesystem._libc")
    @patch("ctypes.get_errno", return_value=1)
    def test_mount_special_failure_raises_oserror(
        self, mock_errno: MagicMock, mock_libc: MagicMock, mock_os: MagicMock
    ) -> None:
        mock_libc.syscall.return_value = -1
        try:
            filesystem.mount_special("/rootfs")
            raise AssertionError("Expected OSError")  # noqa: TRY301
        except OSError as exc:
            assert exc.errno == 1


class TestCleanupOverlay:
    """Tests for cleanup_overlay() — unmounts and removes writable layer."""

    @patch("docklet.filesystem.shutil")
    @patch("docklet.filesystem._libc")
    @patch("docklet.filesystem.CONTAINERS_DIR", new_callable=lambda: MagicMock(spec=Path))
    def test_unmounts_merged_dir(
        self,
        mock_containers: MagicMock,
        mock_libc: MagicMock,
        mock_shutil: MagicMock,
    ) -> None:
        mock_libc.syscall.return_value = 0
        merged = MagicMock(spec=Path)
        upper = MagicMock(spec=Path)
        work = MagicMock(spec=Path)
        container_dir = MagicMock(spec=Path)
        container_dir.__truediv__ = MagicMock(
            side_effect=lambda k: {"merged": merged, "upper": upper, "work": work}[k]
        )
        mock_containers.__truediv__ = MagicMock(return_value=container_dir)
        merged.__str__ = MagicMock(return_value="/fake/merged")

        filesystem.cleanup_overlay("ctr1")

        # Should call umount2 syscall
        mock_libc.syscall.assert_called_once()
        args = mock_libc.syscall.call_args[0]
        assert args[0] == SYS_UMOUNT2
        assert args[1] == b"/fake/merged"

    @patch("docklet.filesystem.shutil")
    @patch("docklet.filesystem._libc")
    @patch("docklet.filesystem.CONTAINERS_DIR", new_callable=lambda: MagicMock(spec=Path))
    def test_removes_container_directory(
        self,
        mock_containers: MagicMock,
        mock_libc: MagicMock,
        mock_shutil: MagicMock,
    ) -> None:
        mock_libc.syscall.return_value = 0
        merged = MagicMock(spec=Path)
        upper = MagicMock(spec=Path)
        work = MagicMock(spec=Path)
        container_dir = MagicMock(spec=Path)
        container_dir.__truediv__ = MagicMock(
            side_effect=lambda k: {"merged": merged, "upper": upper, "work": work}[k]
        )
        mock_containers.__truediv__ = MagicMock(return_value=container_dir)
        merged.__str__ = MagicMock(return_value="/fake/merged")
        container_dir.__str__ = MagicMock(return_value="/fake/container")

        filesystem.cleanup_overlay("ctr1")

        mock_shutil.rmtree.assert_called_once_with(container_dir)
