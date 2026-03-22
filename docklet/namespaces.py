"""Linux namespace primitives using ctypes syscall wrappers.

Wraps libc functions for creating and entering Linux namespaces.
On error (return -1), raises OSError with the errno from ctypes.get_errno().
"""

import ctypes

_libc = ctypes.CDLL("libc.so.6", use_errno=True)


def unshare(flags: int) -> None:
    """Move the calling process into new namespaces specified by flags bitmask."""
    ret: int = _libc.unshare(flags)
    if ret == -1:
        errno = ctypes.get_errno()
        raise OSError(errno, f"unshare(flags=0x{flags:08x}) failed: errno={errno}")


def setns(fd: int, nstype: int) -> None:
    """Enter an existing namespace by file descriptor."""
    ret: int = _libc.setns(fd, nstype)
    if ret == -1:
        errno = ctypes.get_errno()
        raise OSError(errno, f"setns(fd={fd}, nstype=0x{nstype:08x}) failed: errno={errno}")


def sethostname(name: str) -> None:
    """Set the hostname inside the UTS namespace."""
    name_bytes = name.encode("utf-8")
    ret: int = _libc.sethostname(name_bytes, len(name_bytes))
    if ret == -1:
        errno = ctypes.get_errno()
        raise OSError(errno, f"sethostname(name={name!r}) failed: errno={errno}")
