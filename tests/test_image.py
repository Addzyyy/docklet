"""Tests for docklet.image — local image store management."""

from __future__ import annotations

import io
import json
import os
import tarfile
from pathlib import Path
from unittest.mock import patch


class TestExtractLayer:
    """extract_layer extracts .tar.gz layers with OCI whiteout handling."""

    def _make_targz(self, tmp_path: Path, members: dict[str, bytes]) -> str:
        """Helper: create a .tar.gz with given filename->content mappings."""
        tarball_path = str(tmp_path / "layer.tar.gz")
        with tarfile.open(tarball_path, "w:gz") as tar:
            for name, content in members.items():
                info = tarfile.TarInfo(name=name)
                info.size = len(content)
                tar.addfile(info, io.BytesIO(content))
        return tarball_path

    def test_extracts_basic_files(self, tmp_path: Path) -> None:
        from docklet.image import extract_layer

        tarball = self._make_targz(tmp_path, {
            "hello.txt": b"hello world",
            "subdir/nested.txt": b"nested content",
        })
        dest = str(tmp_path / "dest")
        os.makedirs(dest)

        extract_layer(tarball, dest)

        assert (Path(dest) / "hello.txt").read_text() == "hello world"
        assert (Path(dest) / "subdir" / "nested.txt").read_text() == "nested content"

    def test_handles_whiteout_file(self, tmp_path: Path) -> None:
        from docklet.image import extract_layer

        dest = str(tmp_path / "dest")
        os.makedirs(dest)
        # Pre-create a file that the whiteout should delete
        target = Path(dest) / "remove_me.txt"
        target.write_text("should be deleted")

        tarball = self._make_targz(tmp_path, {
            ".wh.remove_me.txt": b"",
        })

        extract_layer(tarball, dest)

        assert not target.exists()

    def test_handles_whiteout_directory(self, tmp_path: Path) -> None:
        from docklet.image import extract_layer

        dest = str(tmp_path / "dest")
        os.makedirs(dest)
        # Pre-create a directory that the whiteout should delete
        target_dir = Path(dest) / "remove_dir"
        target_dir.mkdir()
        (target_dir / "file.txt").write_text("inside dir")

        tarball = self._make_targz(tmp_path, {
            ".wh.remove_dir": b"",
        })

        extract_layer(tarball, dest)

        assert not target_dir.exists()

    def test_handles_opaque_whiteout(self, tmp_path: Path) -> None:
        from docklet.image import extract_layer

        dest = str(tmp_path / "dest")
        subdir = Path(dest) / "mydir"
        subdir.mkdir(parents=True)
        (subdir / "old_file.txt").write_text("old")
        (subdir / "another.txt").write_text("another")

        tarball = self._make_targz(tmp_path, {
            "mydir/.wh..wh..opq": b"",
        })

        extract_layer(tarball, dest)

        # Directory itself should still exist but be empty
        assert subdir.exists()
        assert list(subdir.iterdir()) == []

    def test_nonexistent_whiteout_target_is_noop(self, tmp_path: Path) -> None:
        """Whiteout for a file that doesn't exist should not raise."""
        from docklet.image import extract_layer

        dest = str(tmp_path / "dest")
        os.makedirs(dest)

        tarball = self._make_targz(tmp_path, {
            ".wh.nonexistent.txt": b"",
        })

        # Should not raise
        extract_layer(tarball, dest)


