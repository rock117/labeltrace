"""多类型标注：启用、校验、停用冲突。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

PNG = b"\x89PNG\r\n\x1a\n" + b"\x02" * 40


def _h(u: str) -> dict[str, str]:
    return {"X-User-Id": u}


def _setup(client: TestClient) -> tuple[str, str, str]:
    pid = client.post(
        "/api/v1/projects", json={"name": "多类型"}, headers=_h("u")
    ).json()["id"]
    folder = client.post(
        f"/api/v1/projects/{pid}/folders", json={"name": "F"}, headers=_h("u")
    ).json()["id"]
    img = client.post(
        f"/api/v1/folders/{folder}/assets",
        headers=_h("u"),
        files={"file": ("a.png", PNG, "image/png")},
    ).json()["id"]
    ds = client.post(
        f"/api/v1/projects/{pid}/datasets",
        json={"name": "D"},
        headers=_h("u"),
    ).json()
    did = ds["id"]
    client.post(
        f"/api/v1/datasets/{did}/assets",
        json={"asset_ids": [img]},
        headers=_h("u"),
    )
    cid = ds["classes"][0]["id"] if ds.get("classes") else None
    if not cid:
        cls = client.post(
            f"/api/v1/projects/{pid}/classes",
            json={"name": "物"},
            headers=_h("u"),
        ).json()
        cid = cls["id"]
        client.put(
            f"/api/v1/datasets/{did}/classes",
            json={"classIds": [cid]},
            headers=_h("u"),
        )
    return did, img, cid


def test_enable_types_and_save_shapes() -> None:
    with TestClient(app) as client:
        did, img, cid = _setup(client)

        # 未启用 polygon → 422
        bad = client.put(
            f"/api/v1/datasets/{did}/assets/{img}/annotation",
            headers=_h("u"),
            json={
                "shapes": {
                    "format": "xyxy_abs",
                    "items": [
                        {
                            "type": "polygon",
                            "classId": cid,
                            "points": [[0, 0], [10, 0], [10, 10]],
                        }
                    ],
                }
            },
        )
        assert bad.status_code == 422

        patch = client.patch(
            f"/api/v1/datasets/{did}",
            headers=_h("u"),
            json={
                "enabledAnnotationTypes": [
                    "rect",
                    "polygon",
                    "mask",
                    "keypoint",
                    "obb",
                    "classification",
                ]
            },
        )
        assert patch.status_code == 200, patch.text
        assert set(patch.json()["enabled_annotation_types"]) == {
            "rect",
            "polygon",
            "mask",
            "keypoint",
            "obb",
            "classification",
        }

        items = [
            {
                "type": "polygon",
                "classId": cid,
                "points": [[1, 1], [20, 1], [20, 20], [1, 20]],
            },
            {
                "type": "obb",
                "classId": cid,
                "cx": 50,
                "cy": 40,
                "w": 30,
                "h": 20,
                "angle": 15,
            },
            {
                "type": "keypoint",
                "classId": cid,
                "points": [{"x": 5, "y": 5, "v": 2}, {"x": 8, "y": 9}],
            },
            {
                "type": "mask",
                "classId": cid,
                "strokes": [{"points": [[2, 2], [3, 4], [5, 6]], "width": 10}],
            },
            {"type": "classification", "classId": cid},
            {
                "type": "rect",
                "classId": cid,
                "bbox": [0, 0, 12, 12],
            },
        ]
        ok = client.put(
            f"/api/v1/datasets/{did}/assets/{img}/annotation",
            headers=_h("u"),
            json={"shapes": {"format": "xyxy_abs", "items": items}, "status": "draft"},
        )
        assert ok.status_code == 200, ok.text
        got = ok.json()["shapes"]["items"]
        assert [x["type"] for x in got] == [
            "polygon",
            "obb",
            "keypoint",
            "mask",
            "classification",
            "rect",
        ]

        # 停用仍被引用的 polygon → 409
        blocked = client.patch(
            f"/api/v1/datasets/{did}",
            headers=_h("u"),
            json={"enabledAnnotationTypes": ["rect"]},
        )
        assert blocked.status_code == 409

        # 清空 polygon 后再停用
        client.put(
            f"/api/v1/datasets/{did}/assets/{img}/annotation",
            headers=_h("u"),
            json={
                "shapes": {
                    "format": "xyxy_abs",
                    "items": [
                        {"type": "rect", "classId": cid, "bbox": [0, 0, 5, 5]}
                    ],
                }
            },
        )
        cleared = client.patch(
            f"/api/v1/datasets/{did}",
            headers=_h("u"),
            json={"enabledAnnotationTypes": ["rect"]},
        )
        assert cleared.status_code == 200
        assert cleared.json()["enabled_annotation_types"] == ["rect"]
