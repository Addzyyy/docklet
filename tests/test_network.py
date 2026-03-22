"""Tests for docklet.network — bridge setup, veth pairs, IP allocation, and cleanup."""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, call, mock_open, patch

from docklet.network import _allocate_ip, cleanup_net, setup_bridge, setup_container_net


class TestSetupBridge:
    """Tests for setup_bridge(): creates docklet0 bridge, enables forwarding, adds NAT."""

    @patch("docklet.network.subprocess.run")
    @patch("builtins.open", mock_open())
    def test_creates_bridge_when_not_exists(self, mock_run: MagicMock) -> None:
        """Bridge creation should run ip link add when bridge doesn't exist."""
        # First call (ip link show) raises CalledProcessError → bridge doesn't exist
        mock_run.side_effect = [
            subprocess.CalledProcessError(1, "ip"),  # bridge check fails
            MagicMock(),  # ip link add
            MagicMock(),  # ip addr add
            MagicMock(),  # ip link set up
            MagicMock(),  # iptables MASQUERADE
        ]
        setup_bridge()
        # Verify bridge creation commands
        assert mock_run.call_args_list[1] == call(
            ["ip", "link", "add", "docklet0", "type", "bridge"],
            check=True,
        )
        assert mock_run.call_args_list[2] == call(
            ["ip", "addr", "add", "10.0.100.1/24", "dev", "docklet0"],
            check=True,
        )
        assert mock_run.call_args_list[3] == call(
            ["ip", "link", "set", "docklet0", "up"],
            check=True,
        )

    @patch("docklet.network.subprocess.run")
    @patch("builtins.open", mock_open())
    def test_skips_creation_when_bridge_exists(self, mock_run: MagicMock) -> None:
        """If bridge already exists, skip link add/addr/up commands."""
        mock_run.side_effect = [
            MagicMock(),  # bridge check succeeds → exists
            MagicMock(),  # iptables
        ]
        setup_bridge()
        # Should only have 2 calls: the check + iptables
        assert mock_run.call_count == 2

    @patch("docklet.network.subprocess.run")
    def test_enables_ip_forwarding(self, mock_run: MagicMock) -> None:
        """IP forwarding must be enabled by writing '1' to /proc/sys/net/ipv4/ip_forward."""
        mock_run.return_value = MagicMock()  # bridge exists
        m = mock_open()
        with patch("builtins.open", m):
            setup_bridge()
        m.assert_called_once_with("/proc/sys/net/ipv4/ip_forward", "w")
        m().write.assert_called_once_with("1")

    @patch("docklet.network.subprocess.run")
    @patch("builtins.open", mock_open())
    def test_adds_masquerade_rule(self, mock_run: MagicMock) -> None:
        """Should add iptables MASQUERADE rule for the subnet."""
        mock_run.return_value = MagicMock()  # bridge exists
        setup_bridge()
        # Last call should be iptables
        iptables_call = mock_run.call_args_list[-1]
        assert iptables_call == call(
            [
                "iptables",
                "-t", "nat",
                "-A", "POSTROUTING",
                "-s", "10.0.100.0/24",
                "-j", "MASQUERADE",
            ],
            check=True,
        )


class TestAllocateIp:
    """Tests for _allocate_ip(): picks next available IP from subnet."""

    def test_first_container_gets_dot_2(self, tmp_path: Path) -> None:
        """With no existing containers, first IP should be .2."""
        with patch("docklet.network.CONTAINERS_DIR", tmp_path):
            ip = _allocate_ip("abc123")
        assert ip == "10.0.100.2"

    def test_second_container_gets_dot_3(self, tmp_path: Path) -> None:
        """With one existing container using .2, next should be .3."""
        container_dir = tmp_path / "existing"
        container_dir.mkdir()
        config = {"ip": "10.0.100.2"}
        (container_dir / "config.json").write_text(json.dumps(config))

        with patch("docklet.network.CONTAINERS_DIR", tmp_path):
            ip = _allocate_ip("abc456")
        assert ip == "10.0.100.3"

    def test_fills_gap_in_allocation(self, tmp_path: Path) -> None:
        """If .2 is free but .3 is taken, should allocate .2."""
        container_dir = tmp_path / "existing"
        container_dir.mkdir()
        config = {"ip": "10.0.100.3"}
        (container_dir / "config.json").write_text(json.dumps(config))

        with patch("docklet.network.CONTAINERS_DIR", tmp_path):
            ip = _allocate_ip("abc789")
        assert ip == "10.0.100.2"

    def test_skips_multiple_used_ips(self, tmp_path: Path) -> None:
        """With .2 and .3 taken, should allocate .4."""
        for i, name in enumerate(["c1", "c2"], start=2):
            d = tmp_path / name
            d.mkdir()
            (d / "config.json").write_text(json.dumps({"ip": f"10.0.100.{i}"}))

        with patch("docklet.network.CONTAINERS_DIR", tmp_path):
            ip = _allocate_ip("newcontainer")
        assert ip == "10.0.100.4"

    def test_ignores_dirs_without_config(self, tmp_path: Path) -> None:
        """Directories without config.json should be ignored."""
        (tmp_path / "broken").mkdir()
        with patch("docklet.network.CONTAINERS_DIR", tmp_path):
            ip = _allocate_ip("abc123")
        assert ip == "10.0.100.2"

    def test_ignores_configs_without_ip(self, tmp_path: Path) -> None:
        """Config files without 'ip' key should be ignored."""
        d = tmp_path / "noip"
        d.mkdir()
        (d / "config.json").write_text(json.dumps({"name": "test"}))
        with patch("docklet.network.CONTAINERS_DIR", tmp_path):
            ip = _allocate_ip("abc123")
        assert ip == "10.0.100.2"


