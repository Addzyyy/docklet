"""Container lifecycle orchestrator — create, start, stop, remove, exec, list.

Ties together all other docklet modules (namespaces, cgroups, filesystem,
network, image) to manage the full container lifecycle. Uses os.fork()
with a double-fork pattern for PID namespace isolation and pipe-based
synchronization between parent and child processes.
"""

from __future__ import annotations

import contextlib
import datetime
import json
import os
import shutil
import signal
from pathlib import Path
from typing import Any

from docklet import cgroups, filesystem, image, namespaces, network
from docklet.config import (
    CLONE_NEWIPC,
    CLONE_NEWNET,
    CLONE_NEWNS,
    CLONE_NEWPID,
    CLONE_NEWUTS,
    CONTAINERS_DIR,
)

_UNSHARE_FLAGS: int = CLONE_NEWPID | CLONE_NEWNS | CLONE_NEWUTS | CLONE_NEWIPC | CLONE_NEWNET

_MEMORY_SUFFIXES: dict[str, int] = {
    "b": 1,
    "k": 1024,
    "m": 1024 * 1024,
    "g": 1024 * 1024 * 1024,
}


def _parse_memory_limit(limit: str) -> int:
    """Parse a memory limit string like '512m', '1g', '256k' into bytes.

    Raises ValueError if the format is invalid.
    """
    if not limit:
        msg = "Invalid memory limit: empty string"
        raise ValueError(msg)

    suffix = limit[-1].lower()
    if suffix not in _MEMORY_SUFFIXES:
        msg = f"Invalid memory limit: {limit!r}"
        raise ValueError(msg)

    try:
        value = int(limit[:-1])
    except ValueError:
        msg = f"Invalid memory limit: {limit!r}"
        raise ValueError(msg) from None

    return value * _MEMORY_SUFFIXES[suffix]


def _read_config(container_id: str) -> dict[str, Any]:
    """Read a container's config.json and return it as a dict."""
    config_path = CONTAINERS_DIR / container_id / "config.json"
    return json.loads(config_path.read_text())  # type: ignore[no-any-return]


def _write_config(container_id: str, config: dict[str, Any]) -> None:
    """Write a container's config dict to config.json."""
    config_path = CONTAINERS_DIR / container_id / "config.json"
    config_path.write_text(json.dumps(config, indent=2))


def create(
    image_name: str,
    tag: str,
    command: list[str],
    *,
    mem_limit: str | None = None,
    cpu_limit: int | None = None,
) -> str:
    """Create a new container: generate ID, create dir, write config.json.

    Returns the 8-character hex container ID.
    """
    container_id = os.urandom(4).hex()
    container_dir = CONTAINERS_DIR / container_id
    container_dir.mkdir(parents=True, exist_ok=True)

    config: dict[str, Any] = {
        "id": container_id,
        "image": image_name,
        "tag": tag,
        "command": command,
        "pid": None,
        "status": "created",
        "ip": None,
        "created": datetime.datetime.now().isoformat(),
        "mem_limit": mem_limit,
        "cpu_limit": cpu_limit,
    }

    _write_config(container_id, config)
    return container_id


def start(container_id: str) -> None:
    """Start a container using fork + unshare + double-fork pattern.

    Parent side:
      1. Wait for child to unshare (sync via pipe)
      2. Add child PID to cgroup
      3. Setup veth networking
      4. Signal child that network is ready
      5. Write PID + status to config.json
      6. Wait for child

    Child side:
      1. unshare all namespaces
      2. Signal parent that unshare is done
      3. fork again for PID namespace
        Inner child (PID 1 inside container):
          1. Wait for parent's network-ready signal
          2. Mount overlayfs
          3. Mount /proc, /dev inside new root
          4. pivot_root into new rootfs
          5. sethostname
          6. execvp(command)
    """
    config = _read_config(container_id)

    # Create pipes for synchronization:
    # child_ready_pipe: child writes when unshare is done
    # net_ready_pipe: parent writes when network is ready
    child_ready_r, child_ready_w = os.pipe()
    net_ready_r, net_ready_w = os.pipe()

    pid = os.fork()

    if pid > 0:
        # === Parent side ===
        os.close(child_ready_w)
        os.close(net_ready_r)

        # 1. Wait for child to complete unshare
        os.read(child_ready_r, 1)
        os.close(child_ready_r)

        # 2. Setup cgroup
        cgroups.init()
        cgroups.create(container_id)
        cgroups.add_process(container_id, pid)

        if config.get("mem_limit") is not None:
            mem_bytes = _parse_memory_limit(config["mem_limit"])
            cgroups.set_memory_limit(container_id, mem_bytes)

        if config.get("cpu_limit") is not None:
            cgroups.set_cpu_limit(container_id, config["cpu_limit"])

        # 3. Setup networking
        network.setup_bridge()
        ip = network.setup_container_net(container_id, pid)

        # 4. Signal child that network is ready
        os.write(net_ready_w, b"1")
        os.close(net_ready_w)

        # 5. Update config with PID, IP, and status
        config["pid"] = pid
        config["ip"] = ip
        config["status"] = "running"
        _write_config(container_id, config)

        # 6. Wait for child
        os.waitpid(pid, 0)

    else:
        # === Child side ===
        os.close(child_ready_r)
        os.close(net_ready_w)

        # 1. Unshare all namespaces
        namespaces.unshare(_UNSHARE_FLAGS)

        # 2. Signal parent that unshare is done
        os.write(child_ready_w, b"1")
        os.close(child_ready_w)

        # 3. Fork again for PID namespace (child becomes PID 1 inside)
        inner_pid = os.fork()

        if inner_pid > 0:
            # Middle process: wait for inner child, then exit
            os.waitpid(inner_pid, 0)
            os._exit(0)

        # === Inner child (PID 1 inside container) ===

        # 4. Wait for parent's network-ready signal
        os.read(net_ready_r, 1)
        os.close(net_ready_r)

        # 5. Get image layers and mount overlayfs
        layers = image.get_layers(config["image"], config["tag"])
        rootfs = filesystem.setup_overlay(container_id, layers)

        # 6. Mount special filesystems (/proc, /dev/pts, /dev/shm)
        filesystem.mount_special(rootfs)

        # 7. Pivot root into the new rootfs
        filesystem.pivot_root(rootfs)

        # 8. Set hostname
        namespaces.sethostname(container_id[:8])

        # 9. Execute the container command
        cmd = config["command"]
        os.execvp(cmd[0], cmd)


