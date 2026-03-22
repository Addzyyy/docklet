"""Overlay filesystem and pivot_root using ctypes syscall wrappers.

Provides overlayfs mount/unmount, pivot_root dance, and special filesystem
mounts (/proc, /dev/pts, /dev/shm) for container setup.
"""

import ctypes
import os
import shutil

from docklet.config import (
    CONTAINERS_DIR,
    SYS_MOUNT,
    SYS_PIVOT_ROOT,
    SYS_UMOUNT2,
)

_libc = ctypes.CDLL("libc.so.6", use_errno=True)

# Mount flags
_MS_BIND: int = 0x00001000
_MS_NOSUID: int = 0x00000002
_MS_NOEXEC: int = 0x00000008
_MS_NODEV: int = 0x00000004
_MNT_DETACH: int = 0x00000002


def _syscall_mount(
    source: bytes,
    target: bytes,
    fstype: bytes,
    flags: int,
    data: bytes,
) -> None:
    """Call the mount syscall, raising OSError on failure."""
    ret: int = _libc.syscall(
        SYS_MOUNT,
        source,
        target,
        fstype,
        flags,
        data,
    )
    if ret == -1:
        errno = ctypes.get_errno()
        raise OSError(
            errno,
            f"mount(source={source!r}, target={target!r}, "
            f"fstype={fstype!r}) failed: errno={errno}",
        )


def _syscall_umount2(target: bytes, flags: int) -> None:
    """Call the umount2 syscall, raising OSError on failure."""
    ret: int = _libc.syscall(SYS_UMOUNT2, target, flags)
    if ret == -1:
        errno = ctypes.get_errno()
        raise OSError(
            errno, f"umount2(target={target!r}, flags=0x{flags:x}) failed: errno={errno}"
        )


def setup_overlay(container_id: str, image_layers: list[str]) -> str:
    """Mount overlayfs with lowerdir, upperdir, and workdir.

    Args:
        container_id: Unique container identifier.
        image_layers: List of image layer paths (used as lowerdir).

    Returns:
        Path to the merged mountpoint.
    """
    container_dir = CONTAINERS_DIR / container_id
    merged = container_dir / "merged"
    upper = container_dir / "upper"
    work = container_dir / "work"

    merged.mkdir(parents=True, exist_ok=True)
    upper.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)

    lowerdir = ":".join(image_layers)
    options = f"lowerdir={lowerdir},upperdir={upper},workdir={work}"
    merged_str = str(merged)

    _syscall_mount(
        b"overlay",
        merged_str.encode("utf-8"),
        b"overlay",
        0,
        options.encode("utf-8"),
    )

    return merged_str


def pivot_root(new_root: str) -> None:
    """Perform the pivot_root dance.

    Steps:
    1. Bind-mount new_root onto itself.
    2. chdir into new_root.
    3. SYS_pivot_root(".", ".") to swap root.
    4. umount2(".", MNT_DETACH) to detach old root.
    """
    new_root_bytes = new_root.encode("utf-8")

    # Bind-mount new_root onto itself
    _syscall_mount(
        new_root_bytes,
        new_root_bytes,
        b"",
        _MS_BIND,
        b"",
    )

    # chdir into new_root
    os.chdir(new_root)

    # pivot_root(".", ".")
    ret: int = _libc.syscall(SYS_PIVOT_ROOT, b".", b".")
    if ret == -1:
        errno = ctypes.get_errno()
        raise OSError(
            errno, f"pivot_root(new_root={new_root!r}) failed: errno={errno}"
        )

    # Unmount old root with MNT_DETACH
    _syscall_umount2(b".", _MNT_DETACH)


def mount_special(rootfs: str) -> None:
    """Mount /proc, /dev/pts, and /dev/shm inside the container rootfs."""
    mounts: list[tuple[str, str, str, int]] = [
        ("proc", f"{rootfs}/proc", "proc", _MS_NOSUID | _MS_NOEXEC | _MS_NODEV),
        ("devpts", f"{rootfs}/dev/pts", "devpts", _MS_NOSUID | _MS_NOEXEC),
        ("tmpfs", f"{rootfs}/dev/shm", "tmpfs", _MS_NOSUID | _MS_NODEV),
    ]

    for source, target, fstype, flags in mounts:
        os.makedirs(target, exist_ok=True)
        _syscall_mount(
            source.encode("utf-8"),
            target.encode("utf-8"),
            fstype.encode("utf-8"),
            flags,
            b"",
        )


def cleanup_overlay(container_id: str) -> None:
    """Unmount overlayfs and remove the container's writable layer."""
    container_dir = CONTAINERS_DIR / container_id
    merged = container_dir / "merged"

    _syscall_umount2(str(merged).encode("utf-8"), 0)
    shutil.rmtree(container_dir)
