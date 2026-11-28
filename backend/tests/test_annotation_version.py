"""标注、发版、memberSources、血缘（主体路径，不含导入导出）。"""

from uuid import uuid4

from fastapi.testclient import TestClient

from app.annotation.registry import INTERNAL_FORMAT, get_registry
from app.main import app


def _h(u: str) -> dict[str, str]:
    return {"X-User-Id": u}


def test_format_xyxy_abs_unit() -> None:
    assert INTERNAL_FORMAT == "xyxy_abs"
    reg = get_registry()
    cid = str(uuid4())
    ok = reg.validate_shapes(
        {
            "format": "xyxy_abs",
            "items": [
                {"type": "rect", "classId": cid, "bbox": [1, 2, 10, 20]}
            ],
        },
        enabled_types=["rect"],
        allowed_class_ids={cid},
    )
    assert ok["items"][0]["bbox"] == [1.0, 2.0, 10.0, 20.0]
    assert ok["items"][0]["classId"] == cid
    try:
        reg.validate_shapes(
            {
                "format": "xyxy_abs",
                "items": [{"type": "polygon", "classId": cid, "points": []}],
            },
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

        d1_body = client.post(
            f"/api/v1/projects/{pid}/datasets",
            json={"name": "A", "enabled_annotation_types": ["rect"]},
            headers=_h("admin"),
        ).json()
        d2_body = client.post(
            f"/api/v1/projects/{pid}/datasets",
            json={"name": "B", "enabled_annotation_types": ["rect"]},
            headers=_h("admin"),
        ).json()
        assert d1_body["classes"] == []
        d1 = d1_body["id"]
        d2 = d2_body["id"]
        c1 = client.post(
            f"/api/v1/projects/{pid}/classes",
            json={"name": "缺陷"},
            headers=_h("admin"),
        ).json()["id"]
        c2 = client.post(
            f"/api/v1/projects/{pid}/classes",
            json={"name": "污渍"},
            headers=_h("admin"),
        ).json()["id"]
        c1_res = client.put(
            f"/api/v1/datasets/{d1}/classes",
            json={"classIds": [c1]},
            headers=_h("admin"),
        )
        c2_res = client.put(
            f"/api/v1/datasets/{d2}/classes",
            json={"classIds": [c2]},
            headers=_h("admin"),
        )
        assert c1_res.status_code == 200, c1_res.text
        assert c2_res.status_code == 200, c2_res.text
        assert c1_res.json()["classes"][0]["id"] == c1
        assert c2_res.json()["classes"][0]["id"] == c2

        # 非成员拒绝
        assert (
            client.put(
                f"/api/v1/datasets/{d1}/assets/{img}/annotation",
                json={
                    "shapes": {
                        "format": "xyxy_abs",
                        "items": [
                            {
                                "type": "rect",
                                "classId": c1,
                                "bbox": [0, 0, 5, 5],
                            }
                        ],
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
                    "items": [
                        {
                            "type": "rect",
                            "classId": c1,
                            "bbox": [1, 1, 50, 50],
                        }
                    ],
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
                    "items": [
                        {
                            "type": "rect",
                            "classId": c2,
                            "bbox": [9, 9, 20, 20],
                        }
                    ],
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
        assert g1["shapes"]["items"][0]["classId"] == c1
        assert g1["updated_by"]

        # polygon 拒绝
        bad = client.put(
            f"/api/v1/datasets/{d1}/assets/{img}/annotation",
            json={
                "shapes": {
                    "format": "xyxy_abs",
                    "items": [
                        {"type": "polygon", "classId": c1, "points": []}
                    ],
                }
            },
            headers=_h("admin"),
        )
        assert bad.status_code == 422

        # 项目里改名保留 classId；停用被引用类 409
        renamed = client.patch(
            f"/api/v1/projects/{pid}/classes/{c1}",
            json={"name": "缺陷-A"},
            headers=_h("admin"),
        )
        assert renamed.status_code == 200, renamed.text
        assert renamed.json()["id"] == c1
        assert renamed.json()["name"] == "缺陷-A"
        ds_after = client.get(
            f"/api/v1/datasets/{d1}", headers=_h("admin")
        ).json()
        assert ds_after["classes"][0]["name"] == "缺陷-A"
        assert ds_after["classes"][0]["id"] == c1
        blocked = client.put(
            f"/api/v1/datasets/{d1}/classes",
            json={"classIds": [c2]},
            headers=_h("admin"),
        )
        assert blocked.status_code == 409, blocked.text

        sources = client.get(
            f"/api/v1/datasets/{d1}/member-sources", headers=_h("admin")
        )
        assert sources.status_code == 200
        assert any(s.get("kind") == "upload" for s in sources.json())

        # 发版前须 submitted；上面 put1 已 submitted，put2 后 d1 可能被改成 draft
        client.put(
            f"/api/v1/datasets/{d1}/assets/{img}/annotation",
            json={
                "shapes": {
                    "format": "xyxy_abs",
                    "items": [
                        {
                            "type": "rect",
                            "classId": c1,
                            "bbox": [1, 1, 50, 50],
                        }
                    ],
                },
                "status": "submitted",
            },
            headers=_h("admin"),
        )

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
        assert v1.json()["classes"][0]["id"] == c1
        assert v1.json()["classes"][0]["name"] == "缺陷-A"

        # 改工作区后版本不变
        client.put(
            f"/api/v1/datasets/{d1}/assets/{img}/annotation",
            json={
                "shapes": {
                    "format": "xyxy_abs",
                    "items": [
                        {
                            "type": "rect",
                            "classId": c1,
                            "bbox": [0, 0, 2, 2],
                        }
                    ],
                },
                "status": "submitted",
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

        dup = client.post(
            f"/api/v1/projects/{pid}/classes",
            json={"name": "缺陷-A"},
            headers=_h("admin"),
        )
        assert dup.status_code == 409, dup.text
        blocked_delete = client.delete(
            f"/api/v1/projects/{pid}/classes/{c1}",
            headers=_h("admin"),
        )
        assert blocked_delete.status_code == 409, blocked_delete.text
        spare = client.post(
            f"/api/v1/projects/{pid}/classes",
            json={"name": "临时"},
            headers=_h("admin"),
        )
        assert spare.status_code == 201, spare.text
        removed = client.delete(
            f"/api/v1/projects/{pid}/classes/{spare.json()['id']}",
            headers=_h("admin"),
        )
        assert removed.status_code == 204, removed.text

        lin = client.get(f"/api/v1/assets/{img}/lineage", headers=_h("admin"))
        assert lin.status_code == 200
        body = lin.json()
        assert body["origin"] == "upload"
        assert len(body["datasets"]) >= 1
        assert len(body["versions"]) >= 1
