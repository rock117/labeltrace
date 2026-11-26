"""图片上传、hash storage_key、RFC 5987 Content-Disposition。"""

from urllib.parse import unquote

from fastapi.testclient import TestClient

from app.main import app
from app.services.assets import content_disposition_attachment


def _h(user: str) -> dict[str, str]:
    return {"X-User-Id": user}


def test_content_disposition_rfc5987_chinese() -> None:
    header = content_disposition_attachment("图 1.jpg")
    assert "filename=" in header
    assert "filename*=UTF-8''" in header
    assert "图" not in header.split("filename*=UTF-8''")[0]  # ASCII fallback 段
    encoded = header.split("filename*=UTF-8''", 1)[1]
    assert unquote(encoded) == "图 1.jpg"


def test_upload_image_and_read_content() -> None:
    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
        b"\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05"
        b"\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    with TestClient(app) as client:
        proj = client.post(
            "/api/v1/projects", json={"name": "素材上传"}, headers=_h("up1")
        )
        pid = proj.json()["id"]
        folder = client.post(
            f"/api/v1/projects/{pid}/folders",
            json={"name": "产线 A"},
            headers=_h("up1"),
        )
        assert folder.status_code == 201
        assert folder.json()["name"] == "产线 A"
        fid = folder.json()["id"]

        up = client.post(
            f"/api/v1/folders/{fid}/assets",
            headers=_h("up1"),
            files={"file": ("图 1.png", png, "image/png")},
        )
        assert up.status_code == 201, up.text
        body = up.json()
        assert body["media_kind"] == "image"
        assert body["filename"] == "图 1.png"
        assert body["library_visible"] is True
        assert body["origin"] == "upload"
        assert body["storage_backend"] == "local"
        assert body["content_hash"]
        assert body["storage_key"].startswith(f"proj/{pid}/assets/")
        assert "产线" not in body["storage_key"]
        assert "图" not in body["storage_key"]
        asset_id = body["id"]

        meta = client.get(f"/api/v1/assets/{asset_id}", headers=_h("up1"))
        assert meta.status_code == 200
        assert meta.json()["folder_id"] == fid

        content = client.get(
            f"/api/v1/assets/{asset_id}/content", headers=_h("up1")
        )
        assert content.status_code == 200
        assert content.content == png
        cd = content.headers.get("content-disposition", "")
        assert "filename*=UTF-8''" in cd
        assert unquote(cd.split("filename*=UTF-8''", 1)[1]) == "图 1.png"

        listed = client.get(
            f"/api/v1/folders/{fid}/assets", headers=_h("up1")
        )
        assert listed.status_code == 200
        assert any(a["id"] == asset_id for a in listed.json())


def test_dedup_move_and_delete_conflict(monkeypatch) -> None:
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24
    with TestClient(app) as client:
        proj = client.post(
            "/api/v1/projects", json={"name": "去重移动"}, headers=_h("up2")
        )
        pid = proj.json()["id"]
        f1 = client.post(
            f"/api/v1/projects/{pid}/folders",
            json={"name": "A"},
            headers=_h("up2"),
        ).json()["id"]
        f2 = client.post(
            f"/api/v1/projects/{pid}/folders",
            json={"name": "B"},
            headers=_h("up2"),
        ).json()["id"]

        a1 = client.post(
            f"/api/v1/folders/{f1}/assets",
            headers=_h("up2"),
            files={"file": ("x.png", png, "image/png")},
        )
        assert a1.status_code == 201
        id1 = a1.json()["id"]
        key1 = a1.json()["storage_key"]

        a2 = client.post(
            f"/api/v1/folders/{f1}/assets",
            headers=_h("up2"),
            files={"file": ("y.png", png, "image/png")},
        )
        assert a2.status_code == 201
        assert a2.json()["id"] == id1
        assert a2.json()["storage_key"] == key1

        moved = client.post(
            f"/api/v1/assets/{id1}/move",
            json={"folder_id": f2},
            headers=_h("up2"),
        )
        assert moved.status_code == 200
        assert moved.json()["folder_id"] == f2
        assert moved.json()["storage_key"] == key1

        assert (
            client.get(f"/api/v1/folders/{f1}/assets", headers=_h("up2")).json()
            == []
        )
        assert len(
            client.get(f"/api/v1/folders/{f2}/assets", headers=_h("up2")).json()
        ) == 1

        monkeypatch.setattr(
            "app.services.asset_refs.asset_has_references",
            lambda db, asset_id: True,
        )
        blocked = client.delete(f"/api/v1/assets/{id1}", headers=_h("up2"))
        assert blocked.status_code == 409

        monkeypatch.setattr(
            "app.services.asset_refs.asset_has_references",
            lambda db, asset_id: False,
        )
        ok = client.delete(f"/api/v1/assets/{id1}", headers=_h("up2"))
        assert ok.status_code == 204
