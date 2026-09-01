"""Tests for SPA fallback path traversal protection (P0-2).

Two layers:
- The ``_build_app``-based tests exercise the exact containment logic
  (resolve + strict ``parents`` membership) in isolation, including a symlink
  escape that only ``resolve()`` can catch.
- ``test_real_main_spa_fallback_*`` boot the REAL ``app.main`` in a subprocess
  with ``FRONTEND_STATIC_DIR`` pointed at a temp dist, so the production
  ``spa_fallback`` handler itself is covered (these fail on the old
  ``frontend_dist / full_path`` join).
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.testclient import TestClient


def _build_app(dist: Path) -> FastAPI:
    """Recreate the SPA-serving app against a temp dist directory."""

    app = FastAPI()
    resolved_root = dist.resolve()

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        candidate = (dist / full_path).resolve()
        if full_path and candidate.is_file() and resolved_root in candidate.parents:
            return FileResponse(candidate)
        index = dist / "index.html"
        if index.is_file():
            return FileResponse(index)
        return {"detail": "Not Found"}

    return app


@pytest.fixture
def dist(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>spa-index</html>")
    (dist / "favicon.ico").write_bytes(b"fake-icon")
    (dist / "assets").mkdir()
    (dist / "assets" / "app.js").write_text("console.log('app')")
    return dist


@pytest.fixture
def client(dist: Path) -> TestClient:
    return TestClient(_build_app(dist))


def test_normal_file_served(client: TestClient, dist: Path) -> None:
    resp = client.get("/favicon.ico")
    assert resp.status_code == 200
    assert resp.content == (dist / "favicon.ico").read_bytes()


def test_encoded_absolute_path_falls_back_to_index(client: TestClient) -> None:
    resp = client.get("/%2Fetc%2Fpasswd")
    assert resp.status_code == 200
    assert b"spa-index" in resp.content  # index.html fallback, never /etc/passwd
    assert b"root:" not in resp.content


def test_encoded_traversal_falls_back_to_index(client: TestClient) -> None:
    resp = client.get("/..%2f..%2fetc%2fpasswd")
    assert resp.status_code == 200
    assert b"spa-index" in resp.content


def test_double_slash_traversal_falls_back_to_index(client: TestClient) -> None:
    resp = client.get("/../../etc/passwd")
    assert resp.status_code == 200
    assert b"spa-index" in resp.content


def test_missing_path_serves_index(client: TestClient) -> None:
    resp = client.get("/anything")
    assert resp.status_code == 200
    assert b"spa-index" in resp.content


def test_file_outside_dist_never_served(tmp_path: Path, dist: Path) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP SECRET")
    # A directory inside dist symlinked to outside must not leak the target.
    (dist / "leak").symlink_to(secret, target_is_directory=False)
    client = TestClient(_build_app(dist))

    resp = client.get("/leak")
    assert resp.status_code == 200
    assert b"spa-index" in resp.content
    assert b"TOP SECRET" not in resp.content


# ── Real app.main spa_fallback (production handler) ────────────────

def _request_real_app(dist: Path, path: str) -> tuple[int, bytes]:
    """GET ``path`` against the real app.main app with FRONTEND_STATIC_DIR=dist.

    app.main reads FRONTEND_STATIC_DIR at import time, so it must run in a
    subprocess. TestClient needs no server port — it drives the ASGI app
    directly, so we only need the response printed to stdout.
    """
    code = (
        "from fastapi.testclient import TestClient\n"
        "from app.main import app\n"
        f"path = {path!r}\n"
        "with TestClient(app) as client:\n"
        "    resp = client.get(path)\n"
        "    import sys\n"
        "    sys.stdout.write(f\"{resp.status_code}\\n\")\n"
        "    sys.stdout.flush()\n"
        "    sys.stdout.buffer.write(resp.content)\n"
    )
    env = {**os.environ, "FRONTEND_STATIC_DIR": str(dist), "PYTHONPATH": "tests"}
    # Keep the DB away from any default location for this short-lived process.
    env.setdefault("UPLOAD_DIR", str(dist.parent / "uploads"))
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        env=env,
        cwd=str(Path(__file__).resolve().parent.parent),
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr.decode()
    out = proc.stdout
    nl = out.index(b"\n")
    return int(out[:nl]), out[nl + 1 :]


def test_real_main_serves_normal_file(dist: Path) -> None:
    status, body = _request_real_app(dist, "/favicon.ico")
    assert status == 200
    assert body == b"fake-icon"


def test_real_main_encoded_absolute_path_falls_back_to_index(dist: Path) -> None:
    status, body = _request_real_app(dist, "/%2Fetc%2Fpasswd")
    assert status == 200
    assert b"spa-index" in body
    assert b"root:" not in body


def test_real_main_encoded_traversal_falls_back_to_index(dist: Path) -> None:
    status, body = _request_real_app(dist, "/..%2f..%2fetc%2fpasswd")
    assert status == 200
    assert b"spa-index" in body
    assert b"root:" not in body


def test_real_main_missing_path_serves_index(dist: Path) -> None:
    status, body = _request_real_app(dist, "/anything")
    assert status == 200
    assert b"spa-index" in body
