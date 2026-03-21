"""Linux namespace primitives via ctypes.

Wraps unshare(2), setns(2), and sethostname(2) syscalls.
Uses os.fork() + unshare() rather than raw clone() because
Python's runtime (GC, thread state) does not survive clone().
"""

from __future__ import annotations

import ctypes
import ctypes.util
import os
import time

from docklet.log import get_logger

log = get_logger("namespaces")

# Load libc with errno support
_libc_path = ctypes.util.find_library("c")
if _libc_path is None:
    _libc_path = "libc.so.6"
_libc = ctypes.CDLL(_libc_path, use_errno=True)

# Namespace file paths in /proc/<pid>/ns/
NAMESPACE_FILES: dict[str, str] = {
    "pid": "/proc/{}/ns/pid",
    "mnt": "/proc/{}/ns/mnt",
    "uts": "/proc/{}/ns/uts",
    "ipc": "/proc/{}/ns/ipc",
    "net": "/proc/{}/ns/net",
}


def unshare(flags: int) -> None:
    """Move the calling process into new namespaces.

    Args:
        flags: Bitmask of CLONE_NEW* flags from config.
    """
    start = time.monotonic()
    ret = _libc.unshare(flags)
    if ret != 0:
        errno = ctypes.get_errno()
        raise OSError(errno, f"unshare({flags:#x}) failed: {os.strerror(errno)}")
    duration_ms = int((time.monotonic() - start) * 1000)
    log.info("unshare complete", extra={"duration_ms": duration_ms})


def setns(fd: int, nstype: int) -> None:
    """Enter an existing namespace by file descriptor.

    Used by 'docklet exec' to join a running container's namespaces.
    Open /proc/<pid>/ns/<type> and pass the fd here.

    Args:
        fd: File descriptor for the namespace file.
        nstype: Namespace type flag (0 for any).
    """
    ret = _libc.setns(fd, nstype)
    if ret != 0:
        errno = ctypes.get_errno()
        raise OSError(errno, f"setns({fd}, {nstype:#x}) failed: {os.strerror(errno)}")


def sethostname(name: str) -> None:
    """Set the hostname inside a UTS namespace.

    Args:
        name: Hostname to set (typically container ID prefix).
    """
    name_bytes = name.encode()
    ret = _libc.sethostname(name_bytes, len(name_bytes))
    if ret != 0:
        errno = ctypes.get_errno()
        raise OSError(errno, f"sethostname({name!r}) failed: {os.strerror(errno)}")
    log.info("hostname set", extra={"container_id": name})


def enter_namespaces(pid: int) -> None:
    """Enter all namespaces of a running container process.

    Opens each /proc/<pid>/ns/* file and calls setns() to join.

    Args:
        pid: PID of the container's init process.
    """
    for ns_name, path_template in NAMESPACE_FILES.items():
        ns_path = path_template.format(pid)
        fd = os.open(ns_path, os.O_RDONLY)
        try:
            setns(fd, 0)
            log.info("entered namespace", extra={"container_id": str(pid), "layer": ns_name})
        finally:
            os.close(fd)
