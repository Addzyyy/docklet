"""Local image store — list, extract, and remove pulled images."""

from __future__ import annotations

import os
import shutil
import tarfile

from docklet.config import IMAGES_DIR
from docklet.log import get_logger

log = get_logger("image")


def list_images(images_dir: str = IMAGES_DIR) -> list[dict[str, object]]:
    """Scan images directory, return list of {name, tag, size, layers}."""
    results: list[dict[str, object]] = []
    if not os.path.isdir(images_dir):
        return results

    for image_name in sorted(os.listdir(images_dir)):
        image_path = os.path.join(images_dir, image_name)
        if not os.path.isdir(image_path):
            continue
        for tag in sorted(os.listdir(image_path)):
            tag_path = os.path.join(image_path, tag)
            if not os.path.isdir(tag_path):
                continue
            layer_dirs = [
                d
                for d in sorted(os.listdir(tag_path))
                if d.startswith("layer_") and os.path.isdir(os.path.join(tag_path, d))
            ]
            # Calculate total size
            total_size = 0
            for layer_name in layer_dirs:
                layer_path = os.path.join(tag_path, layer_name)
                for dirpath, _dirnames, filenames in os.walk(layer_path):
                    for fname in filenames:
                        total_size += os.path.getsize(os.path.join(dirpath, fname))

            results.append(
                {
                    "name": image_name,
                    "tag": tag,
                    "layers": len(layer_dirs),
                    "size": total_size,
                }
            )
    return results


def get_layers(image: str, tag: str, images_dir: str = IMAGES_DIR) -> list[str]:
    """Return ordered list of layer directory paths for a pulled image."""
    tag_path = os.path.join(images_dir, image, tag)
    if not os.path.isdir(tag_path):
        raise FileNotFoundError(f"Image not found: {image}:{tag}")

    layer_dirs = sorted(
        d
        for d in os.listdir(tag_path)
        if d.startswith("layer_") and os.path.isdir(os.path.join(tag_path, d))
    )
    return [os.path.join(tag_path, d) for d in layer_dirs]


def remove_image(image: str, tag: str, images_dir: str = IMAGES_DIR) -> None:
    """Delete an image's extracted layers."""
    tag_path = os.path.join(images_dir, image, tag)
    if os.path.isdir(tag_path):
        shutil.rmtree(tag_path)
        log.info("image removed", extra={"image": image, "tag": tag})
    # Clean up parent if empty
    image_path = os.path.join(images_dir, image)
    if os.path.isdir(image_path) and not os.listdir(image_path):
        os.rmdir(image_path)


def extract_layer(tarball_path: str, dest_dir: str) -> None:
    """Extract a layer tarball, handling OCI whiteout files (.wh. prefix)."""
    with tarfile.open(tarball_path) as tar:
        for member in tar.getmembers():
            basename = os.path.basename(member.name)

            # Handle whiteout files: .wh.<filename> means delete <filename>
            if basename.startswith(".wh."):
                target_name = basename[4:]  # Strip .wh. prefix
                target_path = os.path.join(dest_dir, os.path.dirname(member.name), target_name)
                if os.path.exists(target_path):
                    if os.path.isdir(target_path):
                        shutil.rmtree(target_path)
                    else:
                        os.remove(target_path)
                continue

            tar.extract(member, dest_dir)
