"""Tests for docklet.cgroups — cgroups v2 resource limits via file I/O."""

from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

from docklet import cgroups


class TestInit:
    """Tests for init() — creates docklet cgroup root and enables controllers."""

    @patch("docklet.cgroups.CGROUP_ROOT", new_callable=lambda: MagicMock(spec=Path))
    def test_init_creates_cgroup_root_directory(self, mock_root: MagicMock) -> None:
        mock_root.exists.return_value = False
        mock_root.__truediv__ = MagicMock(return_value=MagicMock())
        with patch("builtins.open", mock_open()):
            cgroups.init()
        mock_root.mkdir.assert_called_once_with(parents=True, exist_ok=True)

    @patch("docklet.cgroups.CGROUP_ROOT", new_callable=lambda: MagicMock(spec=Path))
    def test_init_writes_subtree_control(self, mock_root: MagicMock) -> None:
        mock_root.exists.return_value = True
        subtree_file = MagicMock()
        mock_root.__truediv__ = MagicMock(return_value=subtree_file)
        m = mock_open()
        with patch("builtins.open", m):
            cgroups.init()
        m.assert_called_once_with(subtree_file, "w")
        m().write.assert_called_once_with("+cpu +memory +pids")


class TestCreate:
    """Tests for create() — creates a per-container cgroup directory."""

    @patch("docklet.cgroups.CGROUP_ROOT", new_callable=lambda: MagicMock(spec=Path))
    def test_create_makes_container_cgroup_dir(self, mock_root: MagicMock) -> None:
        container_dir = MagicMock()
        mock_root.__truediv__ = MagicMock(return_value=container_dir)
        cgroups.create("abc123")
        mock_root.__truediv__.assert_called_once_with("abc123")
        container_dir.mkdir.assert_called_once_with(parents=True, exist_ok=True)


class TestSetMemoryLimit:
    """Tests for set_memory_limit() — writes to memory.max."""

    @patch("docklet.cgroups.CGROUP_ROOT", new_callable=lambda: MagicMock(spec=Path))
    def test_writes_memory_limit(self, mock_root: MagicMock) -> None:
        memory_max_path = MagicMock()
        container_dir = MagicMock()
        container_dir.__truediv__ = MagicMock(return_value=memory_max_path)
        mock_root.__truediv__ = MagicMock(return_value=container_dir)
        m = mock_open()
        with patch("builtins.open", m):
            cgroups.set_memory_limit("abc123", 536870912)
        m.assert_called_once_with(memory_max_path, "w")
        m().write.assert_called_once_with("536870912")


class TestSetCpuLimit:
    """Tests for set_cpu_limit() — writes quota and period to cpu.max."""

    @patch("docklet.cgroups.CGROUP_ROOT", new_callable=lambda: MagicMock(spec=Path))
    def test_writes_cpu_limit_with_defaults(self, mock_root: MagicMock) -> None:
        cpu_max_path = MagicMock()
        container_dir = MagicMock()
        container_dir.__truediv__ = MagicMock(return_value=cpu_max_path)
        mock_root.__truediv__ = MagicMock(return_value=container_dir)
        m = mock_open()
        with patch("builtins.open", m):
            cgroups.set_cpu_limit("abc123")
        m.assert_called_once_with(cpu_max_path, "w")
        m().write.assert_called_once_with("50000 100000")

    @patch("docklet.cgroups.CGROUP_ROOT", new_callable=lambda: MagicMock(spec=Path))
    def test_writes_cpu_limit_with_custom_values(self, mock_root: MagicMock) -> None:
        cpu_max_path = MagicMock()
        container_dir = MagicMock()
        container_dir.__truediv__ = MagicMock(return_value=cpu_max_path)
        mock_root.__truediv__ = MagicMock(return_value=container_dir)
        m = mock_open()
        with patch("builtins.open", m):
            cgroups.set_cpu_limit("abc123", quota_us=25000, period_us=50000)
        m().write.assert_called_once_with("25000 50000")


class TestSetPidsLimit:
    """Tests for set_pids_limit() — writes to pids.max."""

    @patch("docklet.cgroups.CGROUP_ROOT", new_callable=lambda: MagicMock(spec=Path))
    def test_writes_pids_limit(self, mock_root: MagicMock) -> None:
        pids_max_path = MagicMock()
        container_dir = MagicMock()
        container_dir.__truediv__ = MagicMock(return_value=pids_max_path)
        mock_root.__truediv__ = MagicMock(return_value=container_dir)
        m = mock_open()
        with patch("builtins.open", m):
            cgroups.set_pids_limit("abc123", 100)
        m.assert_called_once_with(pids_max_path, "w")
        m().write.assert_called_once_with("100")


class TestAddProcess:
    """Tests for add_process() — writes PID to cgroup.procs."""

    @patch("docklet.cgroups.CGROUP_ROOT", new_callable=lambda: MagicMock(spec=Path))
    def test_writes_pid_to_cgroup_procs(self, mock_root: MagicMock) -> None:
        procs_path = MagicMock()
        container_dir = MagicMock()
        container_dir.__truediv__ = MagicMock(return_value=procs_path)
        mock_root.__truediv__ = MagicMock(return_value=container_dir)
        m = mock_open()
        with patch("builtins.open", m):
            cgroups.add_process("abc123", 42)
        m.assert_called_once_with(procs_path, "w")
        m().write.assert_called_once_with("42")


