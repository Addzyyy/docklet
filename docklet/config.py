"""Paths, constants, and syscall numbers for docklet.

All configuration lives here — single source of truth.
Syscall numbers are for x86-64 Linux.
"""

import os

# ---------------------------------------------------------------------------
# Filesystem paths
# ---------------------------------------------------------------------------
DOCKLET_ROOT: str = "/var/lib/docklet"
CONTAINERS_DIR: str = f"{DOCKLET_ROOT}/containers"
IMAGES_DIR: str = f"{DOCKLET_ROOT}/images"
LAYERS_DIR: str = f"{DOCKLET_ROOT}/layers"

# ---------------------------------------------------------------------------
# cgroups v2
# ---------------------------------------------------------------------------
CGROUP_ROOT: str = "/sys/fs/cgroup/docklet"

# ---------------------------------------------------------------------------
# Networking
# ---------------------------------------------------------------------------
NETWORK_BRIDGE: str = "docklet0"
SUBNET: str = "10.0.100.0/24"
BRIDGE_IP: str = "10.0.100.1"

# ---------------------------------------------------------------------------
# Namespace clone flags
# ---------------------------------------------------------------------------
CLONE_NEWNS: int = 0x00020000
CLONE_NEWUTS: int = 0x04000000
CLONE_NEWIPC: int = 0x08000000
CLONE_NEWUSER: int = 0x10000000
CLONE_NEWPID: int = 0x20000000
CLONE_NEWNET: int = 0x40000000

# ---------------------------------------------------------------------------
# Syscall numbers (x86-64)
# ---------------------------------------------------------------------------
SYS_pivot_root: int = 155
SYS_mount: int = 165
SYS_umount2: int = 166

# ---------------------------------------------------------------------------
# Mount flags
# ---------------------------------------------------------------------------
MS_NOSUID: int = 2
MS_NODEV: int = 4
MS_NOEXEC: int = 8
MS_PRIVATE: int = 1 << 18  # 262144
MS_REC: int = 1 << 14  # 16384
MNT_DETACH: int = 2


def ensure_dirs() -> None:
    """Create docklet data directories if they don't exist."""
    for d in (CONTAINERS_DIR, IMAGES_DIR, LAYERS_DIR):
        os.makedirs(d, exist_ok=True)
