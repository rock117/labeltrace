"""5.3–5.5：split、跨项目防护、仅 frame 成员。"""

from fastapi.testclient import TestClient

from app.main import app


def _h(u: str) -> dict[str, str]:
    return {"X-User-Id": u}


def test_split_cross_project_and_hidden_only_dataset() -> None:
    png = b"\x89PNG\r\n\x1a\n" + b"\x02" * 40
    with TestClient(app) as client:
        p1 = client.post(
            "/api/v1/projects", json={"name": "P1"}, headers=_h("a")
        ).json()["id"]
        p2 = client.post(
            "/api/v1/projects", json={"name": "P2"}, headers=_h("b")
        ).json()["id"]
        f1 = client.post(
            f"/api/v1/projects/{p1}/folders", json={"name": "F"}, headers=_h("a")
        ).json()["id"]
        f2 = client.post(
            f"/api/v1/projects/{p2}/folders", json={"name": "F"}, headers=_h("b")
        ).json()["id"]

        img1 = client.post(
            f"/api/v1/folders/{f1}/assets",
            headers=_h("a"),
            files={"file": ("1.png", png, "image/png")},
        ).json()["id"]
        img2 = client.post(
            f"/api/v1/folders/{f2}/assets",
            headers=_h("b"),
            files={"file": ("2.png", png + b"x", "image/png")},
        ).json()["id"]

        ds = client.post(
            f"/api/v1/projects/{p1}/datasets",
            json={"name": "D", "enabled_annotation_types": ["rect"]},
            headers=_h("a"),
        ).json()
        did = ds["id"]

        client.post(
            f"/api/v1/datasets/{did}/assets",
            json={"asset_ids": [img1], "split": "train"},
            headers=_h("a"),
        )
        # split 更新
        patch = client.patch(
            f"/api/v1/datasets/{did}/assets/{img1}",
            json={"split": "val"},
            headers=_h("a"),
        )
        assert patch.status_code == 200
        assert patch.json()["split"] == "val"

        # 跨项目拒绝
        bad = client.post(
            f"/api/v1/datasets/{did}/assets",
            json={"asset_ids": [img2]},
            headers=_h("a"),
        )
        assert bad.status_code == 422

        # 同一 asset 可属两个数据集
        ds2 = client.post(
            f"/api/v1/projects/{p1}/datasets",
            json={"name": "D2"},
            headers=_h("a"),
        ).json()["id"]
        ok = client.post(
            f"/api/v1/datasets/{ds2}/assets",
            json={"asset_ids": [img1]},
            headers=_h("a"),
        )
        assert ok.status_code == 200

        members = client.get(
            f"/api/v1/datasets/{did}/assets", headers=_h("a")
        ).json()
        assert any(m["asset_id"] == img1 and m["split"] == "val" for m in members)
