"""目录树：嵌套创建、同级重名 409。"""

from fastapi.testclient import TestClient

from app.main import app


def _h(user: str) -> dict[str, str]:
    return {"X-User-Id": user}


def test_nested_folder_and_sibling_conflict() -> None:
    with TestClient(app) as client:
        proj = client.post(
            "/api/v1/projects", json={"name": "库测试"}, headers=_h("u1")
        )
        assert proj.status_code == 201
        pid = proj.json()["id"]

        root = client.post(
            f"/api/v1/projects/{pid}/folders",
            json={"name": "缺陷样本"},
            headers=_h("u1"),
        )
        assert root.status_code == 201
        assert root.json()["path"] == "缺陷样本"
        root_id = root.json()["id"]

        child = client.post(
            f"/api/v1/projects/{pid}/folders",
            json={"name": "划痕", "parent_id": root_id},
            headers=_h("u1"),
        )
        assert child.status_code == 201
        assert child.json()["path"] == "缺陷样本/划痕"

        listed = client.get(
            f"/api/v1/projects/{pid}/folders",
            params={"parent_id": root_id},
            headers=_h("u1"),
        )
        assert listed.status_code == 200
        assert [f["name"] for f in listed.json()] == ["划痕"]

        dup = client.post(
            f"/api/v1/projects/{pid}/folders",
            json={"name": "划痕", "parent_id": root_id},
            headers=_h("u1"),
        )
        assert dup.status_code == 409
        assert dup.json()["code"] == "conflict"


def test_child_folder_list_includes_direct_media_counts() -> None:
    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
        b"\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05"
        b"\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    with TestClient(app) as client:
        proj = client.post(
            "/api/v1/projects", json={"name": "目录计数"}, headers=_h("cnt1")
        )
        pid = proj.json()["id"]
        root = client.post(
            f"/api/v1/projects/{pid}/folders",
            json={"name": "A"},
            headers=_h("cnt1"),
        )
        root_id = root.json()["id"]
        child = client.post(
            f"/api/v1/projects/{pid}/folders",
            json={"name": "B", "parent_id": root_id},
            headers=_h("cnt1"),
        )
        child_id = child.json()["id"]
        up = client.post(
            f"/api/v1/folders/{child_id}/assets",
            headers=_h("cnt1"),
            files={"file": ("a.png", png, "image/png")},
        )
        assert up.status_code == 201, up.text

        listed = client.get(
            f"/api/v1/projects/{pid}/folders",
            params={"parent_id": root_id},
            headers=_h("cnt1"),
        )
        assert listed.status_code == 200
        body = listed.json()
        assert len(body) == 1
        assert body[0]["name"] == "B"
        assert body[0]["image_count"] == 1
        assert body[0]["video_count"] == 0