def run(
    image_name: str,
    tag: str,
    command: list[str],
    *,
    mem_limit: str | None = None,
    cpu_limit: int | None = None,
) -> str:
    """Full create-and-start flow. Returns the container ID."""
    container_id = create(
        image_name, tag, command,
        mem_limit=mem_limit, cpu_limit=cpu_limit,
    )
    start(container_id)
    return container_id


def stop(container_id: str) -> None:
    """Stop a running container with SIGTERM, then SIGKILL if needed.

    Updates config.json status to 'stopped'.
    """
    config = _read_config(container_id)
    pid = config.get("pid")

    if config.get("status") != "running" or pid is None:
        return

    # Send SIGTERM
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        # Process already gone
        config["status"] = "stopped"
        _write_config(container_id, config)
        return

    # Wait briefly for graceful shutdown
    try:
        os.waitpid(pid, 0)
    except ChildProcessError:
        # Not a direct child or already reaped — send SIGKILL
        with contextlib.suppress(ProcessLookupError):
            os.kill(pid, signal.SIGKILL)
        with contextlib.suppress(ChildProcessError):
            os.waitpid(pid, 0)

    config["status"] = "stopped"
    _write_config(container_id, config)


def remove(container_id: str) -> None:
    """Remove a container: stop if running, clean up all resources, delete dir."""
    config = _read_config(container_id)

    if config.get("status") == "running":
        stop(container_id)

    # Clean up resources (ignore errors from already-cleaned resources)
    with contextlib.suppress(OSError):
        filesystem.cleanup_overlay(container_id)

    with contextlib.suppress(OSError):
        cgroups.cleanup(container_id)

    with contextlib.suppress(Exception):
        network.cleanup_net(container_id)

    # Remove container directory
    container_dir = CONTAINERS_DIR / container_id
    if container_dir.exists():
        shutil.rmtree(container_dir)


def list_containers() -> list[dict[str, object]]:
    """Read all container configs and check PID liveness.

    Returns a list of config dicts with status updated based on
    whether the container's PID is still alive.
    """
    results: list[dict[str, object]] = []

    if not CONTAINERS_DIR.is_dir():
        return results

    for entry in sorted(CONTAINERS_DIR.iterdir()):
        config_path: Path = entry / "config.json"
        if not config_path.is_file():
            continue

        try:
            config: dict[str, object] = json.loads(config_path.read_text())
        except (json.JSONDecodeError, OSError):
            continue

        # Check if PID is alive for "running" containers
        pid = config.get("pid")
        if config.get("status") == "running" and isinstance(pid, int):
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                config["status"] = "stopped"
            except PermissionError:
                pass  # Process exists but we can't signal it

        results.append(config)

    return results


def exec_in(container_id: str, command: list[str]) -> None:
    """Execute a command inside an existing container's namespaces.

    Opens /proc/<pid>/ns/{pid,mnt,uts,ipc,net}, calls setns() for each,
    then fork() + execvp().
    """
    config = _read_config(container_id)
    pid = config["pid"]

    ns_types = ["pid", "mnt", "uts", "ipc", "net"]
    ns_fds: list[int] = []

    # Open all namespace file descriptors
    for ns in ns_types:
        ns_path = f"/proc/{pid}/ns/{ns}"
        fd = os.open(ns_path, os.O_RDONLY)
        ns_fds.append(fd)

    child_pid = os.fork()

    if child_pid > 0:
        # Parent: close namespace FDs and wait
        for fd in ns_fds:
            os.close(fd)
        os.waitpid(child_pid, 0)
    else:
        # Child: enter all namespaces then exec
        for fd in ns_fds:
            namespaces.setns(fd, 0)
            os.close(fd)

        os.execvp(command[0], command)
