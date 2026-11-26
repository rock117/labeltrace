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
