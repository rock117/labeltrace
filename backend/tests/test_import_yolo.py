"""YOLO zip 导入：解析、去重、非库可见、非法包拒绝。"""

from __future__ import annotations

import io
import struct
import time
import zipfile

from fastapi.testclient import TestClient

from app.main import app
from app.services.import_yolo import (
    decode_yolo_line,
    parse_data_yaml_names,
    parse_yolo_zip,
    yolo_line_to_keypoint,
    yolo_line_to_obb,
    yolo_line_to_polygon,
)


def _h(u: str) -> dict[str, str]:
    return {"X-User-Id": u}


def _png(w: int = 100, h: int = 80, pad: bytes = b"") -> bytes:
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    chunk = struct.pack(">I", 13) + b"IHDR" + ihdr + b"\x00\x00\x00\x00"
    return b"\x89PNG\r\n\x1a\n" + chunk + pad


def _yolo_zip(*, with_box: bool = True, task: str = "detect") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "data.yaml",
            f'path: .\ntrain: train/images\nnames:\n  0: "缺陷"\ntask: {task}\n',
        )
        zf.writestr("train/images/a.png", _png(100, 80, b"\x11"))
        if with_box:
            # cx=0.5 cy=0.5 w=0.2 h=0.2 → xyxy 40,32,60,48 on 100x80
            zf.writestr("train/labels/a.txt", "0 0.5 0.5 0.2 0.2\n")
        else:
            zf.writestr("train/labels/a.txt", "")
        zf.writestr("train/images/b.png", _png(100, 80, b"\x22"))
        zf.writestr("train/labels/b.txt", "")
    return buf.getvalue()


def test_parse_data_yaml_variants() -> None:
    assert parse_data_yaml_names("names: ['a', 'b']\n") == ["a", "b"]
    assert parse_data_yaml_names("names:\n  0: person\n  1: car\n") == [
        "person",
        "car",
    ]
    pkg = parse_yolo_zip(_yolo_zip())
    assert pkg.classes == ["缺陷"]
    assert len(pkg.images) == 2
    assert pkg.task_hint == "detect"


def test_decode_segment_obb_pose_lines() -> None:
    cids = ["c1"]
    poly = yolo_line_to_polygon(
        "0 0.1 0.1 0.9 0.1 0.9 0.9 0.1 0.9".split(),
        100,
        100,
        class_ids=cids,
    )
    assert poly is not None
    assert poly["type"] == "polygon"
    assert len(poly["points"]) == 4
    assert abs(poly["points"][0][0] - 10) < 1e-6

    obb = yolo_line_to_obb(
        # axis-aligned 20x40 box centered at 50,50 → corners
        "0 0.4 0.3 0.6 0.3 0.6 0.7 0.4 0.7".split(),
        100,
        100,
        class_ids=cids,
    )
    assert obb is not None
    assert obb["type"] == "obb"
    assert abs(obb["cx"] - 50) < 1e-6
    assert abs(obb["cy"] - 50) < 1e-6
    assert abs(obb["w"] - 20) < 1e-6
    assert abs(obb["h"] - 40) < 1e-6

    kpt = yolo_line_to_keypoint(
        "0 0.5 0.5 0.2 0.2 0.2 0.3 2 0.8 0.7 2".split(),
        100,
        100,
        class_ids=cids,
        kpt_count=2,
    )
    assert kpt is not None
    assert kpt["type"] == "keypoint"
    assert len(kpt["points"]) == 2
    assert abs(kpt["points"][0]["x"] - 20) < 1e-6

    seg = decode_yolo_line(
        "segment",
        "0 0.1 0.1 0.9 0.1 0.9 0.9".split(),
        100,
        100,
        class_ids=cids,
    )
    assert seg is not None and seg["type"] == "polygon"


