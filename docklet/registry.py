"""Docker Hub registry v2 API client — pulls images using only urllib.

Authenticates with auth.docker.io, fetches manifests from registry-1.docker.io,
downloads layer blobs, and extracts them into the local image store.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from typing import Any

from docklet.config import IMAGES_DIR, LAYERS_DIR
from docklet.image import extract_layer

_AUTH_URL = "https://auth.docker.io/token"
_REGISTRY_URL = "https://registry-1.docker.io/v2"
_MANIFEST_V2_TYPE = "application/vnd.docker.distribution.manifest.v2+json"
_MANIFEST_LIST_TYPE = "application/vnd.docker.distribution.manifest.list.v2+json"


def _normalize_image(image: str) -> str:
    """Expand bare image names like 'alpine' to 'library/alpine'."""
    if "/" not in image:
        return f"library/{image}"
    return image


def _get_auth_token(image: str) -> str:
    """Request a bearer token from auth.docker.io scoped to pull the image."""
    url = f"{_AUTH_URL}?service=registry.docker.io&scope=repository:{image}:pull"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as resp:
        data: dict[str, Any] = json.loads(resp.read())
    token: str = data["token"]
    return token


def _get_manifest(image: str, tag: str, token: str) -> dict[str, Any]:
    """Fetch the image manifest from registry-1.docker.io.

    Handles manifest lists (multi-arch) by selecting the amd64/linux entry.
    """
    url = f"{_REGISTRY_URL}/{image}/manifests/{tag}"
    accept = f"{_MANIFEST_V2_TYPE}, {_MANIFEST_LIST_TYPE}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": accept,
    })
    with urllib.request.urlopen(req) as resp:
        data: dict[str, Any] = json.loads(resp.read())

    # If this is a manifest list, find the amd64/linux entry and fetch that manifest
    media_type = data.get("mediaType", "")
    if media_type == _MANIFEST_LIST_TYPE or "manifests" in data:
        digest = _select_amd64_digest(data)
        return _get_manifest(image, digest, token)

    return data


def _select_amd64_digest(manifest_list: dict[str, Any]) -> str:
    """Select the amd64/linux digest from a manifest list."""
    for entry in manifest_list["manifests"]:
        platform = entry.get("platform", {})
        if platform.get("architecture") == "amd64" and platform.get("os") == "linux":
            digest: str = entry["digest"]
            return digest
    msg = "No amd64/linux manifest found in manifest list"
    raise RuntimeError(msg)


def _pull_layer(image: str, digest: str, token: str, dest: str) -> None:
    """Download a layer blob from the registry and save it to dest.

    Prints progress showing bytes downloaded vs total.
    """
    url = f"{_REGISTRY_URL}/{image}/blobs/{digest}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
    })
    with urllib.request.urlopen(req) as resp:
        total = int(resp.headers.get("Content-Length", 0))
        downloaded = 0
        with open(dest, "wb") as f:
            while True:
                chunk = resp.read(8192)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if total > 0:
                    _print_progress(digest, downloaded, total)

    if total > 0:
        print(flush=True)  # newline after progress


def _print_progress(digest: str, downloaded: int, total: int) -> None:
    """Print download progress to stderr."""
    short_digest = digest[:19] if len(digest) > 19 else digest
    sys.stderr.write(f"\r  {short_digest}: {downloaded}/{total} bytes")
    sys.stderr.flush()


def pull_image(image: str, tag: str = "latest") -> list[str]:
    """Pull an image from Docker Hub.

    Orchestrates: authenticate -> fetch manifest -> download layers -> extract.
    Returns an ordered list of layer directory paths.
    """
    qualified = _normalize_image(image)

    # Step 1: Authenticate
    token = _get_auth_token(qualified)

    # Step 2: Fetch manifest
    manifest = _get_manifest(qualified, tag, token)

    # Step 3: Ensure directories exist
    os.makedirs(LAYERS_DIR, exist_ok=True)
    image_dir = IMAGES_DIR / image / tag
    os.makedirs(image_dir, exist_ok=True)

    # Step 4: Download and extract each layer
    layer_dirs: list[str] = []
    layers: list[dict[str, Any]] = manifest.get("layers", [])

    for layer_info in layers:
        digest: str = layer_info["digest"]
        # Use digest as directory name (replacing : with _)
        layer_id = digest.replace(":", "_")
        tarball_path = str(LAYERS_DIR / f"{layer_id}.tar.gz")
        layer_dir = str(LAYERS_DIR / layer_id)

        # Download the layer blob
        _pull_layer(qualified, digest, token, tarball_path)

        # Extract the layer
        os.makedirs(layer_dir, exist_ok=True)
        extract_layer(tarball_path, layer_dir)

        layer_dirs.append(layer_dir)

    # Step 5: Save manifest metadata
    manifest_path = image_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))

    # Save layer order for get_layers()
    layers_file = image_dir / "layers.json"
    layers_file.write_text(json.dumps(layer_dirs))

    return layer_dirs