class TestSetupContainerNet:
    """Tests for setup_container_net(): creates veth pair and configures networking."""

    @patch("docklet.network._allocate_ip", return_value="10.0.100.2")
    @patch("docklet.network.subprocess.run")
    def test_creates_veth_pair(self, mock_run: MagicMock, mock_alloc: MagicMock) -> None:
        """Should create veth pair: veth-{id[:7]} <-> eth0."""
        setup_container_net("abcdef1234567890", pid=42)
        veth_create = mock_run.call_args_list[0]
        assert veth_create == call(
            [
                "ip", "link", "add", "veth-abcdef1",
                "type", "veth",
                "peer", "name", "eth0",
            ],
            check=True,
        )

    @patch("docklet.network._allocate_ip", return_value="10.0.100.2")
    @patch("docklet.network.subprocess.run")
    def test_attaches_host_end_to_bridge(
        self, mock_run: MagicMock, mock_alloc: MagicMock
    ) -> None:
        """Host-side veth should be attached to the bridge."""
        setup_container_net("abcdef1234567890", pid=42)
        attach_call = mock_run.call_args_list[1]
        assert attach_call == call(
            ["ip", "link", "set", "veth-abcdef1", "master", "docklet0"],
            check=True,
        )

    @patch("docklet.network._allocate_ip", return_value="10.0.100.2")
    @patch("docklet.network.subprocess.run")
    def test_brings_host_veth_up(self, mock_run: MagicMock, mock_alloc: MagicMock) -> None:
        """Host-side veth should be brought up."""
        setup_container_net("abcdef1234567890", pid=42)
        up_call = mock_run.call_args_list[2]
        assert up_call == call(
            ["ip", "link", "set", "veth-abcdef1", "up"],
            check=True,
        )

    @patch("docklet.network._allocate_ip", return_value="10.0.100.2")
    @patch("docklet.network.subprocess.run")
    def test_moves_peer_into_container_netns(
        self, mock_run: MagicMock, mock_alloc: MagicMock
    ) -> None:
        """Container-side eth0 should be moved into container's network namespace."""
        setup_container_net("abcdef1234567890", pid=42)
        move_call = mock_run.call_args_list[3]
        assert move_call == call(
            ["ip", "link", "set", "eth0", "netns", "42"],
            check=True,
        )

    @patch("docklet.network._allocate_ip", return_value="10.0.100.2")
    @patch("docklet.network.subprocess.run")
    def test_assigns_ip_inside_container(
        self, mock_run: MagicMock, mock_alloc: MagicMock
    ) -> None:
        """IP address should be assigned to eth0 inside the container namespace."""
        setup_container_net("abcdef1234567890", pid=42)
        ip_call = mock_run.call_args_list[4]
        assert ip_call == call(
            [
                "nsenter", "--net=/proc/42/ns/net",
                "ip", "addr", "add", "10.0.100.2/24", "dev", "eth0",
            ],
            check=True,
        )

    @patch("docklet.network._allocate_ip", return_value="10.0.100.2")
    @patch("docklet.network.subprocess.run")
    def test_brings_eth0_up_inside_container(
        self, mock_run: MagicMock, mock_alloc: MagicMock
    ) -> None:
        """eth0 inside the container should be brought up."""
        setup_container_net("abcdef1234567890", pid=42)
        up_call = mock_run.call_args_list[5]
        assert up_call == call(
            [
                "nsenter", "--net=/proc/42/ns/net",
                "ip", "link", "set", "eth0", "up",
            ],
            check=True,
        )

    @patch("docklet.network._allocate_ip", return_value="10.0.100.2")
    @patch("docklet.network.subprocess.run")
    def test_sets_default_route_inside_container(
        self, mock_run: MagicMock, mock_alloc: MagicMock
    ) -> None:
        """Default route should point to bridge IP inside the container."""
        setup_container_net("abcdef1234567890", pid=42)
        route_call = mock_run.call_args_list[6]
        assert route_call == call(
            [
                "nsenter", "--net=/proc/42/ns/net",
                "ip", "route", "add", "default", "via", "10.0.100.1",
            ],
            check=True,
        )

    @patch("docklet.network._allocate_ip", return_value="10.0.100.5")
    @patch("docklet.network.subprocess.run")
    def test_returns_assigned_ip(self, mock_run: MagicMock, mock_alloc: MagicMock) -> None:
        """Function should return the allocated IP address."""
        ip = setup_container_net("abcdef1234567890", pid=42)
        assert ip == "10.0.100.5"

    @patch("docklet.network._allocate_ip", return_value="10.0.100.2")
    @patch("docklet.network.subprocess.run")
    def test_total_subprocess_calls(self, mock_run: MagicMock, mock_alloc: MagicMock) -> None:
        """Should make exactly 7 subprocess.run calls."""
        setup_container_net("abcdef1234567890", pid=42)
        assert mock_run.call_count == 7


class TestCleanupNet:
    """Tests for cleanup_net(): deletes host-side veth to tear down the pair."""

    @patch("docklet.network.subprocess.run")
    def test_deletes_host_veth(self, mock_run: MagicMock) -> None:
        """Should delete the host-side veth interface."""
        cleanup_net("abcdef1234567890")
        mock_run.assert_called_once_with(
            ["ip", "link", "del", "veth-abcdef1"],
            check=True,
        )

    @patch("docklet.network.subprocess.run")
    def test_uses_first_seven_chars_of_id(self, mock_run: MagicMock) -> None:
        """Veth name should use first 7 characters of container ID."""
        cleanup_net("xyz9876543210")
        mock_run.assert_called_once_with(
            ["ip", "link", "del", "veth-xyz9876"],
            check=True,
        )
