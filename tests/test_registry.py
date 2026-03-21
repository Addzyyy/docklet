"""Tests for docklet.registry — Docker Hub registry v2 API client.

These tests use unittest.mock to avoid hitting the real registry.
"""

import json
from unittest.mock import MagicMock, patch

from docklet.registry import (
    _get_auth_token,
    _get_manifest,
    _normalize_image,
    _pull_layer,
)


def test_normalize_image_bare_name() -> None:
    assert _normalize_image("alpine") == "library/alpine"


def test_normalize_image_already_qualified() -> None:
    assert _normalize_image("myuser/myrepo") == "myuser/myrepo"


def test_normalize_image_preserves_nested() -> None:
    assert _normalize_image("ghcr.io/owner/repo") == "ghcr.io/owner/repo"


def _make_urlopen_response(data: bytes, headers: dict[str, str] | None = None) -> MagicMock:
    resp = MagicMock()
    resp.read.return_value = data
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    resp.headers = headers or {}
    resp.getheader = lambda key, default=None: (headers or {}).get(key, default)
    return resp


@patch("docklet.registry.urlopen")
def test_get_auth_token(mock_urlopen: MagicMock) -> None:
    token_response = json.dumps({"token": "test-token-abc"}).encode()
    mock_urlopen.return_value = _make_urlopen_response(token_response)

    token = _get_auth_token("library/alpine")
    assert token == "test-token-abc"

    call_args = mock_urlopen.call_args
    req = call_args[0][0]
    assert "auth.docker.io" in req.full_url
    assert "library/alpine" in req.full_url


@patch("docklet.registry.urlopen")
def test_get_manifest_v2(mock_urlopen: MagicMock) -> None:
    manifest = {
        "schemaVersion": 2,
        "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
        "config": {"digest": "sha256:configdigest", "size": 100},
        "layers": [
            {"digest": "sha256:layer1digest", "size": 1000},
            {"digest": "sha256:layer2digest", "size": 2000},
        ],
    }
    mock_urlopen.return_value = _make_urlopen_response(json.dumps(manifest).encode())

    result = _get_manifest("library/alpine", "latest", "fake-token")
    assert len(result["layers"]) == 2
    assert result["layers"][0]["digest"] == "sha256:layer1digest"


@patch("docklet.registry.urlopen")
def test_get_manifest_list_selects_amd64(mock_urlopen: MagicMock) -> None:
    manifest_list = {
        "schemaVersion": 2,
        "mediaType": "application/vnd.docker.distribution.manifest.list.v2+json",
        "manifests": [
            {
                "digest": "sha256:arm64digest",
                "platform": {"architecture": "arm64", "os": "linux"},
            },
            {
                "digest": "sha256:amd64digest",
                "platform": {"architecture": "amd64", "os": "linux"},
            },
        ],
    }
    actual_manifest = {
        "schemaVersion": 2,
        "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
        "config": {"digest": "sha256:configdigest", "size": 100},
        "layers": [{"digest": "sha256:layer1", "size": 500}],
    }
    mock_urlopen.side_effect = [
        _make_urlopen_response(json.dumps(manifest_list).encode()),
        _make_urlopen_response(json.dumps(actual_manifest).encode()),
    ]

    result = _get_manifest("library/alpine", "latest", "fake-token")
    assert result["layers"][0]["digest"] == "sha256:layer1"

    # Second call should use the amd64 digest
    second_call_req = mock_urlopen.call_args_list[1][0][0]
    assert "sha256:amd64digest" in second_call_req.full_url


@patch("docklet.registry.urlopen")
def test_pull_layer_downloads_to_file(mock_urlopen: MagicMock, tmp_path: object) -> None:
    import pathlib

    dest = pathlib.Path(str(tmp_path)) / "layer.tar.gz"
    layer_data = b"fake-layer-data-contents"

    resp = MagicMock()
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    resp.getheader = lambda key, default=None: (
        str(len(layer_data)) if key == "Content-Length" else default
    )
    # Simulate chunked reading
    resp.read = MagicMock(side_effect=[layer_data, b""])

    mock_urlopen.return_value = resp

    _pull_layer("library/alpine", "sha256:testdigest", "fake-token", str(dest))
    assert dest.exists()
    assert dest.read_bytes() == layer_data
