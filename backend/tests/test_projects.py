"""项目与成员：列表隔离、多角色、viewer 上传 403。"""

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
    owner = client.post(
        "/api/v1/projects", json={"name": "角色测试"}, headers=_h("owner1")
    )
    project_id = owner.json()["id"]

    add = client.post(
        f"/api/v1/projects/{project_id}/members",
        json={"user_id": "viewer1", "roles": ["viewer"]},
        headers=_h("owner1"),
    )
    assert add.status_code == 201
    assert add.json()["roles"] == ["viewer"]

    forbidden = client.post(
        f"/api/v1/projects/{project_id}/assets/upload",
        headers=_h("viewer1"),
    )
    assert forbidden.status_code == 403

    allowed = client.post(
        f"/api/v1/projects/{project_id}/assets/upload",
        headers=_h("owner1"),
    )
    assert allowed.status_code == 202


def test_user_can_have_roles_across_projects() -> None:
    p1 = client.post(
        "/api/v1/projects", json={"name": "项目甲"}, headers=_h("alice")
    ).json()["id"]
    p2 = client.post(
        "/api/v1/projects", json={"name": "项目乙"}, headers=_h("bob")
    ).json()["id"]

    add = client.post(
        f"/api/v1/projects/{p2}/members",
        json={"user_id": "alice", "roles": ["annotator"]},
        headers=_h("bob"),
    )
    assert add.status_code == 201
    assert add.json()["roles"] == ["annotator"]

    members = client.get(f"/api/v1/projects/{p2}/members", headers=_h("alice"))
    assert members.status_code == 200
    by_user = {m["user_id"]: m["roles"] for m in members.json()}
    assert by_user["alice"] == ["annotator"]
    assert by_user["bob"] == ["owner"]

    alice_projects = {
        p["id"] for p in client.get("/api/v1/projects", headers=_h("alice")).json()
    }
    assert p1 in alice_projects and p2 in alice_projects


def test_same_project_multiple_roles() -> None:
    pid = client.post(
        "/api/v1/projects", json={"name": "多角色"}, headers=_h("owner1")
    ).json()["id"]
    add = client.post(
        f"/api/v1/projects/{pid}/members",
        json={"user_id": "multi1", "roles": ["annotator", "viewer"]},
        headers=_h("owner1"),
    )
    assert add.status_code == 201
    assert add.json()["roles"] == ["annotator", "viewer"]

    # 含 annotator → 可写
    ok = client.post(
        f"/api/v1/projects/{pid}/assets/upload",
        headers=_h("multi1"),
    )
    assert ok.status_code == 202

    patched = client.patch(
        f"/api/v1/projects/{pid}/members/multi1",
        json={"roles": ["viewer"]},
        headers=_h("owner1"),
    )
    assert patched.status_code == 200
    assert patched.json()["roles"] == ["viewer"]

    forbidden = client.post(
        f"/api/v1/projects/{pid}/assets/upload",
        headers=_h("multi1"),
    )
    assert forbidden.status_code == 403


def test_owner_can_change_member_roles() -> None:
    pid = client.post(
        "/api/v1/projects", json={"name": "改角色"}, headers=_h("owner1")
    ).json()["id"]
    client.post(
        f"/api/v1/projects/{pid}/members",
        json={"user_id": "ann1", "roles": ["annotator"]},
        headers=_h("owner1"),
    )
    patched = client.patch(
        f"/api/v1/projects/{pid}/members/ann1",
        json={"roles": ["viewer", "annotator"]},
        headers=_h("owner1"),
    )
    assert patched.status_code == 200
    assert patched.json()["roles"] == ["annotator", "viewer"]
