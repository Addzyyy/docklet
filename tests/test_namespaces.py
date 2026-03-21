"""Tests for docklet.namespaces — Linux namespace primitives.

These tests verify the ctypes wrappers are correctly structured.
Actual namespace operations require CAP_SYS_ADMIN so we test the
interface and error handling, not the kernel behavior.
"""

import ctypes
from unittest.mock import MagicMock, patch

import pytest

from docklet.namespaces import (
    NAMESPACE_FILES,
    sethostname,
    setns,
    unshare,
)


def test_namespace_files_maps_all_namespaces() -> None:
    expected = {"pid", "mnt", "uts", "ipc", "net"}
    assert expected.issubset(set(NAMESPACE_FILES.keys()))


def test_namespace_files_point_to_proc() -> None:
    for ns, path_template in NAMESPACE_FILES.items():
        # Should contain a {} placeholder for PID
        assert "{}" in path_template or "%d" in path_template or "pid" in path_template, (
            f"NAMESPACE_FILES[{ns}] should be a path template"
        )


@patch("docklet.namespaces._libc")
def test_unshare_calls_libc(mock_libc: MagicMock) -> None:
    mock_libc.unshare.return_value = 0
    unshare(0x20000000)  # CLONE_NEWPID
    mock_libc.unshare.assert_called_once_with(0x20000000)


@patch("docklet.namespaces._libc")
def test_unshare_raises_on_failure(mock_libc: MagicMock) -> None:
    mock_libc.unshare.return_value = -1
    with patch("ctypes.get_errno", return_value=1):  # EPERM
        with pytest.raises(OSError):
            unshare(0x20000000)


@patch("docklet.namespaces._libc")
def test_setns_calls_libc(mock_libc: MagicMock) -> None:
    mock_libc.setns.return_value = 0
    setns(5, 0)
    mock_libc.setns.assert_called_once_with(5, 0)


@patch("docklet.namespaces._libc")
def test_setns_raises_on_failure(mock_libc: MagicMock) -> None:
    mock_libc.setns.return_value = -1
    with patch("ctypes.get_errno", return_value=1):
        with pytest.raises(OSError):
            setns(5, 0)


@patch("docklet.namespaces._libc")
def test_sethostname_calls_libc(mock_libc: MagicMock) -> None:
    mock_libc.sethostname.return_value = 0
    sethostname("mycontainer")
    args = mock_libc.sethostname.call_args[0]
    assert args[1] == len("mycontainer")