def test_import_creates_hidden_assets_and_dedup() -> None:
    z1 = _yolo_zip()
    with TestClient(app) as client:
        pid = client.post(
            "/api/v1/projects", json={"name": "导入测"}, headers=_h("imp-owner")
        ).json()["id"]

        # 非法包
        bad = client.post(
            f"/api/v1/projects/{pid}/dataset-imports",
            headers=_h("imp-owner"),
            files={"file": ("bad.zip", b"not-a-zip", "application/zip")},
            data={"datasetName": "坏包"},
        )
        assert bad.status_code == 422, bad.text

        r = client.post(
            f"/api/v1/projects/{pid}/dataset-imports",
            headers=_h("imp-owner"),
            files={"file": ("demo.zip", z1, "application/zip")},
            data={"datasetName": "导入集"},
        )
        assert r.status_code == 202, r.text
        import_id = r.json()["id"]
        dataset_id = r.json()["dataset_id"]
        assert dataset_id

        row = None
        for _ in range(80):
            row = client.get(
                f"/api/v1/dataset-imports/{import_id}", headers=_h("imp-owner")
            ).json()
            if row["status"] in ("succeeded", "failed"):
                break
            time.sleep(0.15)
        assert row is not None
        assert row["status"] == "succeeded", row
        assert row["stats"]["images"] == 2
        assert row["stats"]["created"] == 2
        assert row["stats"]["profile"] == "detect"

        imported = client.get(
            f"/api/v1/datasets/{dataset_id}", headers=_h("imp-owner")
        ).json()
        assert "rect" in imported["enabled_annotation_types"]
        assert imported["classes"][0]["name"] == "缺陷"
        class_id = imported["classes"][0]["id"]
        vocab = client.get(
            f"/api/v1/projects/{pid}/classes", headers=_h("imp-owner")
        ).json()
        assert [c["id"] for c in vocab] == [class_id]

        mem = client.get(
            f"/api/v1/datasets/{dataset_id}/assets", headers=_h("imp-owner")
        ).json()
        assert len(mem) == 2

        # 素材库目录不应出现导入图
        folders = client.get(
            f"/api/v1/projects/{pid}/folders", headers=_h("imp-owner")
        ).json()
        if folders:
            page = client.get(
                f"/api/v1/folders/{folders[0]['id']}/assets?media_kind=image",
                headers=_h("imp-owner"),
            ).json()
            ids = {a["id"] for a in page.get("items", page if isinstance(page, list) else [])}
            for m in mem:
                assert m["asset_id"] not in ids

        # 标注可读
        ann = client.get(
            f"/api/v1/datasets/{dataset_id}/assets/{mem[0]['asset_id']}/annotation",
            headers=_h("imp-owner"),
        ).json()
        assert ann["status"] == "submitted"

        # 血缘含 importId
        lin = client.get(
            f"/api/v1/assets/{mem[0]['asset_id']}/lineage",
            headers=_h("imp-owner"),
        ).json()
        assert lin.get("importId") == import_id

        # 再次导入相同内容到新空集 → reused
        empty = client.post(
            f"/api/v1/projects/{pid}/datasets",
            json={"name": "空集复用"},
            headers=_h("imp-owner"),
        ).json()["id"]
        r2 = client.post(
            f"/api/v1/projects/{pid}/dataset-imports",
            headers=_h("imp-owner"),
            files={"file": ("demo2.zip", z1, "application/zip")},
            data={"datasetId": empty},
        )
        assert r2.status_code == 202, r2.text
        iid2 = r2.json()["id"]
        row2 = None
        for _ in range(80):
            row2 = client.get(
                f"/api/v1/dataset-imports/{iid2}", headers=_h("imp-owner")
            ).json()
            if row2["status"] in ("succeeded", "failed"):
                break
            time.sleep(0.15)
        assert row2["status"] == "succeeded", row2
        assert row2["stats"]["reused"] == 2
        assert row2["stats"]["created"] == 0
        reused_ds = client.get(
            f"/api/v1/datasets/{empty}", headers=_h("imp-owner")
        ).json()
        assert reused_ds["classes"][0]["id"] == class_id
        vocab_after = client.get(
            f"/api/v1/projects/{pid}/classes", headers=_h("imp-owner")
        ).json()
        assert len(vocab_after) == 1


def _profile_zip(profile: str, label_line: str, *, yaml_extra: str = "") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "data.yaml",
            "path: .\ntrain: train/images\n"
            'names:\n  0: "缺陷"\n'
            f"task: {profile}\n{yaml_extra}",
        )
        zf.writestr("train/images/a.png", _png(100, 100, b"\x33"))
        zf.writestr("train/labels/a.txt", label_line + "\n")
    return buf.getvalue()


def _wait_import(client: TestClient, import_id: str, user: str = "imp-owner") -> dict:
    row = None
    for _ in range(80):
        row = client.get(
            f"/api/v1/dataset-imports/{import_id}", headers=_h(user)
        ).json()
        if row["status"] in ("succeeded", "failed"):
            break
        time.sleep(0.15)
    assert row is not None
    return row