class TestListImages:
    """list_images scans IMAGES_DIR and returns metadata."""

    def test_empty_when_no_images_dir(self, tmp_path: Path) -> None:
        from docklet.image import list_images

        fake_dir = tmp_path / "images"
        # Don't create it — it doesn't exist

        with patch("docklet.image.IMAGES_DIR", fake_dir):
            result = list_images()

        assert result == []

    def test_returns_image_metadata(self, tmp_path: Path) -> None:
        from docklet.image import list_images

        images_dir = tmp_path / "images"
        tag_dir = images_dir / "alpine" / "latest"
        tag_dir.mkdir(parents=True)

        layers_dir = tmp_path / "layers"
        layer_path = layers_dir / "sha256_abc"
        layer_path.mkdir(parents=True)
        (layer_path / "bin").mkdir()
        (layer_path / "bin" / "sh").write_bytes(b"x" * 100)

        layer_dirs = [str(layer_path)]
        (tag_dir / "layers.json").write_text(json.dumps(layer_dirs))
        (tag_dir / "manifest.json").write_text("{}")

        with patch("docklet.image.IMAGES_DIR", images_dir):
            result = list_images()

        assert len(result) == 1
        assert result[0]["name"] == "alpine"
        assert result[0]["tag"] == "latest"
        assert result[0]["size"] == 100
        assert result[0]["layers"] == layer_dirs

    def test_lists_multiple_images_and_tags(self, tmp_path: Path) -> None:
        from docklet.image import list_images

        images_dir = tmp_path / "images"

        for name, tag in [("alpine", "latest"), ("alpine", "3.18"), ("nginx", "1.25")]:
            tag_dir = images_dir / name / tag
            tag_dir.mkdir(parents=True)
            (tag_dir / "layers.json").write_text("[]")

        with patch("docklet.image.IMAGES_DIR", images_dir):
            result = list_images()

        names_tags = [(r["name"], r["tag"]) for r in result]
        assert ("alpine", "3.18") in names_tags
        assert ("alpine", "latest") in names_tags
        assert ("nginx", "1.25") in names_tags
        assert len(result) == 3


class TestGetLayers:
    """get_layers returns ordered layer paths for a pulled image."""

    def test_returns_layer_list(self, tmp_path: Path) -> None:
        from docklet.image import get_layers

        images_dir = tmp_path / "images"
        tag_dir = images_dir / "alpine" / "latest"
        tag_dir.mkdir(parents=True)

        expected = ["/var/lib/docklet/layers/sha256_aaa", "/var/lib/docklet/layers/sha256_bbb"]
        (tag_dir / "layers.json").write_text(json.dumps(expected))

        with patch("docklet.image.IMAGES_DIR", images_dir):
            result = get_layers("alpine", "latest")

        assert result == expected

    def test_returns_empty_for_missing_image(self, tmp_path: Path) -> None:
        from docklet.image import get_layers

        images_dir = tmp_path / "images"

        with patch("docklet.image.IMAGES_DIR", images_dir):
            result = get_layers("nonexistent", "latest")

        assert result == []


class TestRemoveImage:
    """remove_image deletes the image directory tree and associated layers."""

    def test_removes_image_and_layers(self, tmp_path: Path) -> None:
        from docklet.image import remove_image

        images_dir = tmp_path / "images"
        tag_dir = images_dir / "alpine" / "latest"
        tag_dir.mkdir(parents=True)

        layers_dir = tmp_path / "layers"
        layer1 = layers_dir / "sha256_aaa"
        layer1.mkdir(parents=True)
        (layer1 / "file.txt").write_text("content")
        tarball1 = layers_dir / "sha256_aaa.tar.gz"
        tarball1.write_bytes(b"fake")

        layer_dirs = [str(layer1)]
        (tag_dir / "layers.json").write_text(json.dumps(layer_dirs))
        (tag_dir / "manifest.json").write_text("{}")

        with patch("docklet.image.IMAGES_DIR", images_dir):
            remove_image("alpine", "latest")

        assert not tag_dir.exists()
        assert not layer1.exists()
        assert not tarball1.exists()
        # Parent "alpine" dir should be removed since it's empty
        assert not (images_dir / "alpine").exists()

    def test_preserves_other_tags(self, tmp_path: Path) -> None:
        from docklet.image import remove_image

        images_dir = tmp_path / "images"

        tag1 = images_dir / "alpine" / "latest"
        tag1.mkdir(parents=True)
        (tag1 / "layers.json").write_text("[]")

        tag2 = images_dir / "alpine" / "3.18"
        tag2.mkdir(parents=True)
        (tag2 / "layers.json").write_text("[]")

        with patch("docklet.image.IMAGES_DIR", images_dir):
            remove_image("alpine", "latest")

        assert not tag1.exists()
        assert tag2.exists()
        # Parent "alpine" dir should still exist (has another tag)
        assert (images_dir / "alpine").exists()

    def test_noop_for_missing_image(self, tmp_path: Path) -> None:
        """Removing a nonexistent image should not raise."""
        from docklet.image import remove_image

        images_dir = tmp_path / "images"
        images_dir.mkdir()

        with patch("docklet.image.IMAGES_DIR", images_dir):
            remove_image("nonexistent", "latest")  # should not raise
