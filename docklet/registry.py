"""Docker Hub registry v2 API client.

Pulls images using only urllib from stdlib. No external HTTP libraries.

Flow: authenticate → fetch manifest → download layers → extract.
"""

from __future__ import annotations

import json
import os
import tarfile
import time
from urllib.request import Request, urlopen

from docklet.config import IMAGES_DIR, LAYERS_DIR
from docklet.log import get_logger

log = get_logger("registry")

REGISTRY_BASE = "https://registry-1.docker.io/v2"
AUTH_URL = "https://auth.docker.io/token"
MANIFEST_V2 = "application/vnd.docker.distribution.manifest.v2+json"
MANIFEST_LIST_V2 = "application/vnd.docker.distribution.manifest.list.v2+json"


def _normalize_image(image: str) -> str:
    """Expand bare image names: 'alpine' -> 'library/alpine'."""
    if "/" not in image:
        return f"library/{image}"
    return image


def _get_auth_token(image: str) -> str:
    """Get a bearer token for pulling from Docker Hub."""
    url = f"{AUTH_URL}?service=registry.docker.io&scope=repository:{image}:pull"
    req = Request(url)
    with urlopen(req) as resp:
        data = json.loads(resp.read())
    token: str = data["token"]
    return token


def _get_manifest(image: str, tag: str, token: str) -> dict[str, object]:
    """Fetch the image manifest, handling manifest lists (multi-arch)."""
    url = f"{REGISTRY_BASE}/{image}/manifests/{tag}"
    accept = f"{MANIFEST_V2}, {MANIFEST_LIST_V2}"
    req = Request(url, headers={"Authorization": f"Bearer {token}", "Accept": accept})

    with urlopen(req) as resp:
        manifest: dict[str, object] = json.loads(resp.read())

    # If it's a manifest list, pick the amd64/linux variant and fetch that
    media_type = manifest.get("mediaType", "")
    if media_type == MANIFEST_LIST_V2:
        manifests = manifest.get("manifests", [])
        assert isinstance(manifests, list)
        amd64_digest = None
        for m in manifests:
            assert isinstance(m, dict)
            platform = m.get("platform", {})
            assert isinstance(platform, dict)
            if platform.get("architecture") == "amd64" and platform.get("os") == "linux":
                amd64_digest = m["digest"]
                break

        if amd64_digest is None:
            raise RuntimeError(f"No amd64/linux manifest found for {image}:{tag}")

        # Fetch the actual manifest using the digest
        url = f"{REGISTRY_BASE}/{image}/manifests/{amd64_digest}"
        req = Request(url, headers={"Authorization": f"Bearer {token}", "Accept": MANIFEST_V2})
        with urlopen(req) as resp:
            manifest = json.loads(resp.read())

    return manifest


def _pull_layer(image: str, digest: str, token: str, dest: str) -> None:
    """Download a single layer blob to dest path."""
    url = f"{REGISTRY_BASE}/{image}/blobs/{digest}"
    req = Request(url, headers={"Authorization": f"Bearer {token}"})

    start = time.monotonic()
    with urlopen(req) as resp, open(dest, "wb") as f:
        while True:
            chunk = resp.read(8192)
            if not chunk:
                break
            f.write(chunk)

    duration_ms = int((time.monotonic() - start) * 1000)
    log.info(
        "layer downloaded",
        extra={"image": image, "layer": digest[:19], "duration_ms": duration_ms},
    )


def pull_image(image: str, tag: str = "latest") -> list[str]:
    """Pull an image from Docker Hub. Returns list of extracted layer directories."""
    image = _normalize_image(image)
    log.info("pull started", extra={"image": image, "tag": tag})

    # Ensure directories exist
    os.makedirs(LAYERS_DIR, exist_ok=True)
    image_dir = os.path.join(IMAGES_DIR, image.replace("/", "_"), tag)
    os.makedirs(image_dir, exist_ok=True)

    # Authenticate
    token = _get_auth_token(image)
    log.info("authenticated", extra={"image": image})

    # Get manifest
    manifest = _get_manifest(image, tag, token)
    log.info("manifest fetched", extra={"image": image, "tag": tag})

    # Download and extract each layer
    layers_obj = manifest.get("layers", [])
    assert isinstance(layers_obj, list)
    layer_dirs: list[str] = []

    for i, layer_info in enumerate(layers_obj):
        assert isinstance(layer_info, dict)
        digest = layer_info["digest"]
        assert isinstance(digest, str)

        layer_tarball = os.path.join(LAYERS_DIR, digest.replace(":", "_") + ".tar.gz")
        layer_dir = os.path.join(image_dir, f"layer_{i}")

        if os.path.isdir(layer_dir):
            log.info("layer cached", extra={"image": image, "layer": i})
            layer_dirs.append(layer_dir)
            continue

        # Download
        _pull_layer(image, digest, token, layer_tarball)

        # Extract
        os.makedirs(layer_dir, exist_ok=True)
        with tarfile.open(layer_tarball) as tar:
            tar.extractall(path=layer_dir)
        log.info("layer extracted", extra={"image": image, "layer": i})

        layer_dirs.append(layer_dir)

    # Save manifest for reference
    manifest_path = os.path.join(image_dir, "manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    log.info("pull complete", extra={"image": image, "tag": tag, "layer": len(layer_dirs)})
    return layer_dirs
