"""Tests for docklet.namespaces — Linux namespace syscall wrappers."""

from unittest.mock import MagicMock, patch

from docklet.config import CLONE_NEWNS, CLONE_NEWPID, CLONE_NEWUTS


class TestUnshare:
    """Tests for unshare() — moves calling process into new namespaces."""

    @patch("docklet.namespaces._libc")
    def test_unshare_calls_libc_with_flags(self, mock_libc: MagicMock) -> None:
        from docklet.namespaces import unshare

        mock_libc.unshare.return_value = 0
        flags = CLONE_NEWNS | CLONE_NEWPID | CLONE_NEWUTS
        unshare(flags)
        mock_libc.unshare.assert_called_once_with(flags)

    @patch("docklet.namespaces._libc")
    def test_unshare_success_returns_none(self, mock_libc: MagicMock) -> None:
        from docklet.namespaces import unshare

        mock_libc.unshare.return_value = 0
        result = unshare(CLONE_NEWNS)
        assert result is None

    @patch("docklet.namespaces._libc")
    @patch("ctypes.get_errno", return_value=1)
    def test_unshare_failure_raises_oserror(
        self, mock_get_errno: MagicMock, mock_libc: MagicMock
    ) -> None:
        from docklet.namespaces import unshare

        mock_libc.unshare.return_value = -1
        try:
            unshare(CLONE_NEWNS)
            raise AssertionError("Expected OSError")  # noqa: TRY301
        except OSError as exc:
            assert exc.errno == 1

    @patch("docklet.namespaces._libc")
    def test_unshare_single_flag(self, mock_libc: MagicMock) -> None:
        from docklet.namespaces import unshare

        mock_libc.unshare.return_value = 0
        unshare(CLONE_NEWPID)
        mock_libc.unshare.assert_called_once_with(CLONE_NEWPID)


class TestSetns:
    """Tests for setns() — enter an existing namespace by file descriptor."""

    @patch("docklet.namespaces._libc")
    def test_setns_calls_libc_with_fd_and_nstype(self, mock_libc: MagicMock) -> None:
        from docklet.namespaces import setns

        mock_libc.setns.return_value = 0
        setns(fd=5, nstype=CLONE_NEWNS)
        mock_libc.setns.assert_called_once_with(5, CLONE_NEWNS)

    @patch("docklet.namespaces._libc")
    def test_setns_success_returns_none(self, mock_libc: MagicMock) -> None:
        from docklet.namespaces import setns

        mock_libc.setns.return_value = 0
        result = setns(fd=3, nstype=0)
        assert result is None

    @patch("docklet.namespaces._libc")
    @patch("ctypes.get_errno", return_value=22)
    def test_setns_failure_raises_oserror(
        self, mock_get_errno: MagicMock, mock_libc: MagicMock
    ) -> None:
        from docklet.namespaces import setns

        mock_libc.setns.return_value = -1
        try:
            setns(fd=5, nstype=CLONE_NEWNS)
            raise AssertionError("Expected OSError")  # noqa: TRY301
        except OSError as exc:
            assert exc.errno == 22


class TestSethostname:
    """Tests for sethostname() — sets hostname inside UTS namespace."""

    @patch("docklet.namespaces._libc")
    def test_sethostname_calls_libc(self, mock_libc: MagicMock) -> None:
        from docklet.namespaces import sethostname

        mock_libc.sethostname.return_value = 0
        sethostname("mycontainer")
        mock_libc.sethostname.assert_called_once()
        args = mock_libc.sethostname.call_args[0]
        assert args[1] == len("mycontainer")

    @patch("docklet.namespaces._libc")
    def test_sethostname_success_returns_none(self, mock_libc: MagicMock) -> None:
        from docklet.namespaces import sethostname

        mock_libc.sethostname.return_value = 0
        result = sethostname("test")
        assert result is None

    @patch("docklet.namespaces._libc")
    @patch("ctypes.get_errno", return_value=1)
    def test_sethostname_failure_raises_oserror(
        self, mock_get_errno: MagicMock, mock_libc: MagicMock
    ) -> None:
        from docklet.namespaces import sethostname

        mock_libc.sethostname.return_value = -1
        try:
            sethostname("fail")
            raise AssertionError("Expected OSError")  # noqa: TRY301
        except OSError as exc:
            assert exc.errno == 1

    @patch("docklet.namespaces._libc")
    def test_sethostname_encodes_name_as_bytes(self, mock_libc: MagicMock) -> None:
        from docklet.namespaces import sethostname

        mock_libc.sethostname.return_value = 0
        sethostname("host123")
        args = mock_libc.sethostname.call_args[0]
        # First arg should be bytes, second is length
        assert isinstance(args[0], bytes)
        assert args[0] == b"host123"
        assert args[1] == 7
