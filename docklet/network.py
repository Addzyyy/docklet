"""Container networking: bridge setup, veth pairs, IP allocation, and cleanup.

Uses subprocess.run(["ip", ...]) for all network configuration.
No external dependencies — stdlib only.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from docklet.config import BRIDGE_IP, CONTAINERS_DIR, NETWORK_BRIDGE, SUBNET


def setup_bridge() -> None:
    """Create the network bridge with IP, enable forwarding, and add NAT rule.

    Creates bridge ``docklet0`` with IP ``10.0.100.1/24`` if it doesn't already
    exist.  Enables IP forwarding and adds an iptables MASQUERADE rule for
    outbound NAT.
    """
    # Check whether the bridge already exists
    try:
        subprocess.run(
            ["ip", "link", "show", NETWORK_BRIDGE],
            check=True,
        )
    except subprocess.CalledProcessError:
        # Bridge doesn't exist — create it
        subnet_prefix = SUBNET.split("/")[1]
        subprocess.run(
            ["ip", "link", "add", NETWORK_BRIDGE, "type", "bridge"],
            check=True,
        )
        subprocess.run(
            ["ip", "addr", "add", f"{BRIDGE_IP}/{subnet_prefix}", "dev", NETWORK_BRIDGE],
            check=True,
        )
        subprocess.run(
            ["ip", "link", "set", NETWORK_BRIDGE, "up"],
            check=True,
        )

    # Enable IP forwarding
    with open("/proc/sys/net/ipv4/ip_forward", "w") as f:
        f.write("1")

    # Add iptables MASQUERADE rule for outbound NAT
    subprocess.run(
        [
            "iptables",
            "-t", "nat",
            "-A", "POSTROUTING",
            "-s", SUBNET,
            "-j", "MASQUERADE",
        ],
        check=True,
    )


def _allocate_ip(container_id: str) -> str:
    """Pick the next available IP address in the subnet.

    Scans existing container config.json files in ``CONTAINERS_DIR`` to find
    IPs already in use, then returns the lowest available address starting
    from .2 (since .1 is the bridge, .0 is the network address).
    """
    used_ips: set[str] = set()

    if CONTAINERS_DIR.is_dir():
        for entry in CONTAINERS_DIR.iterdir():
            config_path: Path = entry / "config.json"
            if not config_path.is_file():
                continue
            try:
                data: dict[str, object] = json.loads(config_path.read_text())
                ip = data.get("ip")
                if isinstance(ip, str):
                    used_ips.add(ip)
            except (json.JSONDecodeError, OSError):
                continue

    # Derive base from BRIDGE_IP (e.g. "10.0.100.1" -> "10.0.100.")
    base = BRIDGE_IP.rsplit(".", maxsplit=1)[0] + "."

    # Allocate starting from .2
    for host in range(2, 255):
        candidate = f"{base}{host}"
        if candidate not in used_ips:
            return candidate

    msg = "No available IP addresses in subnet"
    raise RuntimeError(msg)


def setup_container_net(container_id: str, pid: int) -> str:
    """Create veth pair and configure networking for a container.

    1. Creates a veth pair: ``veth-{id[:7]}`` (host) and ``eth0`` (container).
    2. Attaches host end to the bridge.
    3. Moves container end into the container's network namespace.
    4. Assigns an IP from the subnet.
    5. Sets a default route inside the container pointing to the bridge IP.
    6. Returns the assigned IP address.
    """
    veth_host = f"veth-{container_id[:7]}"
    ip = _allocate_ip(container_id)
    subnet_prefix = SUBNET.split("/")[1]

    # 1. Create veth pair
    subprocess.run(
        ["ip", "link", "add", veth_host, "type", "veth", "peer", "name", "eth0"],
        check=True,
    )

    # 2. Attach host end to bridge
    subprocess.run(
        ["ip", "link", "set", veth_host, "master", NETWORK_BRIDGE],
        check=True,
    )

    # 3. Bring host end up
    subprocess.run(
        ["ip", "link", "set", veth_host, "up"],
        check=True,
    )

    # 4. Move container end into container's network namespace
    subprocess.run(
        ["ip", "link", "set", "eth0", "netns", str(pid)],
        check=True,
    )

    # 5. Assign IP inside container
    subprocess.run(
        [
            "nsenter", f"--net=/proc/{pid}/ns/net",
            "ip", "addr", "add", f"{ip}/{subnet_prefix}", "dev", "eth0",
        ],
        check=True,
    )

    # 6. Bring eth0 up inside container
    subprocess.run(
        [
            "nsenter", f"--net=/proc/{pid}/ns/net",
            "ip", "link", "set", "eth0", "up",
        ],
        check=True,
    )

    # 7. Set default route inside container
    subprocess.run(
        [
            "nsenter", f"--net=/proc/{pid}/ns/net",
            "ip", "route", "add", "default", "via", BRIDGE_IP,
        ],
        check=True,
    )

    return ip


def cleanup_net(container_id: str) -> None:
    """Delete the host-side veth interface, which automatically destroys the pair."""
    veth_host = f"veth-{container_id[:7]}"
    subprocess.run(
        ["ip", "link", "del", veth_host],
        check=True,
    )
