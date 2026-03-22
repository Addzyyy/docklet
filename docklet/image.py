"""Local image store — list, get layers, remove images, extract layers.

Manages the on-disk image and layer directories created by the registry module.
Handles OCI whiteout files during layer extraction.
"""

from __future__ import annotations

import json
import os
import shutil
import tarfile
from pathlib import Path
from typing import Any

from docklet.config import IMAGES_DIR


def list_images() -> list[dict[str, Any]]:
    """Scan IMAGES_DIR and return metadata for all pulled images.

    Returns a list of dicts with keys: name, tag, size, layers.
    """
    results: list[dict[str, Any]] = []
    if not IMAGES_DIR.exists():
        return results

    for image_dir in sorted(IMAGES_DIR.iterdir()):
        if not image_dir.is_dir():
            continue
        image_name = image_dir.name
        for tag_dir in sorted(image_dir.iterdir()):
            if not tag_dir.is_dir():
                continue
            tag = tag_dir.name
            layers = get_layers(image_name, tag)
            total_size = _compute_size(layers)
            results.append({
                "name": image_name,
                "tag": tag,
                "size": total_size,
                "layers": layers,
            })

    return results


def get_layers(image: str, tag: str) -> list[str]:
    """Return the ordered list of layer directory paths for a pulled image."""
    layers_file = IMAGES_DIR / image / tag / "layers.json"
    if not layers_file.exists():
        return []
    layers: list[str] = json.loads(layers_file.read_text())
    return layers


def remove_image(image: str, tag: str) -> None:
    """Delete the image directory tree and its associated layers."""
    image_tag_dir = IMAGES_DIR / image / tag

    # Read layers before deleting so we can clean up layer dirs
    layers = get_layers(image, tag)

    # Remove the image metadata
    if image_tag_dir.exists():
        shutil.rmtree(image_tag_dir)

    # Remove parent image dir if now empty
    image_dir = IMAGES_DIR / image
    if image_dir.exists() and not any(image_dir.iterdir()):
        image_dir.rmdir()

    # Clean up layer directories and tarballs
    for layer_dir in layers:
        layer_path = Path(layer_dir)
        if layer_path.exists():
            shutil.rmtree(layer_path)
        tarball = Path(f"{layer_dir}.tar.gz")
        if tarball.exists():
            tarball.unlink()


def extract_layer(tarball_path: str, dest_dir: str) -> None:
    """Extract a .tar.gz layer, handling OCI whiteout files.

    Whiteout files (.wh. prefix) indicate that a file from a lower layer
    should be hidden. When encountered, the corresponding file is deleted
    from dest_dir instead of being extracted.
    """
    with tarfile.open(tarball_path, "r:gz") as tar:
        for member in tar.getmembers():
            basename = os.path.basename(member.name)
            dirname = os.path.dirname(member.name)

            if basename.startswith(".wh."):
                # Whiteout: delete the corresponding file from dest
                target_name = basename[4:]  # strip ".wh." prefix
                if target_name == ".wh..opq":
                    # Opaque whiteout — clear the entire directory
                    opaque_dir = os.path.join(dest_dir, dirname)
                    if os.path.exists(opaque_dir):
                        for entry in os.listdir(opaque_dir):
                            entry_path = os.path.join(opaque_dir, entry)
                            if os.path.isdir(entry_path):
                                shutil.rmtree(entry_path)
                            else:
                                os.unlink(entry_path)
                else:
                    target_path = os.path.join(dest_dir, dirname, target_name)
                    if os.path.isdir(target_path):
                        shutil.rmtree(target_path)
                    elif os.path.exists(target_path):
                        os.unlink(target_path)
            else:
                # Normal file — extract it
                tar.extract(member, dest_dir, filter="data")


def _compute_size(layer_dirs: list[str]) -> int:
    """Compute total size in bytes across all layer directories."""
    total = 0
    for layer_dir in layer_dirs:
        path = Path(layer_dir)
        if path.exists():
            for f in path.rglob("*"):
                if f.is_file():
                    total += f.stat().st_size
    return total
