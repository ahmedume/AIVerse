# tests/test_files_api.py
# Purpose: files API integration tests — upload (multipart + JSON text), list, delete, errors.

from fastapi.testclient import TestClient


def test_upload_json_text(client: TestClient):
    resp = client.post("/api/files", json={"text": "Hello world.\n\nSecond paragraph."})
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["blocks"] == 2
    assert data["words"] > 0

    listing = client.get("/api/files")
    assert listing.status_code == 200
    assert listing.json()["data"][0]["id"] == data["id"]

    deleted = client.delete(f"/api/files/{data['id']}")
    assert deleted.status_code == 204
    assert client.get("/api/files").json()["data"] == []


def test_upload_multipart(client: TestClient):
    resp = client.post(
        "/api/files",
        files={"file": ("note.txt", b"Hello from multipart.", "text/plain")},
    )
    assert resp.status_code == 201
    assert resp.json()["data"]["filename"] == "note.txt"


def test_upload_unsupported_type(client: TestClient):
    resp = client.post("/api/files", files={"file": ("run.exe", b"MZ...", "application/octet-stream")})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"


def test_upload_empty_text(client: TestClient):
    resp = client.post("/api/files", json={"text": "   "})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "EMPTY_DOCUMENT"


def test_delete_missing_returns_404(client: TestClient):
    resp = client.delete("/api/files/0000000000000000")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"