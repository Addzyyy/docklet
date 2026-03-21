# Docklet - Technical Specification

A minimalist Docker clone written in Python for learning container internals.
Uses real Linux primitives (namespaces, cgroups, overlayfs) with zero external dependencies.

---

## Project Structure

```
docklet/
├── pyproject.toml              # Packaging, entry point: "docklet"
├── README.md
├── SPEC.md                     # This file
├── docklet/
│   ├── __init__.py
│   ├── cli.py                  # argparse CLI: run, ps, images, pull, rm, exec
│   ├── container.py            # Container lifecycle orchestrator
│   ├── namespaces.py           # ctypes wrappers for unshare/setns/sethostname
│   ├── cgroups.py              # cgroups v2 resource limits (memory, cpu, pids)
│   ├── filesystem.py           # overlayfs mount + pivot_root
│   ├── network.py              # veth pairs + bridge via ip commands
│   ├── registry.py             # Docker Hub registry v2 API (urllib only)
│   ├── image.py                # Local image store: extract layers, list, remove
│   └── config.py               # Paths, constants, syscall numbers
```

---

## CLI Interface

```
docklet pull IMAGE[:TAG]                        # Pull image from Docker Hub
docklet run [-m MEM] [-c CPU] IMAGE [CMD...]    # Create and start a container
docklet exec CONTAINER CMD...                   # Execute command in running container
docklet ps                                      # List containers
docklet images                                  # List locally pulled images
docklet rm CONTAINER                            # Remove a container
```

Requires root (or equivalent capabilities). The CLI checks `os.geteuid() == 0`
at startup and exits with a clear message if not root.

---

## Module Specifications

### config.py — Paths and Constants

Defines all filesystem paths and syscall constants. No logic, just data.

**Paths:**

| Constant         | Value                          | Purpose                       |
|------------------|--------------------------------|-------------------------------|
| DOCKLET_ROOT     | /var/lib/docklet               | Top-level data directory      |
| CONTAINERS_DIR   | {DOCKLET_ROOT}/containers/     | Per-container state dirs      |
| IMAGES_DIR       | {DOCKLET_ROOT}/images/         | Extracted image layers        |
| LAYERS_DIR       | {DOCKLET_ROOT}/layers/         | Raw downloaded layer tarballs |
| CGROUP_ROOT      | /sys/fs/cgroup/docklet         | Cgroup subtree for docklet    |

**Networking:**

| Constant       | Value           |
|----------------|-----------------|
| NETWORK_BRIDGE | docklet0        |
| SUBNET         | 10.0.100.0/24   |
| BRIDGE_IP      | 10.0.100.1      |

**Syscall numbers (x86-64):**

| Constant        | Value | Purpose                           |
|-----------------|-------|-----------------------------------|
| SYS_pivot_root  | 155   | Switch root filesystem            |
| SYS_mount       | 165   | Mount filesystems                 |
| SYS_umount2     | 166   | Unmount filesystems               |
| SYS_unshare     | 272   | Move process into new namespaces  |
| SYS_setns       | 308   | Enter an existing namespace       |

**Namespace clone flags:**

| Flag           | Value        |
|----------------|--------------|
| CLONE_NEWNS    | 0x00020000   |
| CLONE_NEWUTS   | 0x04000000   |
| CLONE_NEWIPC   | 0x08000000   |
| CLONE_NEWUSER  | 0x10000000   |
| CLONE_NEWPID   | 0x20000000   |
| CLONE_NEWNET   | 0x40000000   |

---

### namespaces.py — Linux Namespace Primitives

Wraps raw syscalls using `ctypes.CDLL("libc.so.6", use_errno=True)`.

**Functions:**

- `unshare(flags: int) -> None`
  Calls `libc.unshare()`. Moves the calling process into new namespaces
  specified by the flags bitmask.

- `setns(fd: int, nstype: int) -> None`
  Calls `libc.setns()`. Enters an existing namespace by file descriptor.
  Used by `docklet exec` to join a running container's namespaces via
  `/proc/<pid>/ns/*` files.

- `sethostname(name: str) -> None`
  Sets the hostname inside the UTS namespace so the container gets its
  own hostname (typically the short container ID).

