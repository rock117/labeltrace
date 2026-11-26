"""标注、发版、memberSources、血缘（主体路径，不含导入导出）。"""

from fastapi.testclient import TestClient

from app.annotation.registry import INTERNAL_FORMAT, get_registry
from app.main import app


def _h(u: str) -> dict[str, str]:
    return {"X-User-Id": u}


def test_format_xyxy_abs_unit() -> None:
    assert INTERNAL_FORMAT == "xyxy_abs"
    reg = get_registry()
    ok = reg.validate_shapes(
        {
            "format": "xyxy_abs",
            "items": [{"type": "rect", "cls": 0, "bbox": [1, 2, 10, 20]}],
        },
        enabled_types=["rect"],
    )
    assert ok["items"][0]["bbox"] == [1.0, 2.0, 10.0, 20.0]
    try:
        reg.validate_shapes(
            {"format": "xyxy_abs", "items": [{"type": "polygon", "points": []}]},
            enabled_types=["rect"],
        )
        raised = False
    except Exception:
        raised = True
    assert raised


def test_annotation_isolation_publish_and_lineage() -> None:
    png = b"\x89PNG\r\n\x1a\n" + b"\x03" * 48
    with TestClient(app) as client:
        pid = client.post(
            "/api/v1/projects", json={"name": "标注发版"}, headers=_h("admin")
        ).json()["id"]
        fid = client.post(
            f"/api/v1/projects/{pid}/folders",
            json={"name": "图"},
            headers=_h("admin"),
        ).json()["id"]
        img = client.post(
            f"/api/v1/folders/{fid}/assets",
            headers=_h("admin"),
            files={"file": ("x.png", png, "image/png")},
        ).json()["id"]

        d1 = client.post(
            f"/api/v1/projects/{pid}/datasets",
            json={"name": "A", "classes": ["缺陷"], "enabled_annotation_types": ["rect"]},
            headers=_h("admin"),
        ).json()["id"]
        d2 = client.post(
            f"/api/v1/projects/{pid}/datasets",
            json={"name": "B", "classes": ["缺陷"], "enabled_annotation_types": ["rect"]},
            headers=_h("admin"),
        ).json()["id"]

        # 非成员拒绝
        assert (
            client.put(
                f"/api/v1/datasets/{d1}/assets/{img}/annotation",
                json={
                    "shapes": {
                        "format": "xyxy_abs",
                        "items": [{"type": "rect", "cls": 0, "bbox": [0, 0, 5, 5]}],
                    }
                },
                headers=_h("admin"),
            ).status_code
            == 422
        )

        client.post(
            f"/api/v1/datasets/{d1}/assets",
            json={"asset_ids": [img]},
            headers=_h("admin"),
        )
        client.post(
            f"/api/v1/datasets/{d2}/assets",
            json={"asset_ids": [img]},
            headers=_h("admin"),
        )

        put1 = client.put(
            f"/api/v1/datasets/{d1}/assets/{img}/annotation",
            json={
                "shapes": {
                    "format": "xyxy_abs",
                    "items": [{"type": "rect", "cls": 0, "bbox": [1, 1, 50, 50]}],
                },
                "status": "submitted",
            },
            headers=_h("admin"),
        )
        assert put1.status_code == 200, put1.text
        put2 = client.put(
            f"/api/v1/datasets/{d2}/assets/{img}/annotation",
            json={
                "shapes": {
                    "format": "xyxy_abs",
                    "items": [{"type": "rect", "cls": 0, "bbox": [9, 9, 20, 20]}],
                }
            },
            headers=_h("admin"),
        )
        assert put2.status_code == 200

        g1 = client.get(
            f"/api/v1/datasets/{d1}/assets/{img}/annotation", headers=_h("admin")
        ).json()
        g2 = client.get(
            f"/api/v1/datasets/{d2}/assets/{img}/annotation", headers=_h("admin")
        ).json()
        assert g1["shapes"]["items"][0]["bbox"][0] == 1.0
        assert g2["shapes"]["items"][0]["bbox"][0] == 9.0
        assert g1["updated_by"] == "admin"

        # polygon 拒绝
        bad = client.put(
            f"/api/v1/datasets/{d1}/assets/{img}/annotation",
            json={
                "shapes": {
                    "format": "xyxy_abs",
                    "items": [{"type": "polygon", "cls": 0, "points": []}],
                }
            },
            headers=_h("admin"),
        )
        assert bad.status_code == 422

        sources = client.get(
            f"/api/v1/datasets/{d1}/member-sources", headers=_h("admin")
        )
        assert sources.status_code == 200
        assert any(s.get("kind") == "upload" for s in sources.json())

        v1 = client.post(
            f"/api/v1/datasets/{d1}/versions",
            json={"name": "v1"},
            headers=_h("admin"),
        )
        assert v1.status_code == 201, v1.text
        vid = v1.json()["id"]
        frozen_sources = list(v1.json()["member_sources"])
        assert v1.json()["entry_count"] == 1
        assert v1.json()["change_summary"]["added"] == 1

        # 改工作区后版本不变
        client.put(
            f"/api/v1/datasets/{d1}/assets/{img}/annotation",
            json={
                "shapes": {
                    "format": "xyxy_abs",
                    "items": [{"type": "rect", "cls": 0, "bbox": [0, 0, 2, 2]}],
                }
            },
            headers=_h("admin"),
        )
        man = client.get(
            f"/api/v1/versions/{vid}/manifest", headers=_h("admin")
        ).json()
        assert man["entries"][0]["shapes"]["items"][0]["bbox"][2] == 50.0
        assert client.get(
            f"/api/v1/versions/{vid}", headers=_h("admin")
        ).json()["member_sources"] == frozen_sources

        v2 = client.post(
            f"/api/v1/datasets/{d1}/versions",
            json={"name": "v2"},
            headers=_h("admin"),
        )
        assert v2.status_code == 201
        assert v2.json()["change_summary"]["changedAnnotations"] == 1
        assert v2.json()["parent_id"] == vid

        lin = client.get(f"/api/v1/assets/{img}/lineage", headers=_h("admin"))
        assert lin.status_code == 200
        body = lin.json()
        assert body["origin"] == "upload"
        assert len(body["datasets"]) >= 1
        assert len(body["versions"]) >= 1
