"""项目与成员：列表隔离、viewer 上传 403。"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _h(user: str) -> dict[str, str]:
    return {"X-User-Id": user}


def test_create_and_list_only_own_projects() -> None:
    r1 = client.post("/api/v1/projects", json={"name": "甲项目"}, headers=_h("alice"))
    assert r1.status_code == 201
    pid = r1.json()["id"]

    client.post("/api/v1/projects", json={"name": "乙项目"}, headers=_h("bob"))

    alice_list = client.get("/api/v1/projects", headers=_h("alice")).json()
    ids = {p["id"] for p in alice_list}
    assert pid in ids
    assert all(p["name"] != "乙项目" for p in alice_list)


def test_viewer_upload_forbidden() -> None:
    admin = client.post(
        "/api/v1/projects", json={"name": "角色测试"}, headers=_h("admin1")
    )
    project_id = admin.json()["id"]

    add = client.post(
        f"/api/v1/projects/{project_id}/members",
        json={"user_id": "viewer1", "role": "viewer"},
        headers=_h("admin1"),
    )
    assert add.status_code == 201

    forbidden = client.post(
        f"/api/v1/projects/{project_id}/assets/upload",
        headers=_h("viewer1"),
    )
    assert forbidden.status_code == 403

    allowed = client.post(
        f"/api/v1/projects/{project_id}/assets/upload",
        headers=_h("admin1"),
    )
    assert allowed.status_code == 202
