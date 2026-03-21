"""Paths, constants, and syscall numbers for docklet.

No logic — just data. Single source of truth for all configuration.
"""

from pathlib import Path

# Filesystem paths
DOCKLET_ROOT: Path = Path("/var/lib/docklet")
CONTAINERS_DIR: Path = DOCKLET_ROOT / "containers"
IMAGES_DIR: Path = DOCKLET_ROOT / "images"
LAYERS_DIR: Path = DOCKLET_ROOT / "layers"

# cgroups v2
CGROUP_ROOT: Path = Path("/sys/fs/cgroup/docklet")

# Networking
NETWORK_BRIDGE: str = "docklet0"
SUBNET: str = "10.0.100.0/24"
BRIDGE_IP: str = "10.0.100.1"

# Syscall numbers (x86-64)
SYS_PIVOT_ROOT: int = 155
SYS_MOUNT: int = 165
SYS_UMOUNT2: int = 166
SYS_UNSHARE: int = 272
SYS_SETNS: int = 308

# Namespace clone flags
CLONE_NEWNS: int = 0x00020000
CLONE_NEWUTS: int = 0x04000000
CLONE_NEWIPC: int = 0x08000000
CLONE_NEWUSER: int = 0x10000000
CLONE_NEWPID: int = 0x20000000
CLONE_NEWNET: int = 0x40000000
