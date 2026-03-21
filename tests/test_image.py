"""Tests for docklet.image — local image store."""

import json
import os
import tarfile
from pathlib import Path

from docklet.image import extract_layer, get_layers, list_images, remove_image


def _create_fake_image(base: str, image: str, tag: str, num_layers: int = 2) -> str:
    """Create a fake pulled image directory structure."""
    image_dir = os.path.join(base, image, tag)
    os.makedirs(image_dir, exist_ok=True)
    for i in range(num_layers):
        layer_dir = os.path.join(image_dir, f"layer_{i}")
        os.makedirs(layer_dir, exist_ok=True)
        # Put a file in each layer
        with open(os.path.join(layer_dir, f"file_{i}.txt"), "w") as f:
            f.write(f"layer {i} content")
    # Write a manifest
    manifest = {"layers": [{"digest": f"sha256:fake{i}"} for i in range(num_layers)]}
    with open(os.path.join(image_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f)
    return image_dir


def test_list_images_empty(tmp_path: Path) -> None:
    result = list_images(str(tmp_path))
    assert result == []


def test_list_images_finds_images(tmp_path: Path) -> None:
    _create_fake_image(str(tmp_path), "library_alpine", "latest", 3)
    _create_fake_image(str(tmp_path), "library_ubuntu", "22.04", 5)
    result = list_images(str(tmp_path))
    assert len(result) == 2
    names = {img["name"] for img in result}
    assert "library_alpine" in names
    assert "library_ubuntu" in names


def test_list_images_includes_layer_count(tmp_path: Path) -> None:
    _create_fake_image(str(tmp_path), "library_alpine", "latest", 3)
    result = list_images(str(tmp_path))
    assert result[0]["layers"] == 3


def test_get_layers_returns_ordered_paths(tmp_path: Path) -> None:
    _create_fake_image(str(tmp_path), "library_alpine", "latest", 3)
    layers = get_layers("library_alpine", "latest", str(tmp_path))
    assert len(layers) == 3
    for i, layer_path in enumerate(layers):
        assert layer_path.endswith(f"layer_{i}")
        assert os.path.isdir(layer_path)


def test_remove_image(tmp_path: Path) -> None:
    _create_fake_image(str(tmp_path), "library_alpine", "latest")
    image_dir = os.path.join(str(tmp_path), "library_alpine", "latest")
    assert os.path.isdir(image_dir)
    remove_image("library_alpine", "latest", str(tmp_path))
    assert not os.path.isdir(image_dir)


def test_extract_layer_basic(tmp_path: Path) -> None:
    # Create a tarball with some files
    tar_path = str(tmp_path / "layer.tar.gz")
    dest_dir = str(tmp_path / "extracted")
    os.makedirs(dest_dir)

    with tarfile.open(tar_path, "w:gz") as tar:
        import io

        data = b"hello from layer"
        info = tarfile.TarInfo(name="hello.txt")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))

    extract_layer(tar_path, dest_dir)
    assert os.path.isfile(os.path.join(dest_dir, "hello.txt"))
    with open(os.path.join(dest_dir, "hello.txt"), "rb") as f:
        assert f.read() == b"hello from layer"


def test_extract_layer_handles_whiteout(tmp_path: Path) -> None:
    # Create a tarball with a whiteout file
    tar_path = str(tmp_path / "layer.tar.gz")
    dest_dir = str(tmp_path / "extracted")
    os.makedirs(dest_dir)

    # Pre-create a file that the whiteout should delete
    os.makedirs(os.path.join(dest_dir, "etc"), exist_ok=True)
    with open(os.path.join(dest_dir, "etc", "shadow"), "w") as f:
        f.write("should be deleted")

    with tarfile.open(tar_path, "w:gz") as tar:
        import io

        info = tarfile.TarInfo(name="etc/.wh.shadow")
        info.size = 0
        tar.addfile(info, io.BytesIO(b""))

    extract_layer(tar_path, dest_dir)
    # The whiteout target should be removed
    assert not os.path.exists(os.path.join(dest_dir, "etc", "shadow"))
    # The whiteout file itself should not be present
    assert not os.path.exists(os.path.join(dest_dir, "etc", ".wh.shadow"))