**Design choice:** Uses `os.fork()` + `unshare()` rather than raw `clone()`.
Python's runtime (GC, thread state) does not survive a raw `clone()` well.
The fork+unshare pattern is standard in Python container code.

---

### cgroups.py — cgroups v2 Resource Limits

All operations are plain file reads/writes to `/sys/fs/cgroup/`. This module
demonstrates that cgroups are fundamentally just a filesystem interface.

**Functions:**

- `init() -> None`
  Creates `/sys/fs/cgroup/docklet/` if needed. Writes `"+cpu +memory +pids"`
  to `cgroup.subtree_control` to enable controllers.

- `create(container_id: str) -> None`
  Creates the cgroup directory at `{CGROUP_ROOT}/{container_id}/`.

- `set_memory_limit(container_id: str, limit_bytes: int) -> None`
  Writes to `memory.max`.

- `set_cpu_limit(container_id: str, quota_us: int = 50000, period_us: int = 100000) -> None`
  Writes `"{quota} {period}"` to `cpu.max`. Default = 50% of one core.

- `set_pids_limit(container_id: str, limit: int) -> None`
  Writes to `pids.max`.

- `add_process(container_id: str, pid: int) -> None`
  Writes PID to `cgroup.procs`.

- `stats(container_id: str) -> dict`
  Reads `memory.current`, `cpu.stat` for reporting in `docklet ps`.

- `cleanup(container_id: str) -> None`
  Removes the cgroup directory after all processes have exited.

---

### filesystem.py — Overlay Filesystem and pivot_root

**Functions:**

- `setup_overlay(container_id: str, image_layers: list[str]) -> str`
  Mounts an overlayfs with:
  - `lowerdir`: colon-separated image layers (bottom to top)
  - `upperdir`: per-container writable layer
  - `workdir`: per-container scratch directory
  - Returns the merged mountpoint path.

- `pivot_root(new_root: str) -> None`
  The pivot_root dance:
  1. Bind-mount `new_root` onto itself (required by pivot_root)
  2. `os.chdir(new_root)`
  3. Call `SYS_pivot_root(".", ".")`
  4. `umount(".", MNT_DETACH)` to detach old root

  Why pivot_root over chroot: chroot is escapable via `fchdir()` on an
  open fd to the old root. pivot_root actually replaces the mount tree.

- `mount_special(rootfs: str) -> None`
  Mounts `/proc` (new instance), `/dev/pts`, `/dev/shm` inside the container
  so tools like `ps` work.

- `cleanup_overlay(container_id: str) -> None`
  Unmounts overlayfs and removes the writable layer.

---

### network.py — Container Networking

Uses `subprocess.run(["ip", ...])` for network configuration. Netlink would
be 200+ lines of binary message construction; `ip` commands are clear and
universally available.

**Functions:**

- `setup_bridge() -> None`
  Creates bridge `docklet0` with IP `10.0.100.1/24` if it doesn't exist.
  Enables IP forwarding (`/proc/sys/net/ipv4/ip_forward`).
  Adds iptables MASQUERADE rule for outbound NAT.

- `setup_container_net(container_id: str, pid: int) -> str`
  1. Creates a veth pair: `veth-{id[:7]}` (host) ↔ `eth0` (container)
  2. Attaches host end to bridge `docklet0`
  3. Moves container end into the container's network namespace
  4. Assigns IP from subnet (sequential from .2)
  5. Sets default route inside container → bridge IP
  6. Returns assigned IP address

- `cleanup_net(container_id: str) -> None`
  Deletes the host-side veth (automatically destroys the pair).

- `_allocate_ip(container_id: str) -> str`
  Reads existing container configs to pick next available IP in the subnet.

---

### registry.py — Docker Hub Image Pulling

Uses only `urllib.request` from stdlib. No external HTTP libraries.

**Functions:**

- `pull_image(image: str, tag: str = "latest") -> list[str]`
  Orchestrator: authenticate → fetch manifest → download layers → extract.
  Returns ordered list of layer directories.

- `_get_auth_token(image: str) -> str`
  Requests a bearer token from `auth.docker.io` scoped to pull the image.

- `_get_manifest(image: str, tag: str, token: str) -> dict`
  Fetches the image manifest from `registry-1.docker.io`.
  Handles manifest lists (multi-arch) by selecting `amd64/linux`.
  Sends `Accept: application/vnd.docker.distribution.manifest.v2+json`.