class TestStats:
    """Tests for stats() — reads memory.current and cpu.stat."""

    @patch("docklet.cgroups.CGROUP_ROOT", new_callable=lambda: MagicMock(spec=Path))
    def test_returns_dict_with_memory_and_cpu(self, mock_root: MagicMock) -> None:
        memory_path = MagicMock()
        cpu_path = MagicMock()
        container_dir = MagicMock()

        def truediv_side_effect(key: str) -> MagicMock:
            if key == "memory.current":
                return memory_path
            if key == "cpu.stat":
                return cpu_path
            return MagicMock()

        container_dir.__truediv__ = MagicMock(side_effect=truediv_side_effect)
        mock_root.__truediv__ = MagicMock(return_value=container_dir)

        memory_data = mock_open(read_data="1048576\n")
        cpu_data = mock_open(read_data="usage_usec 500000\nuser_usec 300000\nsystem_usec 200000\n")

        def open_side_effect(path: MagicMock, mode: str = "r") -> MagicMock:
            if path is memory_path:
                return memory_data()
            if path is cpu_path:
                return cpu_data()
            return mock_open()()

        with patch("builtins.open", side_effect=open_side_effect):
            result = cgroups.stats("abc123")

        assert result["memory_current"] == "1048576"
        assert "usage_usec 500000" in result["cpu_stat"]


class TestCleanup:
    """Tests for cleanup() — removes the container cgroup directory."""

    @patch("docklet.cgroups.CGROUP_ROOT", new_callable=lambda: MagicMock(spec=Path))
    def test_cleanup_removes_cgroup_dir(self, mock_root: MagicMock) -> None:
        container_dir = MagicMock()
        mock_root.__truediv__ = MagicMock(return_value=container_dir)
        cgroups.cleanup("abc123")
        mock_root.__truediv__.assert_called_once_with("abc123")
        container_dir.rmdir.assert_called_once()


class TestCgroupsWithTmpPath:
    """Integration-style tests using tmp_path for real file I/O."""

    def test_init_creates_directory_and_writes_subtree_control(
        self, tmp_path: Path
    ) -> None:
        cgroup_root = tmp_path / "docklet"
        with patch("docklet.cgroups.CGROUP_ROOT", cgroup_root):
            cgroups.init()
        assert cgroup_root.exists()
        subtree = cgroup_root / "cgroup.subtree_control"
        assert subtree.read_text() == "+cpu +memory +pids"

    def test_create_makes_container_dir(self, tmp_path: Path) -> None:
        cgroup_root = tmp_path / "docklet"
        cgroup_root.mkdir()
        with patch("docklet.cgroups.CGROUP_ROOT", cgroup_root):
            cgroups.create("test-container")
        assert (cgroup_root / "test-container").is_dir()

    def test_set_memory_limit_writes_file(self, tmp_path: Path) -> None:
        cgroup_root = tmp_path / "docklet"
        container_dir = cgroup_root / "ctr1"
        container_dir.mkdir(parents=True)
        with patch("docklet.cgroups.CGROUP_ROOT", cgroup_root):
            cgroups.set_memory_limit("ctr1", 268435456)
        assert (container_dir / "memory.max").read_text() == "268435456"

    def test_set_cpu_limit_writes_file(self, tmp_path: Path) -> None:
        cgroup_root = tmp_path / "docklet"
        container_dir = cgroup_root / "ctr1"
        container_dir.mkdir(parents=True)
        with patch("docklet.cgroups.CGROUP_ROOT", cgroup_root):
            cgroups.set_cpu_limit("ctr1", quota_us=30000, period_us=100000)
        assert (container_dir / "cpu.max").read_text() == "30000 100000"

    def test_set_pids_limit_writes_file(self, tmp_path: Path) -> None:
        cgroup_root = tmp_path / "docklet"
        container_dir = cgroup_root / "ctr1"
        container_dir.mkdir(parents=True)
        with patch("docklet.cgroups.CGROUP_ROOT", cgroup_root):
            cgroups.set_pids_limit("ctr1", 50)
        assert (container_dir / "pids.max").read_text() == "50"

    def test_add_process_writes_pid(self, tmp_path: Path) -> None:
        cgroup_root = tmp_path / "docklet"
        container_dir = cgroup_root / "ctr1"
        container_dir.mkdir(parents=True)
        with patch("docklet.cgroups.CGROUP_ROOT", cgroup_root):
            cgroups.add_process("ctr1", 1234)
        assert (container_dir / "cgroup.procs").read_text() == "1234"

    def test_stats_reads_memory_and_cpu(self, tmp_path: Path) -> None:
        cgroup_root = tmp_path / "docklet"
        container_dir = cgroup_root / "ctr1"
        container_dir.mkdir(parents=True)
        (container_dir / "memory.current").write_text("2097152\n")
        (container_dir / "cpu.stat").write_text(
            "usage_usec 1000000\nuser_usec 600000\nsystem_usec 400000\n"
        )
        with patch("docklet.cgroups.CGROUP_ROOT", cgroup_root):
            result = cgroups.stats("ctr1")
        assert result["memory_current"] == "2097152"
        assert "usage_usec 1000000" in result["cpu_stat"]

    def test_cleanup_removes_container_dir(self, tmp_path: Path) -> None:
        cgroup_root = tmp_path / "docklet"
        container_dir = cgroup_root / "ctr1"
        container_dir.mkdir(parents=True)
        with patch("docklet.cgroups.CGROUP_ROOT", cgroup_root):
            cgroups.cleanup("ctr1")
        assert not container_dir.exists()