def test_import_segment_profile() -> None:
    z = _profile_zip(
        "segment",
        "0 0.1 0.1 0.9 0.1 0.9 0.9 0.1 0.9",
    )
    with TestClient(app) as client:
        pid = client.post(
            "/api/v1/projects", json={"name": "seg导入"}, headers=_h("imp-seg")
        ).json()["id"]
        r = client.post(
            f"/api/v1/projects/{pid}/dataset-imports",
            headers=_h("imp-seg"),
            files={"file": ("seg.zip", z, "application/zip")},
            data={"datasetName": "分割集", "profile": "segment"},
        )
        assert r.status_code == 202, r.text
        row = _wait_import(client, r.json()["id"], "imp-seg")
        assert row["status"] == "succeeded", row
        assert row["stats"]["profile"] == "segment"
        ds_id = r.json()["dataset_id"]
        ds = client.get(f"/api/v1/datasets/{ds_id}", headers=_h("imp-seg")).json()
        assert "polygon" in ds["enabled_annotation_types"]
        mem = client.get(
            f"/api/v1/datasets/{ds_id}/assets", headers=_h("imp-seg")
        ).json()
        ann = client.get(
            f"/api/v1/datasets/{ds_id}/assets/{mem[0]['asset_id']}/annotation",
            headers=_h("imp-seg"),
        ).json()
        items = ann["shapes"]["items"]
        assert len(items) == 1
        assert items[0]["type"] == "polygon"
        assert len(items[0]["points"]) == 4


def test_import_obb_and_pose_profiles() -> None:
    obb_z = _profile_zip(
        "obb",
        "0 0.4 0.3 0.6 0.3 0.6 0.7 0.4 0.7",
    )
    pose_z = _profile_zip(
        "pose",
        "0 0.5 0.5 0.2 0.2 0.2 0.3 2 0.8 0.7 2",
        yaml_extra="kpt_shape: [2, 3]\n",
    )
    with TestClient(app) as client:
        pid = client.post(
            "/api/v1/projects", json={"name": "obbpose导入"}, headers=_h("imp-op")
        ).json()["id"]

        r1 = client.post(
            f"/api/v1/projects/{pid}/dataset-imports",
            headers=_h("imp-op"),
            files={"file": ("obb.zip", obb_z, "application/zip")},
            data={"datasetName": "旋转集", "profile": "obb"},
        )
        assert r1.status_code == 202, r1.text
        row1 = _wait_import(client, r1.json()["id"], "imp-op")
        assert row1["status"] == "succeeded", row1
        ds1 = client.get(
            f"/api/v1/datasets/{r1.json()['dataset_id']}", headers=_h("imp-op")
        ).json()
        assert "obb" in ds1["enabled_annotation_types"]
        mem1 = client.get(
            f"/api/v1/datasets/{r1.json()['dataset_id']}/assets",
            headers=_h("imp-op"),
        ).json()
        ann1 = client.get(
            f"/api/v1/datasets/{r1.json()['dataset_id']}/assets/{mem1[0]['asset_id']}/annotation",
            headers=_h("imp-op"),
        ).json()
        assert ann1["shapes"]["items"][0]["type"] == "obb"

        r2 = client.post(
            f"/api/v1/projects/{pid}/dataset-imports",
            headers=_h("imp-op"),
            files={"file": ("pose.zip", pose_z, "application/zip")},
            data={"datasetName": "姿态集", "profile": "pose"},
        )
        assert r2.status_code == 202, r2.text
        row2 = _wait_import(client, r2.json()["id"], "imp-op")
        assert row2["status"] == "succeeded", row2
        assert row2["stats"]["profile"] == "pose"
        ds2 = client.get(
            f"/api/v1/datasets/{r2.json()['dataset_id']}", headers=_h("imp-op")
        ).json()
        assert "keypoint" in ds2["enabled_annotation_types"]
        mem2 = client.get(
            f"/api/v1/datasets/{r2.json()['dataset_id']}/assets",
            headers=_h("imp-op"),
        ).json()
        ann2 = client.get(
            f"/api/v1/datasets/{r2.json()['dataset_id']}/assets/{mem2[0]['asset_id']}/annotation",
            headers=_h("imp-op"),
        ).json()
        assert ann2["shapes"]["items"][0]["type"] == "keypoint"
        assert len(ann2["shapes"]["items"][0]["points"]) == 2