- `_pull_layer(image: str, digest: str, token: str, dest: str) -> None`
  Downloads a blob with progress output (bytes downloaded / total).
  Saves to `LAYERS_DIR`.

**Image naming:** Bare names like `alpine` are expanded to `library/alpine`.

---

### image.py — Local Image Store

**Functions:**

- `list_images() -> list[dict]`
  Scans `IMAGES_DIR`, returns list of `{name, tag, size, layers}` dicts.

- `get_layers(image: str, tag: str) -> list[str]`
  Returns ordered list of layer directory paths for a pulled image.

- `remove_image(image: str, tag: str) -> None`
  Deletes the image directory tree.

- `extract_layer(tarball_path: str, dest_dir: str) -> None`
  Extracts a `.tar.gz` layer, handling OCI whiteout files (`.wh.` prefix).

---

### container.py — Container Lifecycle

Orchestrates all other modules into a complete container lifecycle.

**Per-container state** stored in `CONTAINERS_DIR/{id}/config.json`:

```json
{
  "id": "a1b2c3d4",
  "image": "alpine",
  "tag": "latest",
  "command": ["/bin/sh"],
  "pid": 12345,
  "status": "running",
  "ip": "10.0.100.2",
  "created": "2026-03-21T12:00:00",
  "mem_limit": "512m",
  "cpu_limit": 50000
}
```

**Functions:**

- `run(image, tag, command, mem_limit, cpu_limit) -> str`
  Full create-and-start flow. Returns container ID.

- `create(image, tag, command, mem_limit, cpu_limit) -> str`
  Generates 8-char hex ID, writes config.json, returns ID.

- `start(container_id: str) -> None`
  The main startup sequence — see "Container Startup Flow" below.

- `exec_in(container_id: str, command: list[str]) -> None`
  Opens `/proc/<pid>/ns/{pid,mnt,uts,ipc,net}`, calls `setns()` for each,
  then `fork()` + `execvp()`.

- `stop(container_id: str) -> None`
  Sends SIGTERM, waits briefly, then SIGKILL.

- `remove(container_id: str) -> None`
  Stops if running, then cleans up filesystem, cgroup, and network.

- `list_containers() -> list[dict]`
  Reads all config.json files, checks if PIDs are alive, returns status info.

---

## Container Startup Flow

```
Parent: os.fork()
  │
  ├─ Parent side:
  │    1. Wait for child to unshare (sync via pipe)
  │    2. Add child PID to cgroup
  │    3. Setup veth networking (move interface into child's netns)
  │    4. Signal child that network is ready (write to pipe)
  │    5. Write PID + status to config.json
  │    6. Wait for child (if interactive)
  │
  └─ Child side:
       1. unshare(CLONE_NEWPID | CLONE_NEWNS | CLONE_NEWUTS | CLONE_NEWIPC | CLONE_NEWNET)
       2. Signal parent that unshare is done
       3. os.fork() again  ← required: PID namespace applies to children
       │
       └─ Inner child (PID 1 inside container):
            1. Wait for parent's "network ready" signal
            2. Mount overlayfs
            3. Mount /proc, /dev inside new root
            4. pivot_root into new rootfs
            5. sethostname(container_id[:8])
            6. os.execvp(command)
```

**Why double fork:** `unshare(CLONE_NEWPID)` does not move the caller into the
new PID namespace — only its future children enter it. The second fork ensures
the container's init process sees itself as PID 1.

---

## Packaging

```toml
[project]
name = "docklet"
version = "0.1.0"
requires-python = ">=3.10"

[project.scripts]
docklet = "docklet.cli:main"
```

- Zero external dependencies — pure stdlib
- Install: `pip install -e .`
- Run: `sudo docklet run alpine /bin/sh`

---

## Build Order

| Phase | Modules                              | Root required? |
|-------|--------------------------------------|----------------|
| 1     | config.py                            | No             |
| 2     | registry.py, image.py                | No             |
| 3     | namespaces.py, cgroups.py, filesystem.py | To test     |
| 4     | network.py                           | To test        |
| 5     | container.py                         | To test        |
| 6     | cli.py, pyproject.toml               | No             |
