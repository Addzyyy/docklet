"""Tests for docklet.registry — Docker Hub image pulling via urllib."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch


class TestGetAuthToken:
    """_get_auth_token requests a bearer token from auth.docker.io."""

    def test_returns_token_string(self) -> None:
        from docklet.registry import _get_auth_token

        token_response = json.dumps({"token": "abc123"}).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = token_response
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
            result = _get_auth_token("library/alpine")

        assert result == "abc123"
        # Verify it called auth.docker.io with correct scope
        req = mock_urlopen.call_args[0][0]
        assert "auth.docker.io" in req.full_url
        assert "library/alpine" in req.full_url

    def test_expands_bare_image_name(self) -> None:
        from docklet.registry import _get_auth_token

        token_response = json.dumps({"token": "tok456"}).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = token_response
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = _get_auth_token("library/alpine")

        assert result == "tok456"


class TestGetManifest:
    """_get_manifest fetches the image manifest from registry-1.docker.io."""

    def test_returns_manifest_dict(self) -> None:
        from docklet.registry import _get_manifest

        manifest = {
            "schemaVersion": 2,
            "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
            "layers": [
                {"digest": "sha256:aaa", "size": 1000},
            ],
        }
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(manifest).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
            result = _get_manifest("library/alpine", "latest", "token123")

        assert result["schemaVersion"] == 2
        assert len(result["layers"]) == 1
        # Verify it sends the correct Accept header and auth
        req = mock_urlopen.call_args[0][0]
        assert "registry-1.docker.io" in req.full_url
        assert req.get_header("Authorization") == "Bearer token123"

    def test_handles_manifest_list_selects_amd64(self) -> None:
        from docklet.registry import _get_manifest

        manifest_list = {
            "schemaVersion": 2,
            "mediaType": "application/vnd.docker.distribution.manifest.list.v2+json",
            "manifests": [
                {
                    "digest": "sha256:arm",
                    "platform": {"architecture": "arm64", "os": "linux"},
                },
                {
                    "digest": "sha256:amd",
                    "platform": {"architecture": "amd64", "os": "linux"},
                },
            ],
        }
        single_manifest = {
            "schemaVersion": 2,
            "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
            "layers": [{"digest": "sha256:bbb", "size": 2000}],
        }

        resp1 = MagicMock()
        resp1.read.return_value = json.dumps(manifest_list).encode()
        resp1.__enter__ = MagicMock(return_value=resp1)
        resp1.__exit__ = MagicMock(return_value=False)

        resp2 = MagicMock()
        resp2.read.return_value = json.dumps(single_manifest).encode()
        resp2.__enter__ = MagicMock(return_value=resp2)
        resp2.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", side_effect=[resp1, resp2]) as mock_urlopen:
            result = _get_manifest("library/alpine", "latest", "token123")

        assert result["layers"][0]["digest"] == "sha256:bbb"
        # Second call should use the amd64 digest
        second_req = mock_urlopen.call_args_list[1][0][0]
        assert "sha256:amd" in second_req.full_url


class TestPullLayer:
    """_pull_layer downloads a blob and saves it to LAYERS_DIR."""

    def test_downloads_blob_to_dest(self, tmp_path: Path) -> None:
        from docklet.registry import _pull_layer

        blob_data = b"\x1f\x8b" + b"\x00" * 100  # fake gzip data
        mock_resp = MagicMock()
        mock_resp.read.side_effect = [blob_data, b""]
        mock_resp.headers = {"Content-Length": str(len(blob_data))}
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        dest = str(tmp_path / "layer.tar.gz")

        with patch("urllib.request.urlopen", return_value=mock_resp):
            _pull_layer("library/alpine", "sha256:abc123", "token", dest)

        assert os.path.exists(dest)
        with open(dest, "rb") as f:
            assert f.read() == blob_data


class TestPullImage:
    """pull_image orchestrates auth → manifest → download → extract."""

    def test_pull_image_returns_layer_dirs(self, tmp_path: Path) -> None:
        from docklet.registry import pull_image

        layers_dir = tmp_path / "layers"
        layers_dir.mkdir()
        images_dir = tmp_path / "images"
        images_dir.mkdir()

        manifest = {
            "schemaVersion": 2,
            "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
            "layers": [
                {"digest": "sha256:aaa111", "size": 500},
                {"digest": "sha256:bbb222", "size": 600},
            ],
        }

        with (
            patch("docklet.registry._get_auth_token", return_value="tok") as mock_auth,
            patch("docklet.registry._get_manifest", return_value=manifest) as mock_manifest,
            patch("docklet.registry._pull_layer") as mock_pull,
            patch("docklet.registry.extract_layer") as mock_extract,
            patch("docklet.registry.LAYERS_DIR", layers_dir),
            patch("docklet.registry.IMAGES_DIR", images_dir),
        ):
            result = pull_image("alpine", "latest")

        mock_auth.assert_called_once_with("library/alpine")
        mock_manifest.assert_called_once_with("library/alpine", "latest", "tok")
        assert mock_pull.call_count == 2
        assert mock_extract.call_count == 2
        assert len(result) == 2

    def test_expands_bare_name_to_library_prefix(self, tmp_path: Path) -> None:
        from docklet.registry import pull_image

        layers_dir = tmp_path / "layers"
        layers_dir.mkdir()
        images_dir = tmp_path / "images"
        images_dir.mkdir()

        manifest: dict[str, Any] = {
            "schemaVersion": 2,
            "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
            "layers": [],
        }

        with (
            patch("docklet.registry._get_auth_token", return_value="tok") as mock_auth,
            patch("docklet.registry._get_manifest", return_value=manifest),
            patch("docklet.registry.LAYERS_DIR", layers_dir),
            patch("docklet.registry.IMAGES_DIR", images_dir),
        ):
            pull_image("nginx", "1.25")

        mock_auth.assert_called_once_with("library/nginx")

    def test_does_not_expand_qualified_name(self, tmp_path: Path) -> None:
        from docklet.registry import pull_image

        layers_dir = tmp_path / "layers"
        layers_dir.mkdir()
        images_dir = tmp_path / "images"
        images_dir.mkdir()

        manifest: dict[str, Any] = {
            "schemaVersion": 2,
            "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
            "layers": [],
        }

        with (
            patch("docklet.registry._get_auth_token", return_value="tok") as mock_auth,
            patch("docklet.registry._get_manifest", return_value=manifest),
            patch("docklet.registry.LAYERS_DIR", layers_dir),
            patch("docklet.registry.IMAGES_DIR", images_dir),
        ):
            pull_image("myuser/myapp", "v2")

        mock_auth.assert_called_once_with("myuser/myapp")

    def test_saves_manifest_metadata(self, tmp_path: Path) -> None:
        from docklet.registry import pull_image

        layers_dir = tmp_path / "layers"
        layers_dir.mkdir()
        images_dir = tmp_path / "images"
        images_dir.mkdir()

        manifest = {
            "schemaVersion": 2,
            "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
            "layers": [
                {"digest": "sha256:abc", "size": 100},
            ],
        }

        with (
            patch("docklet.registry._get_auth_token", return_value="tok"),
            patch("docklet.registry._get_manifest", return_value=manifest),
            patch("docklet.registry._pull_layer"),
            patch("docklet.registry.extract_layer"),
            patch("docklet.registry.LAYERS_DIR", layers_dir),
            patch("docklet.registry.IMAGES_DIR", images_dir),
        ):
            pull_image("alpine", "3.18")

        # Should save manifest to images dir
        manifest_path = images_dir / "alpine" / "3.18" / "manifest.json"
        assert manifest_path.exists()
        saved = json.loads(manifest_path.read_text())
        assert saved["layers"][0]["digest"] == "sha256:abc"
